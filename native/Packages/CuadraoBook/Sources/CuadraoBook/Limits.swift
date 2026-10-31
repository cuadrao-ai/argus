/// Bounds the device book enforces so a stored total cannot overflow and a field cannot grow without end.
public enum Limits {
    /// Characters (Unicode scalars) in an account nickname; the server's `NICKNAME_MAX_CODE_POINTS`.
    public static let nickname = 60
    /// Characters in a movement note; the server's `note` bound.
    public static let note = 200
    /// Largest absolute single amount, in minor units. 9,200 of these still sum inside Int64.
    public static let maximumMinor: Int64 = 1_000_000_000_000_000
    public static let accounts = 200
    public static let planName = 60

    public static func withinAmount(_ minor: Int64) -> Bool {
        minor.magnitude <= UInt64(maximumMinor)
    }
}
