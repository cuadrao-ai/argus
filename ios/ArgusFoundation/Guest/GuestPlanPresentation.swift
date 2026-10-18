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
        case .goal: CuadraoCopy.text("copy.cuadraoVoiceProposalCanvas.a666a311f9", spanish: spanish)
        case .budget: CuadraoCopy.text("copy.guestPlanPresentation.179041c8c6", spanish: spanish)
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
        let space = CuadraoCopy.text("copy.guestAccountSheet.736ea2040f", spanish: spanish)
        switch plan.kind {
        case .goal:
            let progress = book.goalProgress(plan.id)
            return CuadraoPlanCardDisplay(name: plan.name, space: space, look: look(plan.look),
                amount: amount(progress?.savedMinor ?? 0, currency: plan.currency, digits: plan.digits, locale: locale),
                annotation: progress.map { percent($0.fraction) }, progress: progress.map { NSDecimalNumber(decimal: $0.fraction).doubleValue },
                detail: (CuadraoCopy.text("copy.guestPlanPresentation.c9b6dd837a", spanish: spanish)) + amount(plan.targetMinor, currency: plan.currency, digits: plan.digits, locale: locale),
                notice: progress?.reached == true ? (CuadraoCopy.text("copy.guestPlanPresentation.a9ce4da8c3", spanish: spanish)) : nil)
        case .budget:
            let status = book.budgetStatus(plan.id, now: now)
            let limit = amount(plan.targetMinor, currency: plan.currency, digits: plan.digits, locale: locale)
            return CuadraoPlanCardDisplay(name: plan.name, space: space, look: look(plan.look),
                amount: amount(status?.spentMinor ?? 0, currency: plan.currency, digits: plan.digits, locale: locale),
                annotation: status.map { percent($0.fraction) }, progress: status.map { NSDecimalNumber(decimal: $0.fraction).doubleValue },
                detail: CuadraoCopy.text("copy.cuadraoPlanVisuals.d16b6c2fa4", spanish: spanish, String(describing: limit)),
                notice: status?.isOver == true ? (CuadraoCopy.text("copy.guestPlanPresentation.3da1e7fc89", spanish: spanish)) : nil)
        }
    }

    static func message(_ error: BookRuleError, currency: String, spanish: Bool) -> String {
        switch error {
        case .planNameEmpty: CuadraoCopy.text("copy.guestPlanPresentation.25ace280cf", spanish: spanish)
        case .planLimit: CuadraoCopy.text("copy.guestPlanPresentation.08f175d13d", spanish: spanish)
        case .scopeInvalid: CuadraoCopy.text("copy.guestPlanPresentation.18f383d5eb", spanish: spanish)
        case .planArchived: CuadraoCopy.text("copy.guestPlanPresentation.a1ac916101", spanish: spanish)
        case .planNotFound, .planKindLocked: CuadraoCopy.text("copy.guestAccountPresentation.c7aaa1eb33", spanish: spanish)
        default: GuestAccountPresentation.message(error, currency: currency, spanish: spanish)
        }
    }
}
