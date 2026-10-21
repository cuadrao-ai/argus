import SwiftUI
import CuadraoBook

/// Try another monthly amount on a goal, or another limit on a budget, without changing anything. Every number comes from the
/// package's `PlanCalculator`; the slider only chooses a whole amount. Applying it is the plan's own edit.
struct GuestWhatIf: View {
    @ObservedObject var model: GuestBookModel
    let plan: BookPlan
    let spanish: Bool
    @State private var units: Double?
    @State private var status: String?
    @Environment(\.locale) private var locale

    private var scale: Decimal { Decimal(sign: .plus, exponent: plan.digits, significand: 1) }
    private var baselineMinor: Int64 { plan.kind == .goal ? (plan.monthlyMinor ?? 0) : plan.targetMinor }
    /// Whole units of the currency, which is what the slider moves in.
    private var baselineUnits: Double { NSDecimalNumber(decimal: MinorUnits.decimal(baselineMinor, digits: plan.digits).roundedToUnit()).doubleValue }
    private var chosenUnits: Double { units ?? max(1, baselineUnits) }
    private var chosenMinor: Int64 {
        guard let units else { return baselineMinor }
        return MinorUnits.exactMinor(Decimal(Int(units.rounded())), digits: plan.digits) ?? baselineMinor
    }
    private var changed: Bool { chosenMinor != baselineMinor }
    private var ceiling: Double { max(1_000, baselineUnits * 3) }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            if plan.kind == .goal { goalReading } else { budgetReading }
            VStack(spacing: 6) {
                HStack {
                    Text(plan.kind == .goal ? (spanish ? "Cada mes" : "Each month") : (spanish ? "Mi margen" : "My allowance")).font(.subheadline)
                    Spacer()
                    Text(money(chosenMinor)).font(CuadraoTypography.rowAmount).accessibilityIdentifier("guest.whatif.amount")
                }
                Slider(value: Binding(get: { chosenUnits }, set: { units = $0; status = nil }), in: 1...ceiling, step: 1)
                    .tint(GuestPlanPresentation.look(plan.look).color)
                    .accessibilityLabel(spanish ? "Probar otro monto" : "Try another amount")
                    .accessibilityIdentifier("guest.whatif.slider")
            }.padding(16).background(GuestPlanPresentation.look(plan.look).color.opacity(0.065), in: RoundedRectangle(cornerRadius: 24))
            if plan.kind == .goal, let remaining = model.book.goalProgress(plan.id)?.remainingMinor, remaining > 0 {
                ScrollView(.horizontal) {
                    HStack(spacing: 8) {
                        ForEach([3, 6, 12], id: \.self) { months in
                            Button { choose(PlanCalculator.monthlyNeeded(remainingMinor: remaining, months: months)) } label: {
                                Text(spanish ? "Llegar en \(months) meses" : "Get there in \(months) months")
                                    .font(.caption).padding(.horizontal, 14).frame(minHeight: 44)
                                    .background(WelcomePalette.surface, in: Capsule())
                            }.accessibilityIdentifier("guest.whatif.in\(months)")
                        }
                    }
                }.scrollIndicators(.hidden)
            }
            if changed {
                PlanPrimaryButton(title: spanish ? "Aplicar a mi plan" : "Apply to my plan", action: apply)
                    .accessibilityIdentifier("guest.whatif.apply")
                Button(spanish ? "Deshacer prueba" : "Reset experiment") { units = nil; status = nil }
                    .font(.subheadline).frame(maxWidth: .infinity, minHeight: 44).accessibilityIdentifier("guest.whatif.reset")
            }
            if let status { Text(status).font(.subheadline).foregroundStyle(.red).accessibilityIdentifier("guest.whatif.error") }
            Text(disclosure).font(.caption).foregroundStyle(.secondary).accessibilityIdentifier("guest.whatif.disclosure")
        }.accessibilityElement(children: .contain).accessibilityIdentifier("guest.whatif")
    }

    // MARK: Readings

    @ViewBuilder private var goalReading: some View {
        let remaining = model.book.goalProgress(plan.id)?.remainingMinor ?? plan.targetMinor
        let months = PlanCalculator.monthsToGoal(remainingMinor: remaining, monthlyMinor: chosenMinor)
        VStack(alignment: .leading, spacing: 6) {
            Text(remaining == 0 ? (spanish ? "Ya llegaste." : "You're there.")
                 : (spanish ? "A tu ritmo, llegarías en" : "At your pace, you would arrive in")).font(CuadraoTypography.section)
            if remaining > 0 {
                Text(months.flatMap { arrival($0) } ?? (spanish ? "Este aporte no alcanza para llegar." : "This amount won't get you there."))
                    .font(.system(.title, design: .rounded)).foregroundStyle(GuestPlanPresentation.look(plan.look).color)
                    .accessibilityIdentifier("guest.whatif.estimate")
                if changed, let original = PlanCalculator.monthsToGoal(remainingMinor: remaining, monthlyMinor: baselineMinor), let proposed = months, original != proposed {
                    Text(spanish ? "\(abs(original - proposed)) meses \(proposed < original ? "antes" : "después")"
                         : "\(abs(original - proposed)) months \(proposed < original ? "earlier" : "later")")
                        .font(.subheadline.weight(.medium)).foregroundStyle(GuestPlanPresentation.look(plan.look).color)
                        .accessibilityIdentifier("guest.whatif.difference")
                }
            }
        }
    }

    @ViewBuilder private var budgetReading: some View {
        let status = model.book.budgetStatus(plan.id, now: .now)
        VStack(alignment: .leading, spacing: 6) {
            Text(spanish ? "Dale aire a tu mes." : "Give your month some room.").font(CuadraoTypography.section)
            if let status, let pace = PlanCalculator.monthEndPace(spentMinor: status.spentMinor, elapsedDays: status.elapsedDays, totalDays: status.totalDays) {
                Text(spanish ? "A este ritmo: \(money(pace)) al cierre. El margen no cambia el gasto previsto."
                     : "At this pace: \(money(pace)) at month end. The allowance doesn't change projected spending.")
                    .font(.subheadline).foregroundStyle(.secondary).accessibilityIdentifier("guest.whatif.pace")
                Text(pace <= chosenMinor ? (spanish ? "Con este margen, llegas." : "With this allowance, you'd make it.")
                     : (spanish ? "Con este margen, te pasarías por \(money(pace - chosenMinor))." : "With this allowance, you'd go over by \(money(pace - chosenMinor))."))
                    .font(.subheadline.weight(.medium)).foregroundStyle(pace <= chosenMinor ? GuestPlanPresentation.look(plan.look).color : WelcomePalette.owedNegative)
                    .accessibilityIdentifier("guest.whatif.verdict")
            }
        }
    }

    private var disclosure: String {
        if plan.kind == .budget, let status = model.book.budgetStatus(plan.id, now: .now) {
            let elapsed = status.elapsedDays, total = status.totalDays
            return spanish
                ? "Proyección simple con \(elapsed) \(elapsed == 1 ? "día registrado" : "días registrados") de un mes de \(total) días. No es un gasto confirmado."
                : "Simple projection using \(elapsed) recorded \(elapsed == 1 ? "day" : "days") in a \(total)-day month. This is not confirmed spending."
        }
        return spanish
            ? "Supuestos: aportes mensuales constantes, sin rendimientos, compras nuevas ni comisiones. El plan no mueve dinero."
            : "Assumptions: fixed monthly contributions, no returns, new purchases or fees. The plan doesn't move money."
    }

    // MARK: Actions

    private func arrival(_ months: Int) -> String? {
        guard let date = PlanCalculator.completionMonth(after: months, from: .now, zone: TimeZone(identifier: plan.timeZone) ?? .current) else { return nil }
        let text = date.formatted(.dateTime.month(.wide).year().locale(locale))
        return text.prefix(1).uppercased() + text.dropFirst()
    }

    private func money(_ minor: Int64) -> String {
        GuestPlanPresentation.amount(minor, currency: plan.currency, digits: plan.digits, locale: locale)
    }

    private func choose(_ minor: Int64?) {
        guard let minor else { return }
        units = NSDecimalNumber(decimal: MinorUnits.decimal(minor, digits: plan.digits).roundedToUnit(.up)).doubleValue
        status = nil
    }

    private func apply() {
        var draft = BookPlanDraft(kind: plan.kind, name: plan.name, currency: plan.currency,
                                  targetText: MoneyFormatter.plain(plan.targetMinor, digits: plan.digits),
                                  monthlyText: MoneyFormatter.plain(plan.monthlyMinor ?? 0, digits: plan.digits),
                                  look: plan.look, accountScope: plan.accountScope, categoryScope: plan.categoryScope)
        if plan.kind == .goal { draft.monthlyText = MoneyFormatter.plain(chosenMinor, digits: plan.digits) }
        else { draft.targetText = MoneyFormatter.plain(chosenMinor, digits: plan.digits) }
        do {
            try model.apply { try $0.editingPlan(plan.id, with: draft) }
            units = nil
        } catch let error as BookRuleError {
            status = GuestPlanPresentation.message(error, currency: plan.currency, spanish: spanish)
        } catch {}
    }
}

private extension Decimal {
    /// The nearest whole unit down (or up), kept exact.
    func roundedToUnit(_ mode: NSDecimalNumber.RoundingMode = .down) -> Decimal {
        var source = self
        var result = Decimal()
        NSDecimalRound(&result, &source, 0, mode)
        return result
    }
}
