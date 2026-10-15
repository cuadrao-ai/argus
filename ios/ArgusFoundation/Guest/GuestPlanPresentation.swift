import SwiftUI
import CuadraoBook

/// How the book's plans read on screen, and how the shared plan form's values become a draft. Pure; no server model.
enum GuestPlanPresentation {
    static func kind(_ plan: BookPlan) -> CanvasPlanKind { plan.kind == .goal ? .goal : .budget }

    static func look(_ look: PlanLook) -> CanvasPlanLook {
        switch look {
        case .coast: .coast
        case .sunshine: .sunshine
        case .bloom: .bloom
        case .clay: .clay
        }
    }

    static func look(_ look: CanvasPlanLook) -> PlanLook {
        switch look {
        case .coast: .coast
        case .sunshine: .sunshine
        case .bloom: .bloom
        case .clay: .clay
        }
    }

    static func kindTitle(_ kind: PlanKind, spanish: Bool) -> String {
        switch kind {
        case .goal: spanish ? "Meta" : "Goal"
        case .budget: spanish ? "Presupuesto" : "Budget"
        }
    }

    // MARK: The shared form speaks Double; amounts cross it as exact text

    /// A decimal amount the shared form holds as a number, read back exactly. The form's own limits (15 significant digits)
    /// keep the shortest text of the number identical to what was typed.
    static func minor(_ value: Double, digits: Int) -> Int64? {
        guard value.isFinite, let decimal = Decimal(string: "\(value)") else { return nil }
        return MinorUnits.exactMinor(decimal, digits: digits)
    }

    static func text(_ value: Double, digits: Int) -> String {
        guard value != 0 else { return "" }
        return minor(value, digits: digits).map { MoneyFormatter.plain($0, digits: digits) } ?? "\(value)"
    }

    static func number(_ minor: Int64, digits: Int) -> Double {
        NSDecimalNumber(decimal: MinorUnits.decimal(minor, digits: digits)).doubleValue
    }

    static func canvas(_ plan: BookPlan) -> CanvasPlan {
        CanvasPlan(id: plan.id, name: plan.name, kind: kind(plan), spaceID: CanvasSpace.personalID, currency: plan.currency,
                   target: number(plan.targetMinor, digits: plan.digits), recorded: 0,
                   monthly: plan.monthlyMinor.map { number($0, digits: plan.digits) } ?? 0, look: look(plan.look), archived: plan.archived)
    }

    static func draft(_ canvas: CanvasPlan, accountScope: [UUID], categoryScope: [ExpenseCategory]) -> BookPlanDraft {
        let digits = CurrencyTable.digits(canvas.currency) ?? 2
        return BookPlanDraft(kind: canvas.kind == .goal ? .goal : .budget, name: canvas.name, currency: canvas.currency,
                             targetText: text(canvas.target, digits: digits), monthlyText: text(canvas.monthly, digits: digits),
                             look: look(canvas.look), accountScope: accountScope, categoryScope: categoryScope)
    }

    // MARK: Words

    static func amount(_ minor: Int64, currency: String, digits: Int, locale: Locale) -> String {
        currency + " " + MoneyFormatter.grouped(minor, digits: digits, grouping: locale.groupingSeparator ?? ",",
                                                decimal: locale.decimalSeparator ?? ".")
    }

    static func percent(_ fraction: Decimal) -> String {
        var scaled = fraction * 100
        var rounded = Decimal()
        NSDecimalRound(&rounded, &scaled, 0, .down)
        return "\(rounded)%"
    }

    static func card(_ plan: BookPlan, in book: DeviceBook, spanish: Bool, locale: Locale, now: Date = .now) -> CuadraoPlanCardDisplay {
        let space = spanish ? "Este iPhone" : "This iPhone"
        switch plan.kind {
        case .goal:
            let progress = book.goalProgress(plan.id)
            return CuadraoPlanCardDisplay(name: plan.name, space: space, look: look(plan.look),
                amount: amount(progress?.savedMinor ?? 0, currency: plan.currency, digits: plan.digits, locale: locale),
                annotation: progress.map { percent($0.fraction) }, progress: progress.map { NSDecimalNumber(decimal: $0.fraction).doubleValue },
                detail: (spanish ? "Meta: " : "Goal: ") + amount(plan.targetMinor, currency: plan.currency, digits: plan.digits, locale: locale),
                notice: progress?.reached == true ? (spanish ? "Meta alcanzada" : "Goal reached") : nil)
        case .budget:
            let status = book.budgetStatus(plan.id, now: now)
            let limit = amount(plan.targetMinor, currency: plan.currency, digits: plan.digits, locale: locale)
            return CuadraoPlanCardDisplay(name: plan.name, space: space, look: look(plan.look),
                amount: amount(status?.spentMinor ?? 0, currency: plan.currency, digits: plan.digits, locale: locale),
                annotation: status.map { percent($0.fraction) }, progress: status.map { NSDecimalNumber(decimal: $0.fraction).doubleValue },
                detail: spanish ? "de \(limit) este mes" : "of \(limit) this month",
                notice: status?.isOver == true ? (spanish ? "Superaste el límite" : "Over the limit") : nil)
        }
    }

    static func message(_ error: BookRuleError, currency: String, spanish: Bool) -> String {
        switch error {
        case .planNameEmpty: spanish ? "Añade un nombre." : "Add a name."
        case .planLimit: spanish ? "Llegaste al máximo de planes en este iPhone." : "You've reached the most plans this iPhone can hold."
        case .scopeInvalid: spanish ? "Elige solo cuentas de la moneda del plan." : "Choose only accounts in the plan's currency."
        case .planArchived: spanish ? "Un plan archivado no recibe aportes." : "An archived plan takes no contributions."
        case .planNotFound, .planKindLocked: spanish ? "No se pudo guardar. Inténtalo de nuevo." : "Couldn't save. Try again."
        default: GuestAccountPresentation.message(error, currency: currency, spanish: spanish)
        }
    }
}
