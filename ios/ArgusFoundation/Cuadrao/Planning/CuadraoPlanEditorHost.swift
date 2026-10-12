import SwiftUI

struct CuadraoPlanEditorSpace: Identifiable, Hashable {
    let id: String
    let title: String
}

struct CuadraoPlanEditorIdentifiers {
    var name = "plan-name"
    var target = "plan-target"
    var monthly = "plan-monthly"
    var rate = "plan-rate"
    var currency = "plan-edit-currency"
    var save = "plan-save"
    var kind: (CanvasPlanKind) -> String = { "plan-kind-\($0.rawValue)" }
}

/// Everything a host decides for the plan editor; the Preview store builds the default from its own data.
struct CuadraoPlanEditorHost {
    var spaces: [CuadraoPlanEditorSpace]
    var editing: Bool
    var kindLocked = false
    /// The kinds the picker offers. A host that has no debts says so here.
    var allowedKinds = CanvasPlanKind.allCases
    var currencyLocked = false
    var showsTarget = true
    var showsRecorded = true
    var showsRate = true
    var showsLook = true
    var monthlyRequired = true
    var monthlyTitle: String? = nil
    var identifiers = CuadraoPlanEditorIdentifiers()
    var canSave: (CanvasPlan) -> Bool = { _ in true }
    var saving = false
    var dismissesOnSave = true
    var save: (CanvasPlan) -> Void

    init(store: CuadraoPlanPreview, accounts: CuadraoAccountsPreview, initial: CanvasPlan, spanish: Bool, onSave: ((UUID) -> Void)?) {
        spaces = accounts.visibleSpaces.map { .init(id: $0.id, title: PlanFormat.space($0.id, accounts: accounts, spanish: spanish)) }
        editing = store.plan(initial.id) != nil
        save = { plan in store.save(plan); onSave?(plan.id) }
    }

    init(spaces: [CuadraoPlanEditorSpace], editing: Bool, save: @escaping (CanvasPlan) -> Void) {
        self.spaces = spaces; self.editing = editing; self.save = save
    }
}
