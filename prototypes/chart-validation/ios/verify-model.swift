import Foundation

@main
struct VerifyModel {
    static func main() throws {
        let root = URL(fileURLWithPath: CommandLine.arguments[1])
        let fixtures = try JSONDecoder().decode(FixtureBundle.self, from: Data(contentsOf: root))
        let stress = fixtures.cases.first { $0.id == "stress" }!
        let plot = PlotData(stress)
        precondition(plot.nearest(plot.dates[0].addingTimeInterval(-86400)) == 0)
        precondition(plot.nearest(plot.dates.last!.addingTimeInterval(86400)) == plot.dates.count - 1)
        let midpoint = plot.dates[0].addingTimeInterval(plot.dates[1].timeIntervalSince(plot.dates[0]) / 2)
        precondition(plot.nearest(midpoint) == 0, "Ties select earlier")
        for (index, point) in stress.points.enumerated() {
            precondition(plot.nearest(point.date) == index, "Every missing row selectable")
        }
        for field in [\Sample.actual, \Sample.projected] {
            let rendered = field == \Sample.actual ? plot.actual : plot.projected
            precondition(rendered.count == stress.points.filter { $0[keyPath: field] != nil }.count)
            for pair in zip(rendered, rendered.dropFirst()) where pair.0.segment == pair.1.segment {
                let left = stress.points.firstIndex { $0.date == pair.0.date }!
                let right = stress.points.firstIndex { $0.date == pair.1.date }!
                precondition(right == left + 1, "Never bridge a null")
            }
        }
        var state = Selection()
        state.step(-1, count: plot.dates.count)
        precondition(state.index == plot.dates.count - 1)
        state.begin(); state.select(0); state.cancel()
        precondition(state.index == plot.dates.count - 1, "Cancellation restores prior index")
        state.reset(); state.begin(); state.select(2); state.cancel()
        precondition(state.index == nil, "Cancellation restores unselected state")
        state.begin(); state.select(2); state.end()
        precondition(state.index == 2, "Release retains selection")
        state.reset(); precondition(state.index == nil)
        state.step(1, count: 0); precondition(state.index == nil)
        state.step(1, count: 1); state.step(-1, count: 1); precondition(state.index == 0)
        let empty = PlotData(fixtures.cases.first { $0.id == "empty" }!)
        precondition(empty.nearest(Date()) == nil)
        let es = Presentation(spanish: true)
        precondition(es.amount(nil, currency: stress.currency) == "Sin datos")
        precondition(es.amount(-12.5, currency: "DOP").contains("DOP"))
        print("PASS: fixture endpoints, tie, null gaps, missing row selection, empty/single, release/cancel/reset, locale/currency")
    }
}
