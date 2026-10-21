import SwiftUI
import ArgusSession

struct FinancialComingUpView: View {
    @ObservedObject var model: FinancialPlanModel
    let viewPlan: () -> Void
    @State private var expanded = false
    @Environment(\.locale) private var locale
    private var spanish: Bool { CuadraoCopy.isSpanish() }
    private static let compactCount = 4

    var body: some View {
        CuadraoUpcomingSection(spanish: spanish, viewPlan: viewPlan) {
            if let projection = model.homeProjection {
                let planned = projection.occurrences.filter { $0.status != .fulfilled }
                let mixedCurrencies = Set(planned.map(\.currency)).count > 1
                ForEach(Array(planned.prefix(expanded ? planned.count : Self.compactCount))) { occurrence in
                    let row = PlanPresentation.upcomingRow(occurrence, locale: locale, showsCurrency: mixedCurrencies)
                    Button { Task { await model.open(occurrence) } } label: {
                        VStack(alignment: .leading, spacing: 5) {
                            CuadraoFeedRow(title: row.title, detail: row.detail, amount: row.amount, icon: row.icon)
                            if occurrence.overdue { Text("plan.overdue").font(.caption).foregroundStyle(WelcomePalette.owedNegative) }
                        }.accessibilityElement(children: .combine)
                    }.buttonStyle(.plain).disabled(model.saving).accessibilityIdentifier("home.upcoming." + occurrence.id)
                }
                if planned.count > Self.compactCount {
                    Button(expanded ? "plan.showLess" : "plan.showMore") { expanded.toggle() }
                        .frame(minHeight: 44).accessibilityIdentifier("home.upcoming.more")
                }
                if planned.isEmpty {
                    Text(CuadraoCopy.text("copy.financialComingUpView.078d369754", spanish: spanish))
                        .font(CuadraoTypography.supporting).foregroundStyle(.secondary)
                }
            } else if model.loading { ProgressView("accounts.loading") }
            else if let error = model.homeErrorKey {
                Text(LocalizedStringKey(error)).foregroundStyle(.secondary)
                Button("accounts.retry") { Task { await model.refresh() } }.frame(minHeight: 44)
            }
        }
    }
}
