import SwiftUI

/// What Search offers before anything is typed: the person's own recent searches and a few suggestions
/// built from their own accounts and categories. Suggestions are plain text that fills the query.
struct CuadraoSearchStart {
    var suggestions: [String]

    /// Up to four chips: the most used names first, then the remaining names, with no repeats.
    static func suggestions(frequent: [String], names: [String], limit: Int = 4) -> [String] {
        let counts = Dictionary(frequent.filter { !$0.isEmpty }.map { ($0, 1) }, uniquingKeysWith: +)
        let ranked = counts.sorted { $0.value == $1.value ? $0.key < $1.key : $0.value > $1.value }.map(\.key)
        var seen = Set<String>()
        return Array((Array(ranked.prefix(2)) + names).filter { seen.insert($0.lowercased()).inserted }.prefix(limit))
    }
}

/// Recent queries live in memory for this launch only, so a signed-out account never leaves words behind.
@MainActor final class CuadraoSearchRecents: ObservableObject {
    static let shared = CuadraoSearchRecents()
    @Published private(set) var items: [String] = []
    func remember(_ query: String) {
        let text = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard text.count >= 2 else { return }
        items = Array(([text] + items.filter { $0.caseInsensitiveCompare(text) != .orderedSame }).prefix(5))
    }
    func clear() { items = [] }
}

struct CuadraoSearchCopy {
    let spanish: Bool
    var recents: String { spanish ? "Recientes" : "Recent" }
    var clear: String { spanish ? "Borrar" : "Clear" }
    var suggestions: String { spanish ? "Prueba buscar" : "Try searching" }
}

struct CuadraoSearchStartView: View {
    let start: CuadraoSearchStart
    let spanish: Bool
    let prefix: String
    let pick: (String) -> Void
    @ObservedObject private var recents = CuadraoSearchRecents.shared

    private var copy: CuadraoSearchCopy { CuadraoSearchCopy(spanish: spanish) }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            if !recents.items.isEmpty {
                HStack {
                    Text(copy.recents).font(CuadraoTypography.supporting).foregroundStyle(.secondary)
                    Spacer()
                    Button(copy.clear) { recents.clear() }.font(.subheadline).frame(minHeight: 44)
                        .accessibilityIdentifier(prefix + ".recents.clear")
                }.padding(.top, 18)
                ForEach(Array(recents.items.enumerated()), id: \.element) { index, item in
                    Button { pick(item) } label: {
                        HStack(spacing: 12) {
                            Image(systemName: "clock.arrow.circlepath").foregroundStyle(.secondary).accessibilityHidden(true)
                            Text(item).foregroundStyle(WelcomePalette.ink).lineLimit(1)
                            Spacer(minLength: 0)
                        }.frame(minHeight: 48).contentShape(Rectangle())
                    }.buttonStyle(.plain).accessibilityIdentifier(prefix + ".recent.\(index)")
                    Divider().foregroundStyle(WelcomePalette.separator)
                }
            }
            if !start.suggestions.isEmpty {
                Text(copy.suggestions).font(CuadraoTypography.supporting).foregroundStyle(.secondary)
                    .padding(.top, recents.items.isEmpty ? 18 : 28).padding(.bottom, 8)
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 8) {
                        ForEach(Array(start.suggestions.enumerated()), id: \.element) { index, item in
                            Button { pick(item) } label: {
                                Text(item).font(.subheadline).lineLimit(1).padding(.horizontal, 14).frame(minHeight: 44)
                                    .foregroundStyle(WelcomePalette.ink).background(WelcomePalette.surface, in: Capsule())
                            }.buttonStyle(.plain).accessibilityIdentifier(prefix + ".suggestion.\(index)")
                        }
                    }
                }
            }
        }.accessibilityElement(children: .contain).accessibilityIdentifier(prefix + ".start")
    }
}
