import Foundation

/// Calculation policy: money math is integers or `Decimal`, never a floating-point type, and a result is
/// either exact or refused. A test scans this package's sources for floating-point types.
public enum MinorUnits {
    public static func decimal(_ minor: Int64, digits: Int) -> Decimal {
        Decimal(sign: minor < 0 ? .minus : .plus, exponent: -digits, significand: Decimal(minor.magnitude))
    }

    /// The minor units a decimal amount is worth, or nil unless it is a whole number of them.
    public static func exactMinor(_ value: Decimal, digits: Int) -> Int64? {
        var scaled = value
        var scale = Decimal(sign: .plus, exponent: digits, significand: 1)
        var result = Decimal()
        NSDecimalMultiply(&result, &scaled, &scale, .plain)
        var rounded = Decimal()
        NSDecimalRound(&rounded, &result, 0, .plain)
        guard rounded == result, result.magnitude <= Decimal(Int64.max) else { return nil }
        return (result as NSDecimalNumber).int64Value
    }
}
