import Foundation

public enum SearchScope: Sendable, CaseIterable {
    case all, accounts, activity, plans
}

public enum SearchSection: Sendable, Hashable {
    case accounts, activity, plans
}

/// One searchable record. The host writes the words people read (titles, kind names, notes, amounts) because they depend on
/// the language; the index only compares them.
public struct SearchEntry: Equatable, Identifiable, Sendable {
    public let id: UUID
    public let section: SearchSection
    /// Everything a person might type to find it.
    public let text: [String]
    public let currency: String

    public init(id: UUID, section: SearchSection, text: [String], currency: String) {
        self.id = id
        self.section = section
        self.text = text
        self.currency = currency
    }
}

/// Pure search over entries the host built: case and diacritic insensitive, every word of the query must appear, a scope and
/// an optional currency narrow it. The order of the entries is kept.
public enum SearchIndex {
    public static func fold(_ text: String) -> String {
        text.folding(options: [.caseInsensitive, .diacriticInsensitive, .widthInsensitive], locale: nil)
    }

    public static func words(_ query: String) -> [String] {
        fold(query).split(whereSeparator: { $0.isWhitespace }).map(String.init)
    }

    public static func filter(_ entries: [SearchEntry], query: String, scope: SearchScope = .all, currency: String? = nil) -> [SearchEntry] {
        let needles = words(query)
        return entries.filter { entry in
            guard scope == .all || section(of: scope) == entry.section else { return false }
            guard currency == nil || currency == entry.currency else { return false }
            guard !needles.isEmpty else { return true }
            let haystack = entry.text.map(fold).joined(separator: " ")
            return needles.allSatisfy { haystack.contains($0) }
        }
    }

    private static func section(of scope: SearchScope) -> SearchSection? {
        switch scope {
        case .all: nil
        case .accounts: .accounts
        case .activity: .activity
        case .plans: .plans
        }
    }
}
