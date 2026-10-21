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
        var decimals = 2
        static let interest = Bounds(minimum: 0, maximum: 100, emptyAllowed: true)
        static let share = Bounds(minimum: Decimal(string: "0.01")!, maximum: 100, emptyAllowed: false)
        /// The first-account sheet stores whole percents.
        static let wholeShare = Bounds(minimum: 1, maximum: 100, emptyAllowed: false, decimals: 0)
    }

    /// The accepted value, nil for an allowed empty field, or the problem to name next to the field.
    static func parse(_ raw: String, _ bounds: Bounds) -> Result<Decimal?, Problem> {
        let text = raw.replacingOccurrences(of: "%", with: "").trimmingCharacters(in: .whitespacesAndNewlines)
        if text.isEmpty { return bounds.emptyAllowed ? .success(nil) : .failure(.required) }
        guard text.range(of: "^[0-9]+(?:[.,][0-9]*)?$|^[.,][0-9]+$", options: .regularExpression) != nil else { return .failure(.notNumber) }
        let parts = text.split(separator: Character(text.contains(",") ? "," : "."), omittingEmptySubsequences: false)
        let whole = parts.first.map(String.init).flatMap { $0.isEmpty ? "0" : $0 } ?? "0"
        let fraction = parts.count > 1 ? String(parts[1]) : ""
        guard fraction.count <= bounds.decimals else { return .failure(.decimals) }
        guard let value = Decimal(string: fraction.isEmpty ? whole : whole + "." + fraction, locale: Locale(identifier: "en_US_POSIX")) else { return .failure(.notNumber) }
        guard value >= bounds.minimum && value <= bounds.maximum else { return .failure(.range) }
        return .success(value)
    }

    /// The problem with this text, or nil when it is accepted.
    static func problem(_ raw: String, _ bounds: Bounds) -> Problem? {
        if case .failure(let problem) = parse(raw, bounds) { return problem }
        return nil
    }

    static func message(_ problem: Problem, _ bounds: Bounds, spanish: Bool) -> String {
        let low = NSDecimalNumber(decimal: bounds.minimum).stringValue
        switch problem {
        case .notNumber: return CuadraoCopy.text("copy.accountEntry.43a009b129", spanish: spanish)
        case .decimals where bounds.decimals == 0: return CuadraoCopy.text("copy.accountEntry.265f673ea8", spanish: spanish)
        case .decimals: return CuadraoCopy.text("copy.accountEntry.c1b113ea68", spanish: spanish)
        case .range: return CuadraoCopy.text("copy.accountEntry.b8e5deab40", spanish: spanish, String(describing: low))
        case .required: return CuadraoCopy.text("copy.accountEntry.d11f702e18", spanish: spanish)
        }
    }

    /// Basis points for an accepted share, the unit the server stores.
    static func basisPoints(_ value: Decimal) -> Int {
        NSDecimalNumber(decimal: value * 100).intValue
    }
}

/// The plan editor's interest rule: only the visible Deuda rate field holds the save back, and it names itself.
enum PlanRateCheck {
    static func blocking(kind: String, showsRate: Bool, text: String) -> PercentInput.Problem? {
        kind == "debt" && showsRate ? PercentInput.problem(text, .interest) : nil
    }
    static func hint(_ problem: PercentInput.Problem?, spanish: Bool) -> String? {
        problem == nil ? nil : (CuadraoCopy.text("copy.accountEntry.ad60309699", spanish: spanish))
    }
}
