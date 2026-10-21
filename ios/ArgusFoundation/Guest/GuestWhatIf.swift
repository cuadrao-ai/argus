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
                    Text(plan.kind == .goal ? (CuadraoCopy.text("copy.cuadraoPlanEditor.90ae4ff82c", spanish: spanish)) : (CuadraoCopy.text("copy.cuadraoPlanWhatIf.8d5b7791b3", spanish: spanish))).font(.subheadline)
                    Spacer()
                    Text(money(chosenMinor)).font(CuadraoTypography.rowAmount).accessibilityIdentifier("guest.whatif.amount")
                }
                Slider(value: Binding(get: { chosenUnits }, set: { units = $0; status = nil }), in: 1...ceiling, step: 1)
                    .tint(GuestPlanPresentation.look(plan.look).color)
                    .accessibilityLabel(CuadraoCopy.text("copy.cuadraoPlanWhatIf.154fa94cbb", spanish: spanish))
                    .accessibilityIdentifier("guest.whatif.slider")
            }.padding(16).background(GuestPlanPresentation.look(plan.look).color.opacity(0.065), in: RoundedRectangle(cornerRadius: 24))
            if plan.kind == .goal, let remaining = model.book.goalProgress(plan.id)?.remainingMinor, remaining > 0 {
                ScrollView(.horizontal) {
                    HStack(spacing: 8) {
                        ForEach([3, 6, 12], id: \.self) { months in
                            Button { choose(PlanCalculator.monthlyNeeded(remainingMinor: remaining, months: months)) } label: {
                                Text(CuadraoCopy.text("copy.cuadraoPlanWhatIf.2e5a9e4729", spanish: spanish, String(describing: months)))
                                    .font(.caption).padding(.horizontal, 14).frame(minHeight: 44)
                                    .background(WelcomePalette.surface, in: Capsule())
                            }.accessibilityIdentifier("guest.whatif.in\(months)")
                        }
                    }
                }.scrollIndicators(.hidden)
            }
            if changed {
                PlanPrimaryButton(title: CuadraoCopy.text("copy.cuadraoPlanWhatIf.a6debfe200", spanish: spanish), action: apply)
                    .accessibilityIdentifier("guest.whatif.apply")
                Button(CuadraoCopy.text("copy.cuadraoPlanWhatIf.1acfa48fa0", spanish: spanish)) { units = nil; status = nil }
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
            Text(remaining == 0 ? (CuadraoCopy.text("copy.cuadraoPlanEditor.3fd01b458f", spanish: spanish))
                 : (CuadraoCopy.text("copy.cuadraoPlanWhatIf.ea444e4450", spanish: spanish))).font(CuadraoTypography.section)
            if remaining > 0 {
                Text(months.flatMap { arrival($0) } ?? (CuadraoCopy.text("copy.cuadraoPlanWhatIf.bf08094eee", spanish: spanish)))
                    .font(.system(.title, design: .rounded)).foregroundStyle(GuestPlanPresentation.look(plan.look).color)
                    .accessibilityIdentifier("guest.whatif.estimate")
                if changed, let original = PlanCalculator.monthsToGoal(remainingMinor: remaining, monthlyMinor: baselineMinor), let proposed = months, original != proposed {
                    Text(CuadraoCopy.text("copy.guestWhatIf.b20a7805a6", spanish: spanish, String(describing: abs(original - proposed)), String(describing: ((proposed < original ? CuadraoCopy.text("copy.guestWhatIf.a72a71b9cb", spanish: spanish) : CuadraoCopy.text("copy.guestWhatIf.497dfb6c3d", spanish: spanish))))))
                        .font(.subheadline.weight(.medium)).foregroundStyle(GuestPlanPresentation.look(plan.look).color)
                        .accessibilityIdentifier("guest.whatif.difference")
                }
            }
        }
    }

    @ViewBuilder private var budgetReading: some View {
        let status = model.book.budgetStatus(plan.id, now: .now)
        VStack(alignment: .leading, spacing: 6) {
            Text(CuadraoCopy.text("copy.cuadraoPlanWhatIf.92ed11541e", spanish: spanish)).font(CuadraoTypography.section)
            if let status, let pace = PlanCalculator.monthEndPace(spentMinor: status.spentMinor, elapsedDays: status.elapsedDays, totalDays: status.totalDays) {
                Text(CuadraoCopy.text("copy.cuadraoPlanWhatIf.e805e50e8c", spanish: spanish, String(describing: money(pace))))
                    .font(.subheadline).foregroundStyle(.secondary).accessibilityIdentifier("guest.whatif.pace")
                Text(pace <= chosenMinor ? (CuadraoCopy.text("copy.guestWhatIf.5140c62b10", spanish: spanish))
                     : (CuadraoCopy.text("copy.guestWhatIf.329c54a416", spanish: spanish, String(describing: money(pace - chosenMinor)))))
                    .font(.subheadline.weight(.medium)).foregroundStyle(pace <= chosenMinor ? GuestPlanPresentation.look(plan.look).color : WelcomePalette.owedNegative)
                    .accessibilityIdentifier("guest.whatif.verdict")
            }
        }
    }

    private var disclosure: String {
        if plan.kind == .budget, let status = model.book.budgetStatus(plan.id, now: .now) {
            let elapsed = status.elapsedDays, total = status.totalDays
            return CuadraoCopy.text("copy.guestWhatIf.c0ab2032ba", spanish: spanish, String(describing: elapsed), String(describing: ((elapsed == 1 ? CuadraoCopy.text("copy.guestWhatIf.a965f93e10", spanish: spanish) : CuadraoCopy.text("copy.guestWhatIf.1cca1d7c78", spanish: spanish)))), String(describing: total))
        }
        return CuadraoCopy.text("copy.guestWhatIf.a8d1ccae94", spanish: spanish)
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
