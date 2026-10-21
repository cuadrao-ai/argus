import SwiftUI
import ArgusSession

/// Cuadrao Home chrome bound to tip accounts + financial loop.
struct ConnectedCuadraoHome: View {
    @ObservedObject var loop: FinancialLoopModel
    @ObservedObject var accounts: AccountsModel
    @ObservedObject private var plan: FinancialPlanModel
    @Binding var tab: CuadraoTab
    @Binding var homePath: [ConnectedHomeRoute]
    let navigationScroll: CuadraoNavigationScroll
    let showUpdates: (() -> Void)?

    @AppStorage("cuadrao.design.home-section-order") private var homeOrder = CuadraoHomeSection.defaultOrder
    @EnvironmentObject private var auth: ProfileAuthModel
    @State private var householdDestination: AppDestination = .home
    @Environment(\.locale) private var locale
    @State private var sheet: HomeSheet?
    @State private var moreAccount: FinancialAccount?
    @State private var archivedID: UUID?
    @State private var accountOrder: [UUID] = []

    private var spanish: Bool { locale.language.languageCode?.identifier == "es" }
    private var activeAccounts: [FinancialAccount] {
        ConnectedAccountOrder.applying(accountOrder, to: accounts.accounts.filter { !$0.archived })
    }
    private var archivedAccounts: [FinancialAccount] { accounts.accounts.filter(\.archived) }

    private enum HomeSheet: Identifiable {
        case customize, archived, options
        case archive(FinancialAccount)
        var id: String {
            switch self {
            case .customize: "customize"
            case .archived: "archived"
            case .options: "options"
            case .archive(let account): "archive." + account.id.uuidString
            }
        }
    }

    init(loop: FinancialLoopModel, accounts: AccountsModel, tab: Binding<CuadraoTab>,
         homePath: Binding<[ConnectedHomeRoute]>, navigationScroll: CuadraoNavigationScroll, showUpdates: (() -> Void)?) {
        self.loop = loop
        self.accounts = accounts
        self.plan = loop.plan
        self._tab = tab
        self._homePath = homePath
        self.navigationScroll = navigationScroll
        self.showUpdates = showUpdates
    }

    var body: some View {
        NavigationStack(path: $homePath) {
            CuadraoHomeLayout(order: CuadraoHomeSection.decode(homeOrder),
                canCustomize: !activeAccounts.isEmpty, spanish: spanish, customize: { sheet = .customize }) {
                header
                if let household = auth.household {
                    ConnectedCuadraoSpaces(model: household, destination: $householdDestination)
                } else {
                    Text("household.personal").font(.subheadline.weight(.semibold)).frame(minHeight: 44)
                }
            } notice: {
                if loop.pendingConfirmation != nil { pendingBanner }
                if let recoveryError = loop.recoveryErrorKey {
                    Text(LocalizedStringKey(recoveryError)).foregroundStyle(.secondary)
                }
                if let error = accounts.errorKey {
                    Text(LocalizedStringKey(error)).foregroundStyle(.secondary)
                    Button("accounts.retry") { Task { await accounts.load() } }.frame(minHeight: 44)
                }
                if let error = plan.homeErrorKey {
                    Text(LocalizedStringKey(error)).foregroundStyle(.secondary)
                    Button("accounts.retry") { Task { await loop.refresh() } }.frame(minHeight: 44)
                }
            } section: { homeSection($0) }
            .accessibilityIdentifier("screen.home")
            .modifier(CuadraoNavigationScrollObserver(scroll: navigationScroll,
                enabled: tab == .home && sheet == nil && homePath.isEmpty))
            .background(WelcomePalette.background)
            .navigationTitle("").navigationBarTitleDisplayMode(.inline)
            .toolbar(.hidden, for: .navigationBar)
            .navigationDestination(for: ConnectedHomeRoute.self) { route in
                switch route {
                case .activity(let id): activityDetail(id)
                case .account(let id): accountDetail(id)
                }
            }
            .financialPlanDestinations(loop: loop, search: auth.financialSearch, host: .home,
                accountDetailPresented: homePath.last?.accountID != nil)
        }
        .task(id: accounts.identity?.revision) { await accounts.load(); await loop.refresh() }
        .onChange(of: accounts.accounts) { _, _ in Task { await loop.refresh() } }
        .onChange(of: accounts.selectedID) { _, id in
            if let id {
                if homePath.last?.accountID != id { homePath.append(.account(id)) }
            } else if !homePath.isEmpty, !showsActivity {
                homePath = []
            }
        }
        .onChange(of: homePath) { previous, path in
            guard path.count < previous.count, let id = accounts.selectedID,
                  previous.contains(.account(id)), !path.contains(.account(id)), loop.activityEditor == nil,
                  loop.editor == nil, accounts.draft == nil else { return }
            accounts.back()
        }
        .onChange(of: accounts.busy) { _, busy in
            guard !busy, let id = accounts.selectedID, !homePath.contains(.account(id)),
                  loop.activityEditor == nil, loop.editor == nil, accounts.draft == nil else { return }
            accounts.back()
        }
        .onChange(of: accounts.draft == nil) { _, closed in
            if closed { restoreDetailPath() }
        }
        .onChange(of: loop.activityEditor == nil) { _, closed in
            if closed { restoreDetailPath() }
        }
        .onChange(of: loop.editor == nil) { _, closed in
            if closed { restoreDetailPath() }
        }
        .task(id: auth.profile?.id) {
            accountOrder = auth.profile.map { ConnectedAccountOrder.load(for: $0.id) } ?? []
        }
        .refreshable { await accounts.load(); await loop.refresh() }
        .confirmationDialog(Text(verbatim: moreAccount.map(accountName) ?? ""), isPresented: Binding(get: { moreAccount != nil }, set: { if !$0 { moreAccount = nil } }),
                            titleVisibility: .visible, presenting: moreAccount) { account in
            if !account.isOptionalAsset {
                Button(NSLocalizedString("loop.check.title", comment: "")) { loop.check(account) }.accessibilityIdentifier("accounts.more.check")
            }
            Button(spanish ? "Archivar" : "Archive", role: .destructive) { sheet = .archive(account) }
                .accessibilityIdentifier("accounts.more.archive")
        }
        .sheet(item: $sheet) { item in modal(item) }
        .overlay(alignment: .bottom) {
            if let archivedID, homePath.isEmpty, accounts.accounts.first(where: { $0.id == archivedID })?.archived == true {
                CuadraoToast(text: spanish ? "Cuenta archivada" : "Account archived", actionTitle: spanish ? "Deshacer" : "Undo",
                    actionIdentifier: "accounts.archived.undo", action: { restore(archivedID) }, spanish: spanish,
                    token: archivedID, close: { self.archivedID = nil })
            }
        }
        .onChange(of: accounts.identity?.revision) { _, _ in archivedID = nil }
        .onChange(of: householdDestination) { _, _ in archivedID = nil }
    }

    /// Archive is one canonical write; the toast appears only once the server returns the account archived.
    private func archive(_ chosen: FinancialAccount) {
        archivedID = nil
        let account = accounts.accounts.first(where: { $0.id == chosen.id }) ?? chosen
        Task {
            await accounts.archive(account)
            guard accounts.accounts.first(where: { $0.id == account.id })?.archived == true else { return }
            homePath = []
            archivedID = account.id
        }
    }

    private func restore(_ id: UUID) {
        guard let account = accounts.accounts.first(where: { $0.id == id }), account.archived else { archivedID = nil; return }
        Task {
            await accounts.archive(account)
            if accounts.accounts.first(where: { $0.id == id })?.archived == false, archivedID == id { archivedID = nil }
        }
    }

    /// Activity routes never belong to the accounts selection, so selection changes leave them alone.
    private var showsActivity: Bool { homePath.contains { $0.accountID == nil } }

    private func accountName(_ account: FinancialAccount) -> String {
        account.nickname ?? NSLocalizedString("accounts.type." + account.type, comment: "")
    }

    @ViewBuilder private func activityDetail(_ id: UUID) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                FinancialActivityDetailView(loop: loop, activityID: id, accounts: accounts.accounts,
                    openAccount: { accountID in
                        guard let account = accounts.accounts.first(where: { $0.id == accountID }) else { return }
                        homePath.append(.account(accountID))
                        Task { await accounts.open(account); await loop.open(account) }
                    }) { loop.correct($0) }
            }.padding(24)
        }
        .accessibilityIdentifier("screen.activity")
        .background(WelcomePalette.background)
        .navigationTitle("loop.activity.title").navigationBarTitleDisplayMode(.inline)
        .toolbar(.visible, for: .navigationBar)
    }

    @ViewBuilder private func accountDetail(_ id: UUID) -> some View {
        if let account = accounts.accounts.first(where: { $0.id == id }) {
            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    AccountDetailView(account: account, model: accounts, loop: loop, nativePlanNavigation: true, search: auth.financialSearch,
                        archive: { archive($0) })
                }.padding(24)
            }
            .accessibilityIdentifier("screen.accounts")
            .refreshable { await accounts.refresh(account.id); await loop.open(account) }
            .background(WelcomePalette.background)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar(.visible, for: .navigationBar)
        }
    }

    private func restoreDetailPath() {
        guard loop.activityEditor == nil, loop.editor == nil, !showsActivity,
              let id = accounts.selectedID, homePath.last?.accountID != id else { return }
        homePath.append(.account(id))
    }

    private var header: some View {
        HStack {
            CuadraoHomeGreeting(name: auth.profile?.preferredName ?? "", spanish: spanish)
            Spacer()
            if let showUpdates { CuadraoUpdatesButton(spanish: spanish, action: showUpdates) }
        }
    }

    private var pendingBanner: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(LocalizedStringKey(loop.pendingTitle)).font(.body)
            Text("loop.pending.body").font(.caption).foregroundStyle(.secondary)
            Button("loop.pending.retry") { Task { await loop.retryPending() } }
                .buttonStyle(PillButtonStyle()).disabled(loop.recovering)
                .accessibilityIdentifier("loop.pending.retry")
        }.padding(16).overlay(RoundedRectangle(cornerRadius: 14).stroke(WelcomePalette.border))
    }

    @ViewBuilder private func homeSection(_ section: CuadraoHomeSection) -> some View {
        switch section {
        case .overview:
            if let home = loop.home, !home.currencies.isEmpty {
                overview(home)
            }
        case .upcoming:
            if !activeAccounts.isEmpty {
                FinancialComingUpView(model: plan, viewPlan: { tab = .plan })
            }
        case .accounts:
            accountsSection
        case .activity:
            if let home = loop.home, !home.recentActivity.isEmpty {
                activity(home)
            }
        }
    }

    private func overview(_ home: FinancialHome) -> some View {
        ConnectedCuadraoBalanceOverview(home: home, spanish: spanish, loop: loop, accounts: accounts.accounts)
    }

    private var accountsSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            if !activeAccounts.isEmpty || !archivedAccounts.isEmpty {
                HStack(spacing: 0) {
                    Button { sheet = .options } label: {
                        HStack(spacing: 8) {
                            Text(spanish ? "Cuentas" : "Accounts").font(CuadraoTypography.section)
                            Image(systemName: "chevron.right").font(.caption2).foregroundStyle(.secondary)
                        }.frame(minHeight: 44).contentShape(Rectangle())
                    }.buttonStyle(.plain).accessibilityIdentifier("accounts.manage")
                    Spacer()
                    CuadraoSectionAddButton(title: spanish ? "Añadir cuenta" : "Add account") { accounts.create() }
                        .accessibilityLabel(spanish ? "Añadir cuenta" : "Add account")
                        .accessibilityIdentifier("accounts.add")
                }
            }
            accountRows
            if activeAccounts.isEmpty {
                if !accounts.hasLoaded && accounts.errorKey == nil { ProgressView("accounts.loading") }
                else if accounts.errorKey == nil { personalEmpty }
            }
        }
    }

    /// The Preview's collection owns hold and drag, so Home accounts reorder the way the Plan cards do. The order
    /// stays on this device for this person; swipes keep Add movement, Edit and More.
    private var accountRows: some View {
        CuadraoOrderedCollection(items: activeAccounts, spanish: spanish, spacing: 0,
            identifier: { "accounts.row.\($0.id)" },
            open: { account in Task { await accounts.open(account); await loop.open(account) } },
            edit: { accounts.rename($0) }, archive: { sheet = .archive($0) }, reorder: saveAccountOrder,
            leadingSwipes: { swipes(accountActions($0, edge: .leading)) },
            trailingSwipes: { swipes(accountActions($0, edge: .trailing)) }) { account in
            ConnectedAccountRow(account: account, spanish: spanish)
                .overlay(alignment: .bottom) { Rectangle().fill(WelcomePalette.separator).frame(height: 1).padding(.leading, 54) }
        }.id(loop.pendingConfirmation == nil)
    }

    private func swipes(_ actions: [ConnectedSwipeAction]) -> [CuadraoCollectionSwipe] {
        actions.map { CuadraoCollectionSwipe(id: $0.id, title: $0.title, symbol: $0.symbol, tint: $0.tint, action: $0.action) }
    }

    private func saveAccountOrder(_ ids: [UUID]) {
        guard let user = auth.profile?.id else { return }
        accountOrder = ids
        ConnectedAccountOrder.save(ids, for: user)
    }

    /// Swipe right adds a movement; swipe left edits or opens More (Archive and other existing commands).
    private func accountActions(_ account: FinancialAccount, edge: HorizontalEdge) -> [ConnectedSwipeAction] {
        guard loop.pendingConfirmation == nil else { return [] }
        switch edge {
        case .leading:
            return [.init(id: "accounts.swipe.record", title: spanish ? "Añadir movimiento" : "Add movement", symbol: "plus", tint: WelcomePalette.pine) { loop.record(account) }]
        case .trailing:
            return [.init(id: "accounts.swipe.edit", title: spanish ? "Editar" : "Edit", symbol: "pencil", tint: .blue) { accounts.rename(account) },
                    .init(id: "accounts.swipe.more", title: spanish ? "Más" : "More", symbol: "ellipsis", tint: .gray) { moreAccount = account }]
        }
    }

    /// Edit and Category both go through the same correction owner, so every gate the detail applies applies here.
    private func movementActions(_ entry: FinancialActivity, edge: HorizontalEdge) -> [ConnectedSwipeAction] {
        guard loop.pendingConfirmation == nil, entry.active != false else { return [] }
        let id = entry.activityId ?? entry.recordId
        switch edge {
        case .leading:
            return [.init(id: "home.activity.swipe.edit", title: spanish ? "Editar" : "Edit", symbol: "pencil", tint: .blue) { correct(id, focusCategory: false) }]
        case .trailing:
            guard entry.kind == "expense" else { return [] }
            return [.init(id: "home.activity.swipe.category", title: spanish ? "Categoría" : "Category", symbol: "tag", tint: .orange) { correct(id, focusCategory: true) }]
        }
    }

    private func correct(_ activityID: UUID, focusCategory: Bool) {
        Task {
            // The detail explains a failed read or why this movement cannot be corrected, so a swipe never does nothing.
            guard let detail = try? await loop.detail(id: activityID), loop.canCorrect(detail) else {
                homePath.append(.activity(activityID)); return
            }
            loop.correct(detail, focusCategory: focusCategory)
        }
    }

    private var personalEmpty: some View {
        CuadraoPersonalAccountsEmpty(spanish: spanish) { accounts.create() }
    }

    private func activity(_ home: FinancialHome) -> some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Text(spanish ? "Movimientos" : "Activity")
                    .font(CuadraoTypography.section)
                    .accessibilityAddTraits(.isHeader)
                Spacer()
                CuadraoSectionAddButton(title: spanish ? "Añadir movimiento" : "Add activity") {
                    switch ConnectedAddMovement.target(for: activeAccounts, loaded: accounts.hasLoaded, preferredCurrency: auth.profile?.currency) {
                    case .record(let account): loop.record(account)
                    case .loadAccounts: Task { await accounts.load() }
                    case .createAccount: break
                    }
                }
                .disabled(activeAccounts.isEmpty || loop.pendingConfirmation != nil)
                .accessibilityIdentifier("home.record")
            }
            VStack(spacing: 0) {
                ForEach(home.recentActivity, id: \.recordId) { entry in
                    if let account = accounts.accounts.first(where: { $0.id == entry.accountId }) {
                        ConnectedSwipeRow(leading: movementActions(entry, edge: .leading), trailing: movementActions(entry, edge: .trailing)) {
                            ConnectedCuadraoMovementRow(activity: entry, account: account)
                                .onTapGesture { homePath.append(.activity(entry.activityId ?? entry.recordId)) }
                                .accessibilityElement(children: .combine)
                                .accessibilityAddTraits(.isButton)
                                .accessibilityIdentifier("home.activity." + (entry.activityId ?? entry.recordId).uuidString)
                        }
                    }
                }
            }.connectedSwipeContainer()
        }
    }

    @ViewBuilder private func modal(_ item: HomeSheet) -> some View {
        switch item {
        case .customize:
            CuadraoHomeLayoutSheet(savedOrder: $homeOrder, spanish: spanish)
        case .options:
            ConnectedArchivedAccounts(accounts: accounts, spanish: spanish, showAll: true)
        case .archived:
            ConnectedArchivedAccounts(accounts: accounts, spanish: spanish)
        case .archive(let account):
            CuadraoArchiveAccountReview(spanish: spanish) { archive(account) }
        }
    }

}

private struct ConnectedArchivedAccounts: View {
    @ObservedObject var accounts: AccountsModel
    let spanish: Bool
    var showAll = false
    @Environment(\.dismiss) private var dismiss

    private var displayed: [FinancialAccount] { showAll ? accounts.accounts : accounts.accounts.filter(\.archived) }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    if !showAll {
                        Text(spanish ? "Sus balances e historial se conservan." : "Balances and history are kept.")
                            .font(.subheadline).foregroundStyle(.secondary)
                    }
                    if displayed.isEmpty {
                        ContentUnavailableView(spanish ? "No hay cuentas archivadas" : "No archived accounts",
                                               systemImage: "archivebox")
                    }
                    ForEach(displayed) { account in
                        VStack(alignment: .leading, spacing: 0) {
                            Button {
                                Task {
                                    await accounts.open(account)
                                    dismiss()
                                }
                            } label: {
                                ConnectedAccountRow(account: account, spanish: spanish)
                            }
                            .buttonStyle(.plain)
                            .accessibilityIdentifier("accounts.row.\(account.id)")
                            if account.archived {
                                CanvasActionRow(title: spanish ? "Restaurar" : "Restore", symbol: "arrow.uturn.backward") {
                                    Task { await accounts.archive(account) }
                                }.foregroundStyle(WelcomePalette.pine)
                            }
                            Divider()
                        }
                    }
                }.padding(24)
            }.background(WelcomePalette.background)
                .navigationTitle(showAll ? (spanish ? "Cuentas" : "Accounts") : (spanish ? "Cuentas archivadas" : "Archived accounts"))
                .navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement: .topBarLeading) {
                        Button {
                            dismiss()
                        } label: {
                            Label("accounts.back", systemImage: "chevron.left")
                        }
                        .accessibilityIdentifier("accounts.manage.back")
                    }
                }
        }.tint(WelcomePalette.pine)
    }
}
