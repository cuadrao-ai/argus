import Foundation
import ArgusSession

/// Finds saved receipts by what a person remembers: the file name, and once read, the merchant, the date and the
/// amount. Case, accents and number grouping do not matter; every word of the query must appear.
enum ReceiptSearch {
    static func matches(_ documents: [SavedDocument], readings: [String: DocumentReceipt], query: String) -> [SavedDocument] {
        let needles = words(query)
        guard !needles.isEmpty else { return [] }
        return documents.filter { document in
            let haystack = fold(text(document, reading: readings[document.id]))
            return needles.allSatisfy { haystack.contains($0) }
        }
    }

    static func text(_ document: SavedDocument, reading: DocumentReceipt?) -> String {
        var parts = [document.filename, String(document.createdAt.prefix(10))]
        if let reading {
            parts += [reading.merchant, reading.occurredOn, reading.currency].compactMap { $0 }
            for amount in [reading.total, reading.subtotal].compactMap({ $0 }) { parts += [amount, grouped(amount)] }
            parts += reading.items.compactMap(\.description)
        }
        return parts.joined(separator: " ")
    }

    static func fold(_ text: String) -> String {
        text.folding(options: [.caseInsensitive, .diacriticInsensitive, .widthInsensitive], locale: nil)
    }

    private static func words(_ query: String) -> [String] {
        fold(query).split(whereSeparator: \.isWhitespace).map { String($0).replacingOccurrences(of: ",", with: "") }
    }

    /// "1250.50" also matches as "1,250.50".
    private static func grouped(_ amount: String) -> String {
        guard let value = Decimal(string: amount) else { return amount }
        let formatter = NumberFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX"); formatter.numberStyle = .decimal
        formatter.usesGroupingSeparator = true; formatter.groupingSeparator = ","
        formatter.minimumFractionDigits = amount.split(separator: ".").dropFirst().first?.count ?? 0
        formatter.maximumFractionDigits = formatter.minimumFractionDigits
        return formatter.string(from: value as NSDecimalNumber) ?? amount
    }
}
