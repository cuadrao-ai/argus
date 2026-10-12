import SwiftUI

/// "Actualizado hace 2 min": when the last successful load finished, in the device clock. Nothing shows before one has.
struct CuadraoLastUpdated: View {
    let date: Date?
    let spanish: Bool
    var identifier = "cuadrao.lastUpdated"

    static func text(since date: Date, now: Date, spanish: Bool) -> String {
        let minutes = max(0, Int(now.timeIntervalSince(date) / 60))
        switch minutes {
        case 0: return spanish ? "Actualizado ahora" : "Updated just now"
        case 1..<60: return spanish ? "Actualizado hace \(minutes) min" : "Updated \(minutes) min ago"
        case 60..<1440:
            let hours = minutes / 60
            return spanish ? "Actualizado hace \(hours) h" : "Updated \(hours) h ago"
        default:
            let days = minutes / 1440
            return spanish ? "Actualizado hace \(days) d" : "Updated \(days) d ago"
        }
    }

    var body: some View {
        if let date {
            TimelineView(.periodic(from: .now, by: 30)) { context in
                Text(Self.text(since: date, now: context.date, spanish: spanish))
                    .font(.footnote).foregroundStyle(.secondary).accessibilityIdentifier(identifier)
            }
        }
    }
}
