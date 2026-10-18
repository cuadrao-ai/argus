import SwiftUI

/// Independent native design canvas. Sample values never reach financial services.
struct CuadraoHomeCanvas: View {
    @AppStorage("cuadrao.design.home-section-order") private var homeOrder = CuadraoHomeSection.defaultOrder
    @State private var populated = (CuadraoCanvas.standalonePreview || ProcessInfo.processInfo.arguments.contains("--home-populated"))
    @State private var selectedTab: CuadraoTab = .home
    @State private var chat = CuadraoChatPreview(spanish: !ProcessInfo.processInfo.arguments.contains("--design-english"),
        includeExamples: CuadraoCanvas.standalonePreview || ProcessInfo.processInfo.arguments.contains("--home-populated"))
    @State private var plans = CuadraoPlanPreview(
        spanish: !ProcessInfo.processInfo.arguments.contains("--design-english"),
        reset: ProcessInfo.processInfo.arguments.contains("--plan-reset"),
        empty: ProcessInfo.processInfo.arguments.contains("--plan-empty"))
    @State private var groups = CuadraoGroupPreview(
        spanish: !ProcessInfo.processInfo.arguments.contains("--design-english"),
        reset: ProcessInfo.processInfo.arguments.contains("--plan-reset"),
        empty: ProcessInfo.processInfo.arguments.contains("--plan-empty"))
    @State private var receipts = CuadraoReceiptStore(reset: ProcessInfo.processInfo.arguments.contains("--receipt-reset"))
    @State private var receiptRoute: ReceiptRoute?
    @State private var receiptRecoveryError = false
    @State private var profile = CanvasProfileDraft()
    @State private var profilePath: [CanvasProfileRoute] = []
    @State private var updateReadIDs: Set<CanvasUpdate> = []
    @State private var searchChatOrigin = false
    @State private var chatEditing = false
    @State private var voiceProposal: CanvasVoiceProposal?
    @State private var navigationScroll = CuadraoNavigationScroll()
    @State private var sheet: HomeSheet?
    @State private var data = CuadraoAccountsPreview(
        populated: (CuadraoCanvas.standalonePreview || ProcessInfo.processInfo.arguments.contains("--home-populated")),
        spanish: !ProcessInfo.processInfo.arguments.contains("--design-english"))
    private enum HomeRoute: Hashable { case account(UUID), activity(UUID) }
    @State private var accountPath: [HomeRoute] = []
    @State private var archivedID: UUID?
    private let spanish = !ProcessInfo.processInfo.arguments.contains("--design-english")

    private enum HomeSheet: Identifiable {
        case add, updates, spaces, customize, household, gallery, releaseReview
        case account(CanvasAccountSheet)
        var id: String { "home-modal" }
    }

    var body: some View {
        CuadraoAppShell(selection: $selectedTab, chat: chat, spanish: spanish,
            showsNavigation: (accountPath.isEmpty || selectedTab != .home) &&
                (profilePath.isEmpty || selectedTab != .profile) && !(selectedTab == .assistant && chatEditing),
            compact: selectedTab == .home && navigationScroll.compact,
            avatar: profile.avatar, profileName: profile.name,
            showProposal: { voiceProposal = .proposed }) { selection in
            NavigationStack(path: $accountPath) {
                CuadraoHomeLayout(order: CuadraoHomeSection.decode(homeOrder),
                    canCustomize: !data.active.isEmpty, spanish: spanish, customize: { sheet = .customize }) {
                    header
                    CuadraoSpaceSelector(data: data, spanish: spanish, add: { sheet = .spaces })
                    if data.selectedSpace.kind == .household {
                        Button { sheet = .household } label: {
                            PlanAvatarStack(members: data.acceptedHouseholdMembers(spanish: spanish))
                                .frame(minHeight: 44).contentShape(Rectangle())
                        }.buttonStyle(.plain)
                            .accessibilityLabel(CuadraoCopy.text("copy.cuadraoHomeCanvas.132a60da1b", spanish: spanish))
                            .accessibilityValue(String(data.acceptedHouseholdMembers(spanish: spanish).count))
                            .accessibilityIdentifier("home-household-members")
                    }
                } notice: { EmptyView() } section: { homeSection($0) }
                .modifier(CuadraoNavigationScrollObserver(scroll: navigationScroll,
                    enabled: selectedTab == .home && sheet == nil && accountPath.isEmpty))
                .navigationTitle("").navigationBarTitleDisplayMode(.inline)
                .toolbar(.hidden, for: .navigationBar)
                .navigationDestination(for: HomeRoute.self) { route in
                    switch route {
                    case .account(let id):
                        CuadraoAccountCanvas(data: data, accountID: id, spanish: spanish,
                            actions: { sheet = .account($0) }, record: { sheet = .account(.record($0)) })
                    case .activity(let id):
                        CuadraoActivityDetail(data: data, activityID: id, spanish: spanish,
                            actions: { sheet = .account($0) }, record: { sheet = .account(.record($0)) })
                    }
                }
            }
            .toolbar(.hidden, for: .tabBar)
            .tag(CuadraoTab.home)
            ForEach(CuadraoTab.allCases.filter { $0 != .home }) { tab in
                destination(tab, selection: selection).tag(tab)
            }
        }
        .sheet(item: $sheet) { item in modal(item) }
        .receiptPresentation(route: $receiptRoute, workspace: receiptWorkspace, spanish: spanish)
        .environment(\.receiptWorkspace, receiptWorkspace)
        .environment(\.cuadraoChat, chat)
        .task {
            do { try receipts.reconcile(groups: groups, accounts: data) }
            catch { receiptRecoveryError = true }
        }
        .alert(CuadraoCopy.text("copy.cuadraoHomeCanvas.e7cc35cd43", spanish: spanish), isPresented: $receiptRecoveryError) {
            Button(CuadraoCopy.text("copy.cuadraoHomeCanvas.1756cbfe73", spanish: spanish)) {}
        } message: { Text(CuadraoCopy.text("copy.cuadraoHomeCanvas.22cf8ed4dd", spanish: spanish)) }
        .onChange(of: populated) { _, value in chat.includeExamples = value }
        .onChange(of: selectedTab) { _, tab in
            if tab != .assistant { searchChatOrigin = false }
        }
        .onChange(of: chat.current.id) { _, _ in voiceProposal = nil }
        .onChange(of: data.selectedSpaceID) { _, _ in
            archivedID = nil; accountPath = []; navigationScroll = CuadraoNavigationScroll()
        }
        .overlay(alignment: .bottom) {
            if let archivedID {
                CuadraoToast(text: CuadraoCopy.text("copy.connectedCuadraoHome.d6e6d390ca", spanish: spanish), actionTitle: CuadraoCopy.text("copy.connectedCuadraoHome.3ec51337bc", spanish: spanish),
                    actionIdentifier: "accounts.archived.undo", action: { data.archive(archivedID, false); self.archivedID = nil }, spanish: spanish,
                    token: archivedID, close: { self.archivedID = nil })
            }
        }
    }

    @ViewBuilder private func homeSection(_ section: CuadraoHomeSection) -> some View {
        switch section {
        case .overview: if !data.active.isEmpty { CuadraoHomeOverview(data: data, spanish: spanish) }
        case .accounts: accounts
        case .activity: if !data.visibleActivity.isEmpty { activity }
        case .upcoming: if populated && data.selectedSpace.kind == .personal { upcoming }
        }
    }

    private var unreadUpdates: Int {
        CanvasUpdate.available(accounts: data, plans: plans).filter { !updateReadIDs.contains($0) }.count
    }

    private var header: some View {
        HStack {
            CuadraoHomeGreeting(name: profile.preferredName, spanish: spanish)
                .contextMenu {
                    #if DEBUG
                    Button(CuadraoCopy.text("copy.cuadraoHomeCanvas.ab31cbb99d", spanish: spanish)) { sheet = .releaseReview }
                    #endif
                    Button(CuadraoCopy.text("copy.cuadraoDesignGallery.b843c5b747", spanish: spanish)) { sheet = .gallery }
                        .accessibilityIdentifier("cuadrao-gallery-open")
                    Button(CuadraoCopy.text("copy.cuadraoHomeCanvas.92cf104f62", spanish: spanish)) {
                        populated = false; data.reset(populated: false, spanish: spanish)
                    }
                    Button(CuadraoCopy.text("copy.cuadraoHomeCanvas.8554f0b8fc", spanish: spanish)) {
                        populated = false; data.reset(populated: false, spanish: spanish)
                        data.openHousehold(); data.household = .joined("Alex")
                    }
                    Button(CuadraoCopy.text("copy.cuadraoHomeCanvas.94026d9b99", spanish: spanish)) {
                        populated = true; data.reset(populated: true, spanish: spanish)
                    }
                }
            Spacer()
            CuadraoUpdatesButton(spanish: spanish, unread: unreadUpdates) { sheet = .updates }
        }
    }

    private var accounts: some View {
        VStack(alignment: .leading, spacing: 12) {
            if !data.active.isEmpty || !data.archived.isEmpty {
                HStack(spacing: 0) {
                    Button { sheet = .account(.manageAccounts(editing: false)) } label: {
                        HStack(spacing: 8) {
                            sectionTitle(CuadraoCopy.text("copy.connectedCuadraoHome.8cce5d02a3", spanish: spanish))
                            Image(systemName: "chevron.right").font(.caption2).foregroundStyle(.secondary)
                        }.frame(minHeight: 44).contentShape(Rectangle())
                    }.buttonStyle(.plain).accessibilityIdentifier("home-accounts-open")
                    Spacer()
                    CuadraoSectionAddButton(title: CuadraoCopy.text("copy.connectedCuadraoHome.10d1d9ce3f", spanish: spanish)) { sheet = .add }
                        .accessibilityIdentifier("home-account-add")
                }
            }
            CuadraoOrderedCollection(items: data.active, spanish: spanish, spacing: 0,
                identifier: { "home-account-" + $0.id.uuidString },
                open: { accountPath.append(.account($0.id)) }, edit: { sheet = .account(.rename($0.id)) },
                archive: { data.archive($0.id, true); archivedID = $0.id }, reorder: data.reorder) { account in
                    CanvasAccountRow(account: account, spanish: spanish)
                        .overlay(alignment: .bottom) { Rectangle().fill(.separator).frame(height: 0.5).padding(.leading, 54) }
                }
            if data.active.isEmpty { firstAccount }
        }
    }

    private var firstAccount: some View {
        CuadraoHomeEmptyState(data: data, spanish: spanish,
            addAccount: { sheet = .add }, household: { sheet = .household })
    }

    private var activity: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                sectionTitle(CuadraoCopy.text("copy.accountActivityView.f7d6ac01ad", spanish: spanish))
                Spacer()
                CuadraoSectionAddButton(title: CuadraoCopy.text("copy.connectedCuadraoHome.175c809f14", spanish: spanish)) {
                    if let account = data.active.first { sheet = .account(.record(account.id)) }
                }.accessibilityIdentifier("home-activity-add")
            }
            Text(CuadraoCopy.text("copy.cuadraoChatPreview.ebdcdc2bda", spanish: spanish)).font(.footnote).foregroundStyle(.secondary)
            ForEach(data.visibleActivity.prefix(3)) { entry in
                if let account = data.account(entry.accountID) {
                    NavigationLink(value: HomeRoute.activity(entry.id)) {
                        feedRow(entry.title, detail: account.displayName(spanish),
                            amount: (entry.income ? "+" : "−") + CanvasMoney.format(entry.amount, currency: account.currency),
                            icon: entry.income ? "arrow.down.left" : "arrow.up.right")
                    }.buttonStyle(.plain).accessibilityIdentifier("home-activity.\(entry.id.uuidString)")
                }
            }
        }
    }

    private var upcoming: some View {
        CuadraoUpcomingSection(spanish: spanish, viewPlan: { selectedTab = .plan }) {
            CuadraoFeedRow(title: CuadraoCopy.text("copy.cuadraoHomeCanvas.9c5e5e5e7c", spanish: CuadraoCopy.isSpanish()), detail: CuadraoCopy.text("copy.cuadraoHomeCanvas.afa4962b0f", spanish: spanish), amount: "1,500.00", icon: "wifi")
        }
    }

    private func feedRow(_ title: String, detail: String, amount: String, icon: String) -> some View {
        CuadraoFeedRow(title: title, detail: detail, amount: amount, icon: icon)
    }

    private func sectionTitle(_ title: String) -> some View {
        Text(title).font(CuadraoTypography.section).accessibilityAddTraits(.isHeader)
    }

    private var receiptWorkspace: ReceiptWorkspace {
        ReceiptWorkspace(receipts: receipts, groups: groups, accounts: data, chat: chat,
                         capture: { receiptRoute = .capture($0, $1) }, open: { receiptRoute = .review($0) })
    }

    @ViewBuilder private func destination(_ tab: CuadraoTab, selection: Binding<CuadraoTab>) -> some View {
        if tab == .search {
            // Design-preview Search. Connected keeps FinancialSearchDestination; these results stay sample-only.
            CuadraoSearchCanvas(data: data, spanish: spanish, includeExamples: populated,
                plans: plans, groups: groups, chat: chat, openChat: { thread in chat.open(thread); searchChatOrigin = true; selectedTab = .assistant },
                actions: { sheet = .account($0) }, record: { sheet = .account(.record($0)) })
        } else if tab == .assistant {
            CuadraoChatCanvas(store: chat, spanish: spanish, editing: $chatEditing)
                .safeAreaInset(edge: .top, spacing: 0) {
                    if searchChatOrigin {
                        Button { selection.wrappedValue = .search } label: {
                            Label(CuadraoCopy.text("copy.cuadraoHomeCanvas.dc1f63d9d0", spanish: spanish), systemImage: "chevron.left")
                                .font(.subheadline).frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                        }.padding(.horizontal, 24).background(WelcomePalette.background)
                            .accessibilityIdentifier("cuadrao.search.return")
                    }
                }
        } else if tab == .profile {
            CuadraoProfileCanvas(spanish: spanish, includeExamples: populated, profile: $profile,
                path: $profilePath, bottomSpace: CuadraoAppShellMetrics.navigationHeight + 8 + (chat.voice.active ? 64 : 0))
        } else if tab == .plan && voiceProposal == nil {
            CuadraoPlanCanvas(store: plans, accounts: data, spanish: spanish,
                bottomSpace: chat.voice.active ? 160 : 90, groups: groups)
        } else if voiceProposal != nil {
            CuadraoVoiceProposalCanvas(state: $voiceProposal, spanish: spanish)
        } else {
        NavigationStack {
            ContentUnavailableView(tab.title(spanish: spanish), systemImage: tab.symbol,
                description: Text(CuadraoCopy.text("copy.cuadraoHomeCanvas.0af4c52375", spanish: spanish)))
                .background(WelcomePalette.background)
        }
        .toolbar(.hidden, for: .tabBar)
        }
    }

    @ViewBuilder private func modal(_ item: HomeSheet) -> some View {
        switch item {
        case .gallery: CuadraoDesignGallery()
        case .releaseReview:
            #if DEBUG
            ReleaseUIReview()
            #else
            EmptyView()
            #endif
        case .household: CuadraoHouseholdSheet(data: data, spanish: spanish)
        case .customize: CuadraoHomeLayoutSheet(savedOrder: $homeOrder, spanish: spanish)
        case .spaces: CuadraoSpacesSheet(data: data, spanish: spanish)
        case .add: CuadraoFirstAccountSheet(data: data, spanish: spanish)
        case .account(let selection):
            CuadraoAccountModal(data: data, selection: selection, spanish: spanish,
                show: { sheet = .account($0) }, archived: {
                    sheet = nil; accountPath = []; archivedID = $0
                })
        case .updates:
            CuadraoUpdatesCanvas(accounts: data, plans: plans, spanish: spanish,
                readIDs: $updateReadIDs, profile: $profile)
        }
    }
}

#Preview("Home · First use") { CuadraoHomeCanvas().preferredColorScheme(.light) }
