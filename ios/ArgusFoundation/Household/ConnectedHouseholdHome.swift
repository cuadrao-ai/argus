import SwiftUI
import ArgusSession

struct ConnectedHouseholdHome: View {
    @ObservedObject var model: HouseholdModel
    @Binding var destination: AppDestination
    var navigationScroll: CuadraoNavigationScroll?
    var showUpdates: (() -> Void)?
    @ObservedObject private var plan: HouseholdPlanModel
    @EnvironmentObject private var auth: ProfileAuthModel
    @Environment(\.locale) private var locale
    @AppStorage("cuadrao.design.home-section-order") private var homeOrder = CuadraoHomeSection.defaultOrder
    @State private var customizing = false
    @State private var currency: String?

    init(model: HouseholdModel, destination: Binding<AppDestination>,
         navigationScroll: CuadraoNavigationScroll? = nil, showUpdates: (() -> Void)? = nil) {
        self.model = model; _destination = destination; self.navigationScroll = navigationScroll
        self.showUpdates = showUpdates; plan = model.plan
    }

    private var spanish: Bool { CuadraoCopy.isSpanish() }
    private var hasContent: Bool {
        model.snapshot?.accounts.isEmpty == false || !plan.plans.isEmpty
    }
    private var upcoming: [Upcoming] {
        plan.plans.filter { !$0.archived }.flatMap { plan in
            plan.occurrences.filter { $0.status == .pending || $0.status == .partial || $0.status == .needsReview }
                .map { Upcoming(plan: plan, occurrence: $0) }
        }.sorted { $0.occurrence.date < $1.occurrence.date }
    }
    private struct Upcoming: Identifiable {
        let plan: HouseholdPlan
        let occurrence: HouseholdPlanOccurrence
        var id: UUID { occurrence.id }
    }

    var body: some View {
        Group {
            if let navigationScroll {
                home.modifier(CuadraoNavigationScrollObserver(scroll: navigationScroll,
                    enabled: !customizing && model.detail == nil && plan.openedRef == nil))
            } else { home }
        }
        .refreshable { await model.foreground() }
        .sheet(isPresented: $customizing) {
            CuadraoHomeLayoutSheet(savedOrder: $homeOrder, spanish: spanish)
                .presentationDetents([.medium, .large]).presentationDragIndicator(.visible)
        }
    }

    private var home: some View {
        CuadraoHomeLayout(order: CuadraoHomeSection.decode(homeOrder),
            canCustomize: hasContent, spanish: spanish, customize: { customizing = true }) {
            HStack {
                CuadraoHomeGreeting(name: auth.profile?.displayName ?? "", spanish: spanish)
                Spacer()
                if let showUpdates { CuadraoUpdatesButton(spanish: spanish, action: showUpdates) }
            }
            ConnectedCuadraoSpaces(model: model, destination: $destination)
            if let household = model.household {
                Button { model.showManagement = true } label: {
                    PlanAvatarStack(members: household.members.map {
                        PlanMember(id: $0.id, name: $0.displayName, symbol: "person.fill")
                    }).frame(minHeight: 44).contentShape(Rectangle())
                }.buttonStyle(.plain).accessibilityLabel("household.people")
                    .accessibilityValue(String(household.members.count))
                    .accessibilityIdentifier("household.people")
            }
        } notice: {
            ConnectedHouseholdNotice(model: model)
            if plan.state == .unavailable {
                Text(LocalizedStringKey(plan.errorKey ?? "household.loadError")).foregroundStyle(.secondary)
                Button("accounts.retry") { Task { await plan.refresh() } }.frame(minHeight: 44)
                    .accessibilityIdentifier("sharedPlan.retry")
            }
        } section: { section($0) }
    }

    @ViewBuilder private func section(_ section: CuadraoHomeSection) -> some View {
        switch section {
        case .overview:
            if let snapshot = model.snapshot, !snapshot.positions.isEmpty { overview(snapshot) }
        case .upcoming:
            if plan.state == .ready, !upcoming.isEmpty {
                CuadraoUpcomingSection(spanish: spanish, viewPlan: { destination = .plan }) {
                    ForEach(upcoming.prefix(2)) { item in
                        Button { Task { await plan.open(item.plan.ref, origin: .home) } } label: {
                            CuadraoFeedRow(title: item.plan.definition.common.name,
                                detail: item.occurrence.date + " · "
                                    + NSLocalizedString("sharedPlan.occurrence." + item.occurrence.status.rawValue, comment: ""),
                                amount: HouseholdPlanPresentation.money(item.occurrence.remainingMinor, plan: item.plan),
                                icon: "calendar")
                        }.buttonStyle(.plain).accessibilityIdentifier("sharedPlan.occurrence." + item.id.uuidString)
                    }
                }
            }
        case .accounts:
            if model.snapshot != nil { ConnectedHouseholdAccounts(model: model) }
        case .activity:
            if let snapshot = model.snapshot, !snapshot.activities.isEmpty {
                VStack(alignment: .leading, spacing: 16) {
                    Text("household.activity").font(CuadraoTypography.section)
                        .accessibilityAddTraits(.isHeader)
                    ForEach(snapshot.activities.prefix(5)) { item in
                        if let account = snapshot.accounts.first(where: { account in
                            item.activity.legs.contains { $0.accountId == account.id }
                        }) {
                            Button { Task { await model.open(account.id) } } label: {
                                ConnectedHouseholdActivityRow(item: item)
                            }.buttonStyle(.plain)
                        } else { ConnectedHouseholdActivityRow(item: item) }
                    }
                }
            }
        }
    }

    private func overview(_ snapshot: HouseholdSnapshot) -> some View {
        let positions = CurrencyPresentation.ordered(snapshot.positions, primary: auth.profile?.currency, currency: { $0.currency })
        let position = positions.first { $0.currency == currency } ?? positions[0]
        return VStack(alignment: .leading, spacing: 12) {
            Text("household.scopeNotice").font(.subheadline).foregroundStyle(.secondary)
            CuadraoBalanceAmount(
                amount: position.unknownCount > 0
                    ? NSLocalizedString("household.unknown", comment: "")
                    : AccountPresentation.amount(AccountPresentation.decimal(position.amountMinor, digits: position.currencyFractionDigits), locale: locale),
                currency: position.currency, currencies: positions.map(\.currency), spanish: spanish,
                expanded: true, amountIdentifier: "household.position." + position.currency,
                chooseCurrency: { currency = $0 }, expand: {})
            if position.unknownCount > 0 {
                (Text("household.knownSubtotal") + Text(" · " + HouseholdMoney.minor(position.amountMinor,
                    currency: position.currency, digits: position.currencyFractionDigits)))
                    .font(CuadraoTypography.supporting)
                    .accessibilityIdentifier("household.position.knownSubtotal." + position.currency)
                Text("household.unknownIncluded").font(.caption).foregroundStyle(.secondary)
            }
        }
    }
}

struct ConnectedHouseholdNotice: View {
    @ObservedObject var model: HouseholdModel
    var body: some View {
        if let error = model.errorKey {
            VStack(alignment: .leading, spacing: 8) {
                Text(LocalizedStringKey(error)).foregroundStyle(.secondary)
                    .accessibilityIdentifier("household.error")
                Button("accounts.retry") { Task { await model.refresh() } }.frame(minHeight: 44)
            }
        } else if model.snapshot == nil { ProgressView("accounts.loading") }
    }
}
