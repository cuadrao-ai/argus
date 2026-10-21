import SwiftUI

struct CuadraoSpendingHighlights: View {
    let story: CanvasSpendingStory
    let currency: String
    let spanish: Bool
    private func featuredInsights(_ insights: [CanvasSpendingInsight]) -> [CanvasSpendingInsight] {
        let trend = insights.first { $0.kind == .trend }
        let average = insights.first { $0.kind == .average && $0.category == nil }
        return [trend, average].compactMap { $0 }
    }
    private func hasMore(_ insights: [CanvasSpendingInsight], featured: [CanvasSpendingInsight]) -> Bool {
        let available = insights.count + (story.changedCategory == nil ? 0 : 1) + (story.largestExpense == nil ? 0 : 1)
        let shown = featured.count + (featured.count < 2 && story.changedCategory != nil ? 1 : 0)
        return available > shown
    }
    var body: some View {
        // The story's months are walked once per pass; every reader below shares them.
        let insights = story.longitudinalInsights
        let featured = featuredInsights(insights)
        if !insights.isEmpty || story.changedCategory != nil {
            VStack(alignment: .leading, spacing: 16) {
                HStack {
                    Text(CuadraoCopy.text("copy.cuadraoSpendingHighlights.2bffd6a112", spanish: spanish)).font(CuadraoTypography.section)
                    Spacer()
                    if hasMore(insights, featured: featured) {
                        NavigationLink(CuadraoCopy.text("copy.cuadraoSpendingHighlights.e37e717885", spanish: spanish)) { allHighlights(insights) }
                            .font(CuadraoTypography.supporting).frame(minHeight: 44)
                            .accessibilityIdentifier("home-highlights-all")
                    }
                }
                ForEach(featured) { insight in
                    CuadraoSpendingTrendCard(insight: insight, story: story, currency: currency, spanish: spanish)
                }
                if featured.count < 2, let category = story.changedCategory { comparisonCard(category) }
            }.padding(.top, 12)
        }
    }
    private func allHighlights(_ insights: [CanvasSpendingInsight]) -> some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 20) {
                Text(CuadraoCopy.text("copy.cuadraoSpendingHighlights.e21847e80d", spanish: spanish)).font(CuadraoTypography.feature)
                ForEach(insights.filter { $0.category == nil }) { insight in
                    CuadraoSpendingTrendCard(insight: insight, story: story, currency: currency, spanish: spanish)
                }
                Text(CuadraoCopy.text("copy.cuadraoSpendingHighlights.c530befaf7", spanish: spanish)).font(CuadraoTypography.feature)
                if let category = story.changedCategory { comparisonCard(category) }
                ForEach(insights.filter { $0.category != nil }) { insight in
                    CuadraoSpendingTrendCard(insight: insight, story: story, currency: currency, spanish: spanish)
                }
                if let expense = story.largestExpense {
                    Text(CuadraoCopy.text("copy.cuadraoSpendingHighlights.a16f5c284d", spanish: spanish)).font(CuadraoTypography.feature)
                    largestCard(expense)
                }
            }.padding(24)
        }.background(WelcomePalette.background).navigationTitle(CuadraoCopy.text("copy.cuadraoSpendingHighlights.2bffd6a112", spanish: spanish))
            .navigationBarTitleDisplayMode(.inline).accessibilityIdentifier("home-all-highlights")
    }
    private func money(_ amount: Decimal) -> String { currency + " " + CanvasMoney.format(amount, currency: currency) }
    private func header(_ category: CanvasExpenseCategory, title: String) -> some View {
        HStack(spacing: 12) {
            CuadraoExpenseCategoryIcon(category: category)
            Text(title).font(CuadraoTypography.supporting).foregroundStyle(category.color)
            Spacer(minLength: 4)
            Image(systemName: "chevron.right").font(.caption.weight(.semibold)).foregroundStyle(.secondary)
        }
    }
    private func comparisonCard(_ category: CanvasExpenseCategory) -> some View {
        let current = story.total(for: category)
        let previous = story.total(for: category, previous: true)
        let difference = current - previous
        let reference = story.offset == 0
            ? (CuadraoCopy.text("copy.cuadraoSpendingChart.8aef524835", spanish: spanish))
            : (CuadraoCopy.text("copy.cuadraoSpendingChart.75aecad63d", spanish: spanish))
        return NavigationLink {
            CuadraoSpendingEvidence(story: story, category: category, expenseID: nil, currency: currency, spanish: spanish)
        } label: {
            VStack(alignment: .leading, spacing: 16) {
                header(category, title: category.title(spanish))
                Text(CuadraoCopy.text("copy.cuadraoSpendingHighlights.a53c8aaf01", spanish: spanish, String(describing: money(abs(difference))), String(describing: ((difference > 0 ? CuadraoCopy.text("copy.cuadraoSpendingHighlights.14178c1062", spanish: spanish) : CuadraoCopy.text("copy.cuadraoSpendingHighlights.d08611ffa1", spanish: spanish)))), String(describing: (spanish ? (category.title(true).lowercased()) : (category.title(false).lowercased()))), String(describing: reference)))
                    .font(CuadraoTypography.body).fixedSize(horizontal: false, vertical: true)
                comparisonBar(current, ceiling: max(current, previous), title: story.periodText(story.observedInterval, spanish: spanish), color: category.color)
                if let interval = story.comparison {
                    comparisonBar(previous, ceiling: max(current, previous), title: story.periodText(interval, spanish: spanish), color: WelcomePalette.ink.opacity(0.22))
                }
            }.padding(20).frame(maxWidth: .infinity, alignment: .leading)
                .background(WelcomePalette.surface, in: RoundedRectangle(cornerRadius: 24))
                .contentShape(RoundedRectangle(cornerRadius: 24))
        }.buttonStyle(.plain).accessibilityIdentifier("home-highlight-comparison")
    }
    private func comparisonBar(_ amount: Decimal, ceiling: Decimal, title: String, color: Color) -> some View {
        VStack(alignment: .leading, spacing: 7) {
            Text(money(amount)).font(CuadraoTypography.rowAmount).fixedSize(horizontal: false, vertical: true)
            GeometryReader { geometry in
                Capsule().fill(color).frame(width: geometry.size.width * fraction(amount, of: ceiling))
            }.frame(height: 12).accessibilityHidden(true)
            Text(title).font(CuadraoTypography.caption).foregroundStyle(.secondary)
        }
    }
    private func largestCard(_ expense: CanvasActivity) -> some View {
        NavigationLink {
            CuadraoSpendingEvidence(story: story, category: expense.category, expenseID: expense.id, currency: currency, spanish: spanish)
        } label: {
            VStack(alignment: .leading, spacing: 16) {
                header(expense.category, title: CuadraoCopy.text("copy.cuadraoSpendingHighlights.f373f4f30a", spanish: spanish))
                VStack(alignment: .leading, spacing: 6) {
                    Text(expense.title).font(CuadraoTypography.body)
                    Text(money(expense.amount)).font(CuadraoTypography.secondaryAmount).fixedSize(horizontal: false, vertical: true)
                }
                Text(CuadraoCopy.text("copy.cuadraoSpendingHighlights.1fcbbd1412", spanish: spanish, String(describing: share(expense.amount))))
                    .font(CuadraoTypography.supporting).fixedSize(horizontal: false, vertical: true)
                GeometryReader { geometry in
                    Capsule().fill(WelcomePalette.ink.opacity(0.08))
                    Capsule().fill(expense.category.color).frame(width: geometry.size.width * fraction(expense.amount, of: story.total))
                }.frame(height: 12).accessibilityHidden(true)
            }.padding(20).frame(maxWidth: .infinity, alignment: .leading)
                .background(WelcomePalette.surface, in: RoundedRectangle(cornerRadius: 24))
                .contentShape(RoundedRectangle(cornerRadius: 24))
        }.buttonStyle(.plain).accessibilityIdentifier("home-highlight-largest")
    }
    private func fraction(_ amount: Decimal, of total: Decimal) -> Double {
        total > 0 ? min(1, max(0, NSDecimalNumber(decimal: amount / total).doubleValue)) : 0
    }
    private func share(_ amount: Decimal) -> String {
        fraction(amount, of: story.total).formatted(.percent.precision(.fractionLength(0)).locale(Locale(identifier: CuadraoCopy.text("copy.receiptJourneySheet.57139f7c9f", spanish: spanish))))
    }
}

private struct CuadraoSpendingEvidence: View {
    let story: CanvasSpendingStory
    let category: CanvasExpenseCategory
    let expenseID: UUID?
    let currency: String
    let spanish: Bool
    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 20) {
                records(story.entries, interval: story.observedInterval)
                if expenseID == nil, let prior = story.previousEntries, let interval = story.comparison {
                    records(prior, interval: interval)
                }
            }.padding(24)
        }.background(WelcomePalette.background).foregroundStyle(WelcomePalette.ink)
            .navigationTitle(category.title(spanish)).navigationBarTitleDisplayMode(.inline)
            .accessibilityIdentifier("home-highlight-records")
    }
    private func records(_ entries: [CanvasActivity], interval: DateInterval) -> some View {
        let matching = entries.filter { $0.category == category && (expenseID == nil || $0.id == expenseID) }.sorted { $0.date > $1.date }
        return VStack(alignment: .leading, spacing: 16) {
            Text(story.periodText(interval, spanish: spanish)).font(CuadraoTypography.feature)
            if matching.isEmpty {
                Text(CuadraoCopy.text("copy.cuadraoSpendingHighlights.ae1f889e38", spanish: spanish)).font(CuadraoTypography.supporting).foregroundStyle(.secondary)
            }
            ForEach(matching) { entry in
                VStack(alignment: .leading, spacing: 8) {
                    Text(entry.title).font(CuadraoTypography.body)
                    Text(currency + " " + CanvasMoney.format(entry.amount, currency: currency)).font(CuadraoTypography.rowAmount)
                    Text(entry.date, format: .dateTime.day().month(.abbreviated).year().locale(Locale(identifier: CuadraoCopy.text("copy.receiptJourneySheet.57139f7c9f", spanish: spanish))))
                        .font(CuadraoTypography.caption).foregroundStyle(.secondary)
                }.frame(maxWidth: .infinity, alignment: .leading).padding(.vertical, 8)
            }
        }
    }
}
