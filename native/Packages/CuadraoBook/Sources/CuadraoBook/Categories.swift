/// The expense categories the server accepts, in its order (`CATEGORY_IDS`).
public enum ExpenseCategory: String, CaseIterable, Codable, Sendable {
    case other, groceries, dining, transport, housing, health, shopping
    case interestFees = "interest_fees"
}
