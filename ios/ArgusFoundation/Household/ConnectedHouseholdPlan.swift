import SwiftUI
import ArgusSession

struct ConnectedHouseholdPlan: View {
    @ObservedObject var model: HouseholdModel
    @ObservedObject private var plan: HouseholdPlanModel
    @State private var showingActions = false
    @Environment(\.locale) private var locale
    private var spanish: Bool { CuadraoCopy.isSpanish() }

    init(model: HouseholdModel) { self.model = model; plan = model.plan }

    var body: some View {
        CuadraoPlanPage(spanish: spanish, audience: Binding(get: { true }, set: { together in
            if !together { Task { await model.select(nil) } }
        })) {
            CuadraoPlanHeader(spanish: spanish, createTitle: NSLocalizedString("sharedPlan.create", comment: ""),
                canCreate: plan.canStart, createIdentifier: "sharedPlan.add") { showingActions = true }
        } content: {
            ConnectedHouseholdNotice(model: model)
            if let household = model.household {
                HStack(spacing: 16) {
                    Menu {
                        ForEach(model.households) { item in
                            Button(item.name ?? NSLocalizedString("household.title", comment: "")) {
                                Task { await model.select(item.id) }
                            }
                        }
                    } label: {
                        CuadraoChoiceLabel(title: household.name ?? NSLocalizedString("household.title", comment: ""),
                            selectable: model.households.count > 1)
                    }.disabled(model.households.count < 2).accessibilityIdentifier("household.selector")
                    Spacer()
                    Button { model.showManagement = true } label: {
                        PlanAvatarStack(members: household.members.map {
                            PlanMember(id: $0.id, name: $0.displayName, symbol: "person.fill")
                        }).frame(minHeight: 44)
                    }.buttonStyle(.plain).accessibilityLabel("household.people")
                        .accessibilityIdentifier("household.people")
                }
            }
            HouseholdPlanContent(model: plan, showsHeader: false)
        } footer: { EmptyView() }
        .refreshable { await model.foreground() }
        .confirmationDialog("sharedPlan.title", isPresented: $showingActions, titleVisibility: .hidden) {
            Button("sharedPlan.create") { plan.show(.create) }.accessibilityIdentifier("sharedPlan.create")
            Button("sharedPlan.share") { plan.show(.share) }.accessibilityIdentifier("sharedPlan.share")
        }
    }
}

enum ConnectedHouseholdPlanPresentation {
    static func members(_ plan: HouseholdPlan) -> [PlanMember] {
        [PlanMember(id: plan.owner.id, name: plan.owner.displayName, symbol: "person.fill")]
            + plan.participants.filter { $0.id != plan.owner.id }.map {
                PlanMember(id: $0.id, name: $0.displayName, symbol: "person.fill")
            }
    }

    static func card(_ plan: HouseholdPlan) -> CuadraoPlanCardDisplay {
        let amount: String?
        let valueLabel: String
        let targetLabel: String
        let look: CanvasPlanLook
        switch plan.progress {
        case .budget(_, _, _, let spent, _):
            amount = spent; valueLabel = "sharedPlan.spent"; targetLabel = "sharedPlan.limit"; look = .sunshine
        case .goal(let common, _, _):
            amount = HouseholdPlanPresentation.backedSavings(common)
            valueLabel = "sharedPlan.actual"; targetLabel = "sharedPlan.target"; look = .coast
        case .bill(let common):
            amount = common.appliedMinor; valueLabel = "sharedPlan.paid"; targetLabel = "sharedPlan.agreed"; look = .clay
        case .debt(let common):
            amount = common.debtBalanceMinor; valueLabel = "sharedPlan.balance"; targetLabel = "sharedPlan.agreed"; look = .bloom
        }
        return .init(name: plan.definition.common.name,
            space: NSLocalizedString("sharedPlan.kind." + plan.ref.kind.rawValue, comment: "")
                + " · " + NSLocalizedString("sharedPlan.permission." + plan.permission.rawValue, comment: ""),
            look: look, amount: HouseholdPlanPresentation.money(amount, plan: plan),
            annotation: NSLocalizedString(valueLabel, comment: ""),
            progress: progress(plan, amount: amount),
            detail: NSLocalizedString(targetLabel, comment: "") + " · "
                + HouseholdPlanPresentation.money(plan.definition.amountMinor, plan: plan),
            notice: NSLocalizedString(plan.archived ? "sharedPlan.archived"
                : "sharedPlan.state." + plan.progress.common.state.rawValue, comment: ""))
    }

    private static func progress(_ plan: HouseholdPlan, amount: String?) -> Double? {
        guard plan.ref.kind == .budget || plan.ref.kind == .goal,
              plan.progress.common.state != .unknown, plan.progress.common.state != .needsReview,
              let amount, let value = Double(amount), let target = Double(plan.definition.amountMinor),
              value.isFinite, target.isFinite, value >= 0, target > 0 else { return nil }
        return min(1, value / target)
    }
}
