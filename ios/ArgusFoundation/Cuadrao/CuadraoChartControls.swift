import SwiftUI

struct CuadraoChartViewChoice: View {
    @Binding var distribution: Bool
    let spanish: Bool
    var activity = false
    var distributionEnabled = true
    var body: some View {
        HStack(spacing: 0) {
            option(false)
            option(true)
        }.padding(3).background(WelcomePalette.surface, in: Capsule())
            .fixedSize()
    }
    private func option(_ breakdown: Bool) -> some View {
        Button { distribution = breakdown } label: {
            Group {
                if breakdown {
                    HStack(spacing: 2) {
                        RoundedRectangle(cornerRadius: 1).frame(width: 9)
                        RoundedRectangle(cornerRadius: 1).frame(width: 5)
                        RoundedRectangle(cornerRadius: 1).frame(width: 3)
                    }.frame(height: 15)
                } else { Image(systemName: activity ? "chart.bar.xaxis" : "chart.xyaxis.line").font(.system(size: 18, weight: .medium)) }
            }.foregroundStyle(distribution == breakdown ? WelcomePalette.pine : WelcomePalette.ink.opacity(0.45))
                .frame(width: 44, height: 44)
                .background(distribution == breakdown ? WelcomePalette.sage : .clear, in: Circle())
                .contentShape(Rectangle())
                .opacity(breakdown && !distributionEnabled ? 0.35 : 1)
        }.buttonStyle(.plain).disabled(breakdown && !distributionEnabled)
            .accessibilityLabel(breakdown ? (CuadraoCopy.text("copy.cuadraoChartControls.63521b1f42", spanish: spanish)) : (CuadraoCopy.text("copy.cuadraoChartControls.309e2bc554", spanish: spanish)))
            .accessibilityAddTraits(distribution == breakdown ? .isSelected : [])
            .accessibilityIdentifier(breakdown ? "home-view-distribution" : "home-view-history")
    }
}

struct CuadraoHistoryPeriodChoice: View {
    @Binding var range: CanvasHistoryRange
    let spanish: Bool
    var body: some View {
        ViewThatFits(in: .horizontal) {
            HStack(spacing: 2) { options }.fixedSize(horizontal: true, vertical: false)
            VStack(alignment: .leading, spacing: 2) { options }
        }.padding(3).background(WelcomePalette.surface, in: RoundedRectangle(cornerRadius: 24))
    }
    private var options: some View {
        ForEach(CanvasHistoryRange.allCases) { option in
            Button { range = option } label: {
                Text(option.title(spanish)).font(CuadraoTypography.supporting)
                    .padding(.horizontal, 8).frame(minWidth: 44, minHeight: 44)
                    .background(range == option ? WelcomePalette.sage : .clear, in: Capsule())
                    .contentShape(Rectangle())
            }.buttonStyle(.plain).accessibilityAddTraits(range == option ? .isSelected : [])
                .accessibilityIdentifier("home-period-" + option.rawValue)
        }
    }
}

struct CuadraoInsightControls: View {
    @Binding var range: CanvasHistoryRange
    @Binding var distribution: Bool
    let spanish: Bool
    var activity = false
    var distributionEnabled = true
    var body: some View {
        ViewThatFits(in: .horizontal) {
            HStack(spacing: 8) { periods; Spacer(minLength: 0); views }
            VStack(alignment: .leading, spacing: 8) { periods; views }
        }
    }
    private var periods: some View { CuadraoHistoryPeriodChoice(range: $range, spanish: spanish) }
    private var views: some View {
        CuadraoChartViewChoice(distribution: $distribution, spanish: spanish, activity: activity, distributionEnabled: distributionEnabled)
    }
}
