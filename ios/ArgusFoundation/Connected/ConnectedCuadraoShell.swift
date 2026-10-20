import SwiftUI
import ArgusSession

struct ConnectedCuadraoShell: View {
    @Binding var appearance: AppearancePreference
    @EnvironmentObject private var auth: ProfileAuthModel
    @Environment(\.locale) private var locale
    @State private var tab: CuadraoTab = .home
    @State private var destination: AppDestination = .home
    @State private var sheet: FoundationSheet?
    @State private var navigationScroll = CuadraoNavigationScroll()
    @State private var planScroll = CuadraoNavigationScroll()
    @State private var searchScroll = CuadraoNavigationScroll()
    @State private var profileScroll = CuadraoNavigationScroll()
    @State private var homePath: [ConnectedHomeRoute] = []
    @State private var profilePath: [CanvasProfileRoute] = []
    @State private var avatar: CuadraoAvatarSelection = .none
    @State private var chat = CuadraoChatPreview(spanish: Locale.current.language.languageCode?.identifier == "es", includeExamples: false)
    @State private var chatEditing = false
    @State private var searchDetail = false
    @State private var addNotice: AddNotice?
    @State private var creatingPlan = false
    @State private var capturing: ReceiptSourceChoice?
    /// Files the picker returned, kept until its cover has closed so the next sheet can open.
    @State private var captured: [(data: Data, name: String, pdf: Bool)]?

    private var spanish: Bool { locale.language.languageCode?.identifier == "es" }

    @ViewBuilder
    var body: some View {
        if let loop = auth.financialLoop {
            FinancialPlanNavigationState(loop: loop, tab: $tab) { allowed in
                householdShell(allowsFinancialNavigation: allowed)
            }
        } else {
            householdShell(allowsFinancialNavigation: true)
        }
    }

    @ViewBuilder private func householdShell(allowsFinancialNavigation: Bool) -> some View {
        if let household = auth.household {
            HouseholdNavigationVisibility(model: household, tab: householdTab(tab),
                active: tab != .profile && tab != .assistant) { allowed in
                shell(allowsHouseholdNavigation: allowed && allowsFinancialNavigation)
            }
        } else {
            shell(allowsHouseholdNavigation: allowsFinancialNavigation)
        }
    }

    private func shell(allowsHouseholdNavigation: Bool) -> some View {
        CuadraoAppShell(selection: $tab, chat: chat, spanish: spanish,
            showsNavigation: showsNavigation && allowsHouseholdNavigation, compact: scroll(for: tab)?.compact ?? false,
            avatar: avatar, profileName: auth.profile?.displayName ?? "", addItems: addItems) { _ in
            ForEach(CuadraoTab.allCases.filter { $0 != .assistant || CuadraoFirstRelease.hasAssistant }) { item in
                tabContent(item)
                    .toolbar(.hidden, for: .tabBar)
                    .tag(item)
            }
        }
        .background { if let household = auth.household { HouseholdPresenter(model: household) } }
        .background { if let household = auth.household { HouseholdPlanPresenter(model: household.plan) } }
        .background {
            if let loop = auth.financialLoop {
                FinancialBudgetSheets(model: loop.budgets, loop: loop, search: auth.financialSearch)
                FinancialGoalSheets(model: loop.goals, loop: loop, search: auth.financialSearch)
                FinancialDebtSheets(model: loop.debts, loop: loop, search: auth.financialSearch)
            }
        }
        .background {
            if let loop = auth.financialLoop { FinancialEditorPresenter(loop: loop, appearance: appearance) }
        }
        .background {
            if let accounts = auth.accounts, let loop = auth.financialLoop {
                FinancialDomainPresenter(accounts: accounts, plan: loop.plan, loop: loop, search: auth.financialSearch)
            }
        }
        .sheet(item: $sheet) { selected in
            if selected == .updates {
                ConnectedCuadraoUpdates(spanish: spanish) {
                    sheet = nil
                    tab = .profile
                    profilePath = [.notifications]
                }.preferredColorScheme(appearance.colorScheme)
            } else {
                FoundationSheetView(sheet: selected, appearance: $appearance)
                    .preferredColorScheme(appearance.colorScheme)
                    .tint(ArgusStyle.ink)
                    .foregroundStyle(ArgusStyle.ink)
            }
        }
        .savedReceiptOutcome(auth.savedReceipts, spanish: spanish)
        .environment(\.receiptJourney, auth.receiptJourney)
        .receiptJourney(auth.receiptJourney, spanish: spanish) {
            Task {
                await auth.savedReceipts?.load()
                await auth.financialLoop?.refresh()
                auth.financialSearch?.invalidate()
            }
        }
        .fullScreenCover(item: $capturing, onDismiss: {
            ScanTrace.mark("scanner closed")
            if let files = captured { captured = nil; keep(files) }
        }) { source in
            ReceiptNativePicker(source: source, spanish: spanish) { result in
                switch result {
                case .success(let files):
                    // The scanner stays up until the files are ready; it then closes and the consent sheet opens.
                    Task {
                        captured = await SavedReceiptFiles.preparing(files, source: source, spanish: spanish)
                        ScanTrace.mark("prepared files=\(captured?.count ?? 0)")
                        capturing = nil
                    }
                    return
                case .failure(let error) where (error as NSError).code != NSUserCancelledError || (error as NSError).domain != NSCocoaErrorDomain:
                    capturing = nil
                    auth.savedReceipts?.fail(.unusableFile)
                case .failure:
                    capturing = nil
                }
            }.ignoresSafeArea()
        }
        .sheet(isPresented: $creatingPlan) {
            if let loop = auth.financialLoop { ConnectedPlanEditor(loop: loop, seed: .create(kind: nil)) }
        }
        .alert(addNotice.map { LocalizedStringKey($0.title) } ?? "", isPresented: Binding(get: { addNotice != nil }, set: { if !$0 { addNotice = nil } }),
               presenting: addNotice) { _ in
        } message: { notice in
            if let message = notice.message { Text(LocalizedStringKey(message)) }
        }
        .connectedReceiptDrafts(
            userID: auth.profile.flatMap { UUID(uuidString: $0.id) },
            chat: chat,
            spanish: spanish
        )
        .tint(WelcomePalette.pine)
        .foregroundStyle(WelcomePalette.ink)
        .background(WelcomePalette.background.ignoresSafeArea())
        .onChange(of: destination) { _, value in mapDestination(value) }
        .onChange(of: tab) { _, value in mapTab(value) }
        .onChange(of: auth.profile?.id) { _, _ in
            avatar = .none
            profilePath = []
            homePath = []
            searchDetail = false
            chat = CuadraoChatPreview(spanish: spanish, includeExamples: false)
        }
    }

    private var showsNavigation: Bool {
        guard (homePath.isEmpty || tab != .home), (profilePath.isEmpty || tab != .profile),
              !(tab == .assistant && chatEditing), !(tab == .search && searchDetail) else { return false }
        return true
    }

    @ViewBuilder private func tabContent(_ item: CuadraoTab) -> some View {
        if item != .profile && item != .assistant, let household = auth.household {
            HouseholdDestinationRouter(model: household, tab: householdTab(item), active: tab == item, destination: $destination,
                navigationScroll: navigationScroll, showUpdates: updatesAction) { personalTabContent(item) }
        } else { personalTabContent(item) }
    }

    @ViewBuilder private func personalTabContent(_ item: CuadraoTab) -> some View {
        switch item {
        case .home:
            if let loop = auth.financialLoop, let accounts = auth.accounts {
                ConnectedCuadraoHome(loop: loop, accounts: accounts, tab: $tab, homePath: $homePath,
                                     navigationScroll: navigationScroll, showUpdates: updatesAction)
            } else {
                ProgressView("accounts.loading")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        case .plan:
            NavigationStack {
                FinancialPlanDestination(showProfile: { tab = .profile }, nativeNavigation: true, audience: planAudience)
                    .toolbar(.hidden, for: .navigationBar)
            }
            .modifier(CuadraoNavigationScrollObserver(scroll: planScroll, enabled: tab == .plan && sheet == nil))
        case .assistant:
            NavigationStack {
                CuadraoChatCanvas(store: chat, spanish: spanish, editing: $chatEditing, showsPreviewNotice: true)
                    .toolbar(.hidden, for: .navigationBar)
            }
        case .search:
            FinancialSearchDestination(active: tab == .search, showProfile: { tab = .profile }, nativePlanNavigation: true, detailChanged: { searchDetail = $0 })
                .modifier(CuadraoNavigationScrollObserver(scroll: searchScroll, enabled: tab == .search && !searchDetail))
        case .profile:
            ConnectedCuadraoProfile(appearance: $appearance, avatar: $avatar, path: $profilePath)
                .modifier(CuadraoNavigationScrollObserver(scroll: profileScroll, enabled: tab == .profile && profilePath.isEmpty))
        }
    }

    /// Each tab folds the bar from its own scroll, so a long Plan, Search or Profile folds it as Home does.
    private func scroll(for item: CuadraoTab) -> CuadraoNavigationScroll? {
        switch item {
        case .home: navigationScroll
        case .plan: planScroll
        case .search: searchScroll
        case .profile: profileScroll
        case .assistant: nil
        }
    }

    private var updatesAction: (() -> Void)? {
        CuadraoFirstRelease.showsUpdates ? { sheet = .updates } : nil
    }

    private var addableAccounts: [FinancialAccount] {
        let live = (auth.accounts?.accounts ?? []).filter { !$0.archived }
        return ConnectedAccountOrder.applying(auth.profile.map { ConnectedAccountOrder.load(for: $0.id) } ?? [], to: live)
    }

    /// The rows of the + tray. A row appears only when the thing behind it is real in this build.
    private var addItems: [CuadraoAddItem] {
        let household = auth.household
        return CuadraoAddAction.available(
            receiptsConnected: CuadraoFirstRelease.savedReceipts,
            householdsAvailable: household?.isAvailable == true,
            inHousehold: household?.active == true
        ).compactMap { action in
            switch action {
            case .account: CuadraoAddItem(action: action, perform: addAccount)
            case .transaction: CuadraoAddItem(action: action, perform: addMovement)
            case .plan: CuadraoAddItem(action: action, perform: addPlan)
            case .group, .invite: CuadraoAddItem(action: action) { household?.showManagement = true }
            case .scanCamera: CuadraoAddItem(action: action) { capture(.scan) }
            case .choosePhoto: CuadraoAddItem(action: action) { capture(.photos) }
            case .chooseFile: CuadraoAddItem(action: action) { capture(.file) }
            }
        }
    }

    /// Captured files go through the receipt journey, which asks once before any of them is read.
    private func keep(_ files: [(data: Data, name: String, pdf: Bool)]) {
        if let journey = auth.receiptJourney {
            journey.begin(files)
        } else {
            Task { await auth.savedReceipts?.save(files) }
        }
    }

    private func capture(_ source: ReceiptSourceChoice) {
        #if DEBUG
        if CuadraoFirstRelease.savedReceiptsSample {
            keep(SampleSavedReceiptsTransport.files(for: source))
            return
        }
        if SyntheticReceipt.active {
            keep([SyntheticReceipt.file()])
            return
        }
        #endif
        if source == .scan && !SavedReceiptFiles.scannerAvailable {
            auth.savedReceipts?.fail(.scannerUnavailable)
            return
        }
        capturing = source
    }

    private func addAccount() {
        guard let accounts = auth.accounts else {
            addNotice = AddNotice(title: "accounts.loading", message: nil)
            return
        }
        Task {
            if !accounts.hasLoaded { await accounts.load() }
            guard accounts.hasLoaded else {
                addNotice = AddNotice(title: accounts.errorKey ?? "accounts.loading", message: nil)
                return
            }
            accounts.create()
        }
    }

    private func addPlan() {
        guard let loop = auth.financialLoop else {
            addNotice = AddNotice(title: "accounts.loading", message: nil)
            return
        }
        guard loop.pendingConfirmation == nil else {
            addNotice = AddNotice(title: loop.pendingTitle, message: "loop.pending.body")
            return
        }
        // The Plan tab's own Create needs the projection and no save in flight; without it the editor has no accounts.
        Task {
            if loop.plan.projection == nil { await loop.refresh() }
            guard loop.plan.projection != nil, !loop.plan.saving else {
                addNotice = AddNotice(title: loop.plan.homeErrorKey ?? "accounts.loading", message: nil)
                return
            }
            creatingPlan = true
        }
    }

    /// The "Transaction" row records a movement from any tab, through the same rule as Home's Activity "+".
    /// When it cannot act (accounts not ready, or a write waiting for confirmation) it says why in an
    /// alert, because the personal Home that explains it is not on screen in every mode.
    private func addMovement() {
        guard let loop = auth.financialLoop, let accounts = auth.accounts else {
            addNotice = AddNotice(title: "accounts.loading", message: nil)
            return
        }
        guard loop.pendingConfirmation == nil else {
            addNotice = AddNotice(title: loop.pendingTitle, message: "loop.pending.body")
            return
        }
        Task {
            if !accounts.hasLoaded { await accounts.load() }
            switch ConnectedAddMovement.target(for: addableAccounts, loaded: accounts.hasLoaded, preferredCurrency: auth.profile?.currency) {
            case .loadAccounts: addNotice = AddNotice(title: accounts.errorKey ?? "accounts.loading", message: nil)
            case .createAccount: accounts.create()
            case .record(let account): loop.record(account)
            }
        }
    }

    private var planAudience: Binding<Bool>? {
        guard let household = auth.household, household.isAvailable else { return nil }
        return Binding(get: { household.active }, set: { together in
            guard together else { return }
            if household.households.count == 1, let only = household.households.first {
                Task { await household.select(only.id) }
            } else {
                household.showManagement = true
            }
        })
    }

    private func householdTab(_ item: CuadraoTab) -> AppDestination {
        switch item { case .home, .profile: .home; case .plan: .plan; case .assistant: .argus; case .search: .search }
    }

    private func mapDestination(_ value: AppDestination) {
        switch value {
        case .accounts:
            tab = .home
            if let accounts = auth.accounts, let loop = auth.financialLoop {
                if let account = accounts.selected {
                    if homePath != [.account(account.id)] { homePath = [.account(account.id)] }
                    Task { await accounts.open(account); await loop.open(account) }
                } else if let id = accounts.selectedID {
                    if homePath != [.account(id)] { homePath = [.account(id)] }
                }
            }
            if destination != .home { destination = .home }
        case .plan: tab = .plan
        case .search: tab = .search
        case .home:
            tab = .home
            if !homePath.isEmpty { homePath = [] }
        case .argus: if CuadraoFirstRelease.hasAssistant { tab = .assistant }
        }
    }

    private func mapTab(_ value: CuadraoTab) {
        switch value {
        case .home: if destination != .home && destination != .accounts { destination = .home }
        case .plan: destination = .plan
        case .assistant: destination = .argus
        case .search: destination = .search
        case .profile: break
        }
    }
}

/// Why the navigation + could not act, as localization keys.
private struct AddNotice: Identifiable {
    let title: String
    let message: String?
    var id: String { title }
}

private struct HouseholdNavigationVisibility<Content: View>: View {
    @ObservedObject var model: HouseholdModel
    @ObservedObject private var plan: HouseholdPlanModel
    let tab: AppDestination
    let active: Bool
    @ViewBuilder let content: (Bool) -> Content

    init(model: HouseholdModel, tab: AppDestination, active: Bool, @ViewBuilder content: @escaping (Bool) -> Content) {
        self.model = model
        plan = model.plan
        self.tab = tab
        self.active = active
        self.content = content
    }

    var body: some View {
        let detail = (model.detail != nil && tab != .plan) ||
            (plan.openedRef != nil && plan.origin.rawValue == tab.rawValue)
        content(!active || !model.active || !detail)
    }
}
