import Foundation

public enum MoneyError: Error, Equatable, Sendable {
    /// Not a dot-decimal amount (`amount_invalid`).
    case invalid
    /// More fraction digits than the currency has (`amount_precision`). Nothing is ever rounded.
    case precision(digits: Int)
    /// Larger than a signed 64-bit count of minor units (`amount_out_of_range`).
    case outOfRange
}

/// Signed minor units in one currency. The digits are the account's snapshot, not a lookup.
public struct Money: Hashable, Codable, Sendable {
    public let minor: Int64
    public let currency: String
    public let digits: Int

    public init(minor: Int64, currency: String, digits: Int) {
        self.minor = minor
        self.currency = currency
        self.digits = digits
    }

    /// The exact dot-decimal text, as the wire carries it.
    public var plain: String { MoneyFormatter.plain(minor, digits: digits) }
}

/// Parses a typed amount into minor units the way `argus.domain.recording.currency.parse_minor_units` does:
/// ASCII digits only, one optional dot with digits on both sides, a leading minus, and never any rounding.
public enum MoneyParser {
    public static func parse(_ text: String, digits: Int) -> Result<Int64, MoneyError> {
        guard digits >= 0, digits <= 18 else { return .failure(.invalid) }
        var body = Substring(text.trimmingCharacters(in: .whitespacesAndNewlines))
        let negative = body.hasPrefix("-")
        if negative { body = body.dropFirst() }
        let whole: Substring
        var fraction = Substring("")
        var hasDot = false
        if let dot = body.firstIndex(of: ".") {
            whole = body[..<dot]
            fraction = body[body.index(after: dot)...]
            hasDot = true
        } else {
            whole = body
        }
        guard isASCIIDigits(whole), !hasDot || isASCIIDigits(fraction) else { return .failure(.invalid) }
        guard fraction.count <= digits else { return .failure(.precision(digits: digits)) }
        var magnitude: UInt64 = 0
        let padded = String(fraction) + String(repeating: "0", count: digits - fraction.count)
        for scalar in Array(whole.unicodeScalars) + Array(padded.unicodeScalars) {
            let (scaled, scaleOverflow) = magnitude.multipliedReportingOverflow(by: 10)
            let (sum, addOverflow) = scaled.addingReportingOverflow(UInt64(scalar.value - 48))
            guard !scaleOverflow, !addOverflow, sum <= UInt64(Int64.max) else { return .failure(.outOfRange) }
            magnitude = sum
        }
        let signed = Int64(magnitude)
        return .success(negative ? -signed : signed)
    }

    /// For a field a person is typing in: also accepts a trailing dot ("12.") and a leading one (".5"),
    /// which the strict parser refuses. The result is still exact.
    public static func parseTyped(_ text: String, digits: Int) -> Result<Int64, MoneyError> {
        var cleaned = text.trimmingCharacters(in: .whitespacesAndNewlines)
        if cleaned.hasSuffix("."), cleaned.count > 1 { cleaned.removeLast() }
        let negative = cleaned.hasPrefix("-")
        let unsigned = negative ? String(cleaned.dropFirst()) : cleaned
        let normalized = unsigned.hasPrefix(".") ? "0" + unsigned : unsigned
        return parse((negative ? "-" : "") + normalized, digits: digits)
    }

    private static func isASCIIDigits(_ text: Substring) -> Bool {
        !text.isEmpty && text.unicodeScalars.allSatisfy { $0.value >= 48 && $0.value <= 57 }
    }
}

/// Exact text from minor units. A string is built from the integer, never a number formatter, so nothing rounds.
public enum MoneyFormatter {
    /// `-1234.50`: the wire form, matching `format_minor_units`.
    public static func plain(_ minor: Int64, digits: Int) -> String {
        text(minor, digits: digits, grouping: "", decimal: ".")
    }

    /// `-1,234.50` with the given separators, for display.
    public static func grouped(_ minor: Int64, digits: Int, grouping: String = ",", decimal: String = ".") -> String {
        text(minor, digits: digits, grouping: grouping, decimal: decimal)
    }

    private static func text(_ minor: Int64, digits: Int, grouping: String, decimal: String) -> String {
        let sign = minor < 0 ? "-" : ""
        var digitsText = String(minor.magnitude)
        let width = max(digits, 0)
        if digitsText.count <= width {
            digitsText = String(repeating: "0", count: width - digitsText.count + 1) + digitsText
        }
        let split = digitsText.index(digitsText.endIndex, offsetBy: -width)
        let whole = String(digitsText[..<split])
        let fraction = String(digitsText[split...])
        let grouped = grouping.isEmpty ? whole : group(whole, with: grouping)
        return sign + grouped + (width == 0 ? "" : decimal + fraction)
    }

    private static func group(_ whole: String, with separator: String) -> String {
        var pieces: [String] = []
        var end = whole.endIndex
        while end > whole.startIndex {
            let start = whole.index(end, offsetBy: -3, limitedBy: whole.startIndex) ?? whole.startIndex
            pieces.append(String(whole[start..<end]))
            end = start
        }
        return pieces.reversed().joined(separator: separator)
    }
}
