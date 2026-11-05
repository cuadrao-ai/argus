import Foundation

struct FixtureBundle: Decodable {
    let cases: [Scenario]
    static func load() throws -> FixtureBundle {
        guard let url = Bundle.main.url(forResource: "series", withExtension: "json") else {
            throw CocoaError(.fileNoSuchFile)
        }
        return try JSONDecoder().decode(FixtureBundle.self, from: Data(contentsOf: url))
    }
}

struct Scenario: Decodable, Identifiable {
    let id: String
    let title: [String: String]
    let currency: String
    let unit: String
    let shape: String
    let points: [Sample]
}

struct Sample: Decodable {
    let time: String
    let actual: Double?
    let projected: Double?
    let contribution: Double?
    var date: Date { Self.parser.date(from: time)! }
    private static let parser: DateFormatter = {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter
    }()
}

struct PlotPoint: Identifiable {
    let id: String
    let date: Date
    let value: Double
    let segment: String
}

struct PlotData {
    let actual: [PlotPoint]
    let projected: [PlotPoint]
    let dates: [Date]
    init(_ scenario: Scenario) {
        dates = scenario.points.map(\.date)
        func series(_ key: KeyPath<Sample, Double?>, name: String) -> [PlotPoint] {
            var segment = 0
            return scenario.points.enumerated().compactMap { index, sample in
                guard let value = sample[keyPath: key] else { segment += 1; return nil }
                return PlotPoint(id: "\(name)-\(index)", date: sample.date, value: value,
                                 segment: "\(name)-\(segment)")
            }
        }
        actual = series(\.actual, name: "actual")
        projected = series(\.projected, name: "projected")
    }
    var domain: ClosedRange<Date> {
        guard let first = dates.first, let last = dates.last else {
            return Date(timeIntervalSince1970: 0)...Date(timeIntervalSince1970: 86400)
        }
        return first == last ? first.addingTimeInterval(-43200)...last.addingTimeInterval(43200) : first...last
    }
    func nearest(_ date: Date) -> Int? {
        guard !dates.isEmpty else { return nil }
        var low = 0, high = dates.count
        while low < high {
            let mid = (low + high) / 2
            if dates[mid] < date { low = mid + 1 } else { high = mid }
        }
        if low == 0 { return 0 }
        if low == dates.count { return dates.count - 1 }
        return date.timeIntervalSince(dates[low - 1]) <= dates[low].timeIntervalSince(date) ? low - 1 : low
    }
}

struct Selection {
    var index: Int?
    private var beforeDrag: Int?
    private var dragging = false
    mutating func begin() { beforeDrag = index; dragging = true }
    mutating func select(_ value: Int?) { index = value }
    mutating func end() { dragging = false }
    mutating func cancel() {
        if dragging { index = beforeDrag }
        dragging = false
    }
    mutating func reset() { index = nil; dragging = false }
    mutating func step(_ direction: Int, count: Int) {
        guard count > 0 else { return }
        index = index.map { min(max($0 + direction, 0), count - 1) } ?? (direction > 0 ? 0 : count - 1)
    }
}

struct Presentation {
    let spanish: Bool
    var locale: Locale { Locale(identifier: spanish ? "es-419" : "en-US") }
    func text(_ en: String, _ es: String) -> String { spanish ? es : en }
    func amount(_ value: Double?, currency: String) -> String {
        guard let value else { return text("No data", "Sin datos") }
        let format = NumberFormatter()
        format.locale = locale
        format.numberStyle = .decimal
        format.minimumFractionDigits = 2
        format.maximumFractionDigits = 2
        return "\(currency) \(format.string(from: NSNumber(value: value))!)"
    }
    func date(_ value: Date, compact: Bool = false) -> String {
        let format = DateFormatter()
        format.locale = locale
        format.calendar = Calendar(identifier: .gregorian)
        format.timeZone = TimeZone(secondsFromGMT: 0)
        if compact { format.setLocalizedDateFormatFromTemplate("MMMd") } else { format.dateStyle = .medium }
        return format.string(from: value)
    }
}
