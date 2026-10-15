import SwiftUI

/// Searches the same in-memory records as Home; no second financial data owner.
struct CuadraoSearchCanvas: View {
    let data: CuadraoAccountsPreview
    let spanish: Bool
    let includeExamples: Bool
    let plans: CuadraoPlanPreview
    let groups: CuadraoGroupPreview
    let chat: CuadraoChatPreview
    let openChat: (CanvasChatThread) -> Void
    let actions: (CanvasAccountSheet) -> Void
    let record: (UUID) -> Void
    @State private var query = ""
    @State private var kind = Kind.all
    @State private var scope = Scope.all
    @State private var currency = ""
    @FocusState private var focused: Bool

    private typealias Kind = CanvasSearchKind
    /// Release rule (fc7650ea): Memory appears only with the enabled native memory feature
    /// and its controls. One first-release switch gates it in Search and Profile alike.
    private static var memoryEnabled: Bool { CuadraoFirstRelease.shows(.memory) }
    private var kinds: [Kind] { Kind.allCases.filter { $0 != .memory || Self.memoryEnabled } }
    private enum Scope: CaseIterable { case all, personal, household }
    private enum Route: Hashable { case account(UUID), activity(UUID), plan(UUID), group(UUID), reference(String) }

    private var availableAccounts: [CanvasAccount] {
        data.accounts.filter { account in
            !data.spaces.contains { $0.id == account.spaceID && $0.deleted }
            && (currency.isEmpty || account.currency == currency)
            && (scope == .all || (scope == .household ? account.sharedWithHousehold : !account.sharedWithHousehold))
        }
    }
    private var accounts: [CanvasAccount] {
        availableAccounts.filter { matches($0.displayName(spanish) + " " + subtitle($0)) }
    }
    private var activity: [CanvasActivity] {
        let availableAccounts = availableAccounts
        return data.activity.filter { entry in
            guard let account = availableAccounts.first(where: { $0.id == entry.accountID }) else { return false }
            return matches(entry.title + " " + account.displayName(spanish) + " " + subtitle(account))
        }.sorted { $0.date > $1.date }
    }
    private var references: [CanvasSearchReference] {
        guard scope != .household else { return [] }
        let examples = includeExamples ? CanvasSearchReference.examples(spanish).filter { $0.kind == .files || ($0.kind == .memory && Self.memoryEnabled) } : []
        return (examples + chat.references(spanish))
            .filter { matches($0.title + " " + $0.detail + " " + $0.content) }
    }
    private var matchingPlans: [CanvasPlan] {
        plans.plans.filter { plan in
            planIsAvailable(plan)
            && (currency.isEmpty || plan.currency == currency)
            && (scope == .all || (scope == .household ? plan.spaceID == CanvasSpace.householdID : plan.spaceID != CanvasSpace.householdID))
            && matches(plan.name + " " + plan.kind.title(spanish) + " " + PlanFormat.space(plan.spaceID, accounts: data, spanish: spanish))
        }
    }
    private var matchingGroups: [PlanGroup] {
        guard scope == .all else { return [] }
        return groups.groups.filter {
            (currency.isEmpty || $0.currency == currency)
            && matches($0.name + " " + $0.kind.title(spanish))
        }
    }
    private var availableCurrencies: [String] {
        Array(Set(data.accounts.map(\.currency) + plans.plans.map(\.currency) + groups.groups.map(\.currency))).sorted()
    }
    private func planIsAvailable(_ plan: CanvasPlan) -> Bool {
        !data.spaces.contains { $0.id == plan.spaceID && $0.deleted }
    }
    private var count: Int {
        (kind == .all || kind == .accounts ? accounts.count : 0)
        + (kind == .all || kind == .activity ? activity.count : 0)
        + references.filter { kind == .all || kind == $0.kind }.count
        + (kind == .all || kind == .plans ? matchingPlans.count + matchingGroups.count : 0)
    }
    private var start: CuadraoSearchStart {
        CuadraoSearchStart(suggestions: CuadraoSearchStart.suggestions(
            frequent: data.activity.filter { !$0.income }.map { $0.category.title(spanish) },
            names: data.accounts.filter { !$0.archived }.map { $0.displayName(spanish) }))
    }
    private var filterCount: Int { (scope == .all ? 0 : 1) + (currency.isEmpty ? 0 : 1) }

    var body: some View {
        NavigationStack {
            CuadraoSearchContent(query: $query, kind: $kind, kinds: kinds, spanish: spanish,
                filterCount: filterCount,
                filterSummary: [scope == .all ? nil : scopeTitle(scope), currency.isEmpty ? nil : currency].compactMap { $0 }.joined(separator: " · "),
                clearFilters: { scope = .all; currency = "" }, focused: $focused, start: start) {
                if count == 0 {
                    CuadraoSearchEmptyState(query: $query, kind: $kind, spanish: spanish,
                        filterCount: filterCount, clearFilters: { scope = .all; currency = "" })
                        .padding(.top, 36)
                }
                if (kind == .all || kind == .accounts) && !accounts.isEmpty {
                    CuadraoSearchHeading(title: title(.accounts), count: accounts.count)
                    ForEach(accounts) { account in
                        NavigationLink(value: Route.account(account.id)) {
                            CuadraoSearchResultRow(title: account.displayName(spanish), detail: subtitle(account), spanish: spanish, accountKind: account.kind)
                        }.buttonStyle(.plain)
                        Divider().foregroundStyle(WelcomePalette.separator)
                    }
                }
                if (kind == .all || kind == .activity) && !activity.isEmpty {
                    CuadraoSearchHeading(title: title(.activity), count: activity.count)
                    ForEach(activity) { entry in
                        if let account = data.account(entry.accountID) {
                            NavigationLink(value: Route.activity(entry.id)) {
                                CuadraoSearchResultRow(title: entry.title, detail: account.displayName(spanish) + " · " + account.currency + " "
                                    + (entry.income ? "+" : "−") + CanvasMoney.format(entry.amount, currency: account.currency),
                                    spanish: spanish, symbol: entry.income ? "arrow.down.left" : nil, category: entry.income ? nil : entry.category)
                            }.buttonStyle(.plain).accessibilityIdentifier("cuadrao.search.activity.\(entry.id)")
                            Divider().foregroundStyle(WelcomePalette.separator)
                        }
                    }
                }
                if (kind == .all || kind == .plans) && (!matchingPlans.isEmpty || !matchingGroups.isEmpty) {
                    CuadraoSearchHeading(title: title(.plans), count: matchingPlans.count + matchingGroups.count)
                    ForEach(matchingPlans) { plan in
                        NavigationLink(value: Route.plan(plan.id)) {
                            CuadraoSearchResultRow(title: plan.name, detail: [plan.kind.title(spanish),
                                PlanFormat.space(plan.spaceID, accounts: data, spanish: spanish),
                                plan.archived ? (spanish ? "Archivado" : "Archived") : nil].compactMap { $0 }.joined(separator: " · "), spanish: spanish, symbol: plan.look.symbol)
                        }.buttonStyle(.plain).accessibilityIdentifier("cuadrao.search.plan.\(plan.id)")
                        Divider()
                    }
                    ForEach(matchingGroups) { group in
                        NavigationLink(value: Route.group(group.id)) {
                            CuadraoSearchResultRow(title: group.name, detail: [group.kind.title(spanish), group.currency,
                                group.archived ? (spanish ? "Archivado" : "Archived") : nil].compactMap { $0 }.joined(separator: " · "), spanish: spanish, symbol: group.look.symbol)
                        }.buttonStyle(.plain).accessibilityIdentifier("cuadrao.search.group.\(group.id)")
                        Divider()
                    }
                }
                ForEach([Kind.chats, .files, .memory].filter { kinds.contains($0) }, id: \.self) { section in
                    let rows = references.filter { $0.kind == section }
                    if (kind == .all || kind == section) && !rows.isEmpty {
                        CuadraoSearchHeading(title: title(section), count: rows.count)
                        ForEach(rows) { item in
                            if item.kind == .chats, let thread = chat.threads.first(where: { $0.id == item.id }) {
                                Button { focused = false; openChat(thread) } label: {
                                    CuadraoSearchResultRow(title: item.title, detail: item.detail, spanish: spanish, date: thread.lastMessageDate, symbol: "bubble.left")
                                }.buttonStyle(.plain)
                            } else {
                                NavigationLink(value: Route.reference(item.id)) {
                                    CuadraoSearchResultRow(title: item.title, detail: item.detail, spanish: spanish, symbol: item.kind == .memory ? "brain" : "doc")
                                }.buttonStyle(.plain)
                            }
                            Divider()
                        }
                    }
                }
            } filters: {
                filterControls
            }
            .navigationDestination(for: Route.self) { route in
                switch route {
                case .account(let id):
                    CuadraoAccountCanvas(data: data, accountID: id, spanish: spanish, actions: actions, record: record)
                case .activity(let id):
                    CuadraoActivityDetail(data: data, activityID: id, spanish: spanish, actions: actions, record: record)
                case .plan(let id):
                    if let plan = plans.plan(id), planIsAvailable(plan) {
                        CuadraoPlanDetail(store: plans, accounts: data, planID: id, spanish: spanish)
                    } else {
                        ContentUnavailableView(spanish ? "Plan no disponible" : "Plan unavailable", systemImage: "calendar")
                            .toolbar(.visible, for: .navigationBar)
                    }
                case .group(let id):
                    if groups.group(id) != nil {
                        CuadraoGroupDetail(store: groups, groupID: id, spanish: spanish)
                    } else {
                        ContentUnavailableView(spanish ? "Plan no disponible" : "Plan unavailable", systemImage: "person.2")
                            .toolbar(.visible, for: .navigationBar)
                    }
                case .reference(let id):
                    if let item = references.first(where: { $0.id == id }) {
                        CuadraoSearchReferenceDetail(item: item, spanish: spanish,
                            source: item.kind == .memory ? CanvasSearchReference.examples(spanish).first { $0.id == "chat-cd" } : nil)
                    }
                }
            }
        }.toolbar(.hidden, for: .tabBar)
    }

    @ViewBuilder private var filterControls: some View {
        Picker(spanish ? "Incluir" : "Include", selection: $scope) {
            ForEach(Scope.allCases, id: \.self) { value in Text(scopeTitle(value)).tag(value) }
        }
        Picker(spanish ? "Moneda" : "Currency", selection: $currency) {
            Text(spanish ? "Todas" : "All").tag("")
            ForEach(availableCurrencies, id: \.self) { Text($0).tag($0) }
        }
        Section {
            Button(spanish ? "Restablecer filtros" : "Reset filters") { scope = .all; currency = "" }
        } footer: {
            Text(spanish ? "Solo yo incluye lo que no has compartido. Hogar incluye las cuentas compartidas y sus movimientos. Chats y archivos siguen siendo privados. Los planes en grupo aparecen en Todo. La moneda filtra cuentas, movimientos y planes."
                 : "Only me includes what you haven't shared. Household includes shared accounts and their activity. Chats and files remain private. Group plans appear in All. Currency filters accounts, activity and plans.")
        }
    }

    private func matches(_ text: String) -> Bool {
        let needle = query.trimmingCharacters(in: .whitespacesAndNewlines)
        return needle.isEmpty || text.range(of: needle, options: [.caseInsensitive, .diacriticInsensitive]) != nil
    }
    private func subtitle(_ account: CanvasAccount) -> String {
        let space = data.spaces.first { $0.id == account.spaceID }
        return [account.kind.title(spanish), account.currency,
                account.sharedWithHousehold ? (spanish ? "Hogar" : "Household") : space?.title(spanish),
                account.archived ? (spanish ? "Archivada" : "Archived") : nil].compactMap { $0 }.joined(separator: " · ")
    }
    private func title(_ kind: Kind) -> String { kind.title(spanish) }
    private func scopeTitle(_ scope: Scope) -> String {
        switch scope {
        case .all: spanish ? "Todo" : "All"
        case .personal: spanish ? "Solo yo" : "Only me"
        case .household: spanish ? "Hogar" : "Household"
        }
    }
}
