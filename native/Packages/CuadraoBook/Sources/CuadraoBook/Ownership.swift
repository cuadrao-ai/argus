/// The owner's share of an amount, as the server computes it for personal totals.
public enum Ownership {
    public static let fullShareBps = 10_000

    /// Scale by basis points, round half to even, keep the sign. Mirrors the server's `personal_share`;
    /// nil when the share is negative or the arithmetic would overflow.
    public static func share(of amount: Int64, bps: Int) -> Int64? {
        guard bps >= 0 else { return nil }
        let (scaled, overflow) = amount.magnitude.multipliedReportingOverflow(by: UInt64(bps))
        guard !overflow else { return nil }
        var quotient = scaled / 10000
        let remainder = scaled % 10000
        if remainder > 5000 || (remainder == 5000 && quotient % 2 == 1) { quotient += 1 }
        guard quotient <= UInt64(Int64.max) else { return nil }
        return amount >= 0 ? Int64(quotient) : -Int64(quotient)
    }
}
