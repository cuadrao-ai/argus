import Foundation

/// Text-only locale conversion. Currency precision and validity remain server-owned.
enum AccountEntry {
    enum Failure: Error { case amount, share }
    static func amount(_ raw: String, locale: Locale) throws -> String? {
        if raw.isEmpty { return nil }
        let decimal = locale.decimalSeparator ?? "."
        let grouping = locale.groupingSeparator ?? ","
        let d = NSRegularExpression.escapedPattern(for: decimal)
        let g = NSRegularExpression.escapedPattern(for: grouping)
        let pattern = "^-?(?:[0-9]+|[0-9]{1,3}(?:" + g + "[0-9]{3})+)(?:" + d + "[0-9]+)?$"
        guard raw.range(of: pattern, options: .regularExpression) != nil else { throw Failure.amount }
        return raw.replacingOccurrences(of: grouping, with: "").replacingOccurrences(of: decimal, with: ".")
    }
    static func share(_ raw: String) throws -> Int {
        guard case .success(let value?) = PercentInput.parse(raw, .share) else { throw Failure.share }
        return PercentInput.basisPoints(value)
    }
}

/// One rule for every percentage a person types: interest rates and ownership shares.
/// A percentage never needs grouping, so one "." or "," is the decimal mark in any region; "%" and spaces are ignored.
enum PercentInput {
    enum Problem: Error, Equatable { case notNumber, decimals, range, required }
    struct Bounds: Equatable {
        let minimum: Decimal, maximum: Decimal, emptyAllowed: Bool
        static let interest = Bounds(minimum: 0, maximum: 100, emptyAllowed: true)
        static let share = Bounds(minimum: Decimal(string: "0.01")!, maximum: 100, emptyAllowed: false)
    }

    /// The accepted value, nil for an allowed empty field, or the problem to name next to the field.
    static func parse(_ raw: String, _ bounds: Bounds) -> Result<Decimal?, Problem> {
        let text = raw.replacingOccurrences(of: "%", with: "").trimmingCharacters(in: .whitespacesAndNewlines)
        if text.isEmpty { return bounds.emptyAllowed ? .success(nil) : .failure(.required) }
        guard text.range(of: "^[0-9]+(?:[.,][0-9]*)?$|^[.,][0-9]+$", options: .regularExpression) != nil else { return .failure(.notNumber) }
        let parts = text.split(separator: Character(text.contains(",") ? "," : "."), omittingEmptySubsequences: false)
        let whole = parts.first.map(String.init).flatMap { $0.isEmpty ? "0" : $0 } ?? "0"
        let fraction = parts.count > 1 ? String(parts[1]) : ""
        guard fraction.count <= 2 else { return .failure(.decimals) }
        guard let value = Decimal(string: fraction.isEmpty ? whole : whole + "." + fraction, locale: Locale(identifier: "en_US_POSIX")) else { return .failure(.notNumber) }
        guard value >= bounds.minimum && value <= bounds.maximum else { return .failure(.range) }
        return .success(value)
    }

    static func message(_ problem: Problem, _ bounds: Bounds, spanish: Bool) -> String {
        let low = bounds.minimum == 0 ? "0" : "0.01"
        switch problem {
        case .notNumber: return spanish ? "Usa solo números, por ejemplo 18.5." : "Use numbers only, for example 18.5."
        case .decimals: return spanish ? "Usa hasta 2 decimales." : "Use up to 2 decimals."
        case .range: return spanish ? "Debe estar entre \(low) y 100." : "It must be between \(low) and 100."
        case .required: return spanish ? "Escribe un porcentaje." : "Enter a percentage."
        }
    }

    /// Basis points for an accepted share, the unit the server stores.
    static func basisPoints(_ value: Decimal) -> Int {
        NSDecimalNumber(decimal: value * 100).intValue
    }
}
