import SwiftUI

/// "Actualizado hace 2 min": when the last successful load finished, in the device clock. Nothing shows before one has.
struct CuadraoLastUpdated: View {
    let date: Date?
    let spanish: Bool
    var identifier = "cuadrao.lastUpdated"

    static func text(since date: Date, now: Date, spanish: Bool) -> String {
        let minutes = max(0, Int(now.timeIntervalSince(date) / 60))
        switch minutes {
        case 0: return CuadraoCopy.text("copy.cuadraoLastUpdated.63d4eab0ac", spanish: spanish)
        case 1..<60: return CuadraoCopy.text("copy.cuadraoLastUpdated.82ebe5f358", spanish: spanish, String(describing: minutes))
        case 60..<1440:
            let hours = minutes / 60
            return CuadraoCopy.text("copy.cuadraoLastUpdated.ca4ede8acb", spanish: spanish, String(describing: hours))
        default:
            let days = minutes / 1440
            return CuadraoCopy.text("copy.cuadraoLastUpdated.317bdf46ee", spanish: spanish, String(describing: days))
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
