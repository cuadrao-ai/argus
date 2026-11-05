import Foundation
import XCTest
@testable import ArgusSession

final class FinancialExpectationSeedTests: XCTestCase {
    func testNextMonthlyDateKeepsAnchorAndClampsShortMonths() {
        XCTAssertEqual(FinancialRecurrence.nextMonthlyDate(after: "2026-01-31", onOrAfter: "2026-02-15")?.date, "2026-02-28")
        XCTAssertEqual(FinancialRecurrence.nextMonthlyDate(after: "2026-01-31", onOrAfter: "2026-02-15")?.monthDay, 31)
        XCTAssertEqual(FinancialRecurrence.nextMonthlyDate(after: "2024-02-29", onOrAfter: "2025-02-01")?.date, "2025-02-28")
        XCTAssertEqual(FinancialRecurrence.nextMonthlyDate(after: "2024-02-29", onOrAfter: "2025-02-01")?.monthDay, 29)
        XCTAssertEqual(FinancialRecurrence.nextMonthlyDate(after: "2026-01-30", onOrAfter: "2026-03-01")?.date, "2026-03-30")
    }

    func testNextMonthlyDateForMovementTodayPastAndFuture() {
        XCTAssertEqual(FinancialRecurrence.nextMonthlyDate(after: "2026-10-05", onOrAfter: "2026-10-05")?.date, "2026-11-05")
        XCTAssertEqual(FinancialRecurrence.nextMonthlyDate(after: "2026-09-15", onOrAfter: "2026-10-05")?.date, "2026-10-15")
        XCTAssertEqual(FinancialRecurrence.nextMonthlyDate(after: "2026-03-20", onOrAfter: "2026-10-05")?.date, "2026-10-20")
        XCTAssertEqual(FinancialRecurrence.nextMonthlyDate(after: "2026-10-04", onOrAfter: "2026-10-05")?.date, "2026-11-04")
        XCTAssertEqual(FinancialRecurrence.nextMonthlyDate(after: "2026-10-20", onOrAfter: "2026-10-05")?.date, "2026-11-20")
        XCTAssertEqual(FinancialRecurrence.nextMonthlyDate(after: "2026-12-31", onOrAfter: "2026-12-31")?.date, "2027-01-31")
        XCTAssertNil(FinancialRecurrence.nextMonthlyDate(after: "2026-13-01", onOrAfter: "2026-10-05"))
        XCTAssertNil(FinancialRecurrence.nextMonthlyDate(after: "2026-10-05", onOrAfter: "not a day"))
    }

    func testCalendarDayFollowsTheMovementTimeZone() {
        XCTAssertEqual(FinancialRecurrence.calendarDay(of: "2026-10-05T03:30:00+00:00", timeZone: "America/Santo_Domingo"), "2026-10-04")
        XCTAssertEqual(FinancialRecurrence.calendarDay(of: "2026-10-05T03:30:00.250000+00:00", timeZone: "UTC"), "2026-10-05")
        XCTAssertNil(FinancialRecurrence.calendarDay(of: "2026-10-05T03:30:00Z", timeZone: "Mars/Olympus"))
    }

    func testExpenseWithNoteAndEligibleAccountBecomesMonthlyBill() throws {
        let checking = UUID()
        let activity = try Self.activity(kind: "expense", amount: "350.00", note: "Rent for the apartment", account: checking, occurredAt: "2026-09-15T16:00:00Z")
        let seed = try XCTUnwrap(FinancialExpectationSeed(activity: activity, accounts: [Self.account(checking, type: "checking")],
                                                           today: "2026-10-05", fallbackTitle: "Housing"))
        XCTAssertEqual(seed.kind, .bill)
        XCTAssertEqual(seed.title, "Rent for the apartment")
        XCTAssertEqual(seed.currency, "DOP")
        XCTAssertEqual(seed.amount, "350.00")
        XCTAssertEqual(seed.accountId, checking)
        XCTAssertEqual(seed.cadence, .monthly)
        XCTAssertEqual(seed.monthDay, 15)
        XCTAssertEqual(seed.startDate, "2026-10-15")
    }

    func testIncomeWithoutNoteUsesFallbackTitleAndTruncatesLongNotes() throws {
        let cash = UUID()
        let blank = try Self.activity(kind: "income", amount: "1000.00", note: "  ", account: cash, occurredAt: "2026-10-05T16:00:00Z")
        let seed = try XCTUnwrap(FinancialExpectationSeed(activity: blank, accounts: [Self.account(cash, type: "cash")], today: "2026-10-05", fallbackTitle: "Salary"))
        XCTAssertEqual(seed.kind, .income)
        XCTAssertEqual(seed.title, "Salary")
        XCTAssertEqual(seed.startDate, "2026-11-05")
        let long = String(repeating: "x", count: 120)
        let verbose = try Self.activity(kind: "income", amount: "1.00", note: long, account: cash, occurredAt: "2026-10-05T16:00:00Z")
        let truncated = try XCTUnwrap(FinancialExpectationSeed(activity: verbose, accounts: [], today: "2026-10-05", fallbackTitle: "Salary"))
        XCTAssertEqual(truncated.title, String(repeating: "x", count: 100))
        // A family emoji is one Character but five code points; the server counts code points.
        let family = String(repeating: "\u{1F468}\u{200D}\u{1F469}\u{200D}\u{1F467}", count: 25)
        XCTAssertEqual(family.count, 25); XCTAssertEqual(family.unicodeScalars.count, 125)
        let emoji = try Self.activity(kind: "expense", amount: "1.00", note: family, account: cash, occurredAt: "2026-10-05T16:00:00Z")
        let scalars = try XCTUnwrap(FinancialExpectationSeed(activity: emoji, accounts: [], today: "2026-10-05", fallbackTitle: "x"))
        XCTAssertEqual(scalars.title.unicodeScalars.count, 100)
        XCTAssertEqual(scalars.title, String(repeating: "\u{1F468}\u{200D}\u{1F469}\u{200D}\u{1F467}", count: 20))
    }

    func testAccountStaysUnsetUnlessEligibleInTheSameCurrency() throws {
        let card = UUID(), dollars = UUID(), archived = UUID(), savings = UUID()
        func seed(_ account: UUID, _ accounts: [FinancialAccount]) throws -> UUID? {
            let activity = try Self.activity(kind: "expense", amount: "9.00", note: "Coffee", account: account, occurredAt: "2026-10-01T12:00:00Z")
            return try XCTUnwrap(FinancialExpectationSeed(activity: activity, accounts: accounts, today: "2026-10-05", fallbackTitle: "Dining")).accountId
        }
        XCTAssertNil(try seed(card, [Self.account(card, type: "credit_card")]))
        XCTAssertNil(try seed(dollars, [Self.account(dollars, type: "checking", currency: "USD")]))
        XCTAssertNil(try seed(archived, [Self.account(archived, type: "checking", archived: true)]))
        XCTAssertNil(try seed(savings, []))
        XCTAssertEqual(try seed(savings, [Self.account(savings, type: "savings")]), savings)
    }

    func testOnlyIncomeAndExpenseWithTheOriginalAmountAreEligible() throws {
        let account = UUID()
        for kind in ["transfer", "refund", "card_payment", "debt_payment", "payment_reversal"] {
            let activity = try Self.activity(kind: kind, amount: "5.00", note: nil, account: account, occurredAt: "2026-10-01T12:00:00Z")
            XCTAssertFalse(FinancialExpectationSeed.eligible(activity), kind)
            XCTAssertNil(FinancialExpectationSeed(activity: activity, accounts: [], today: "2026-10-05", fallbackTitle: "x"), kind)
        }
        let redacted = try Self.activity(kind: "expense", amount: nil, note: nil, account: account, occurredAt: "2026-10-01T12:00:00Z")
        XCTAssertFalse(FinancialExpectationSeed.eligible(redacted))
        XCTAssertNil(FinancialExpectationSeed(activity: redacted, accounts: [], today: "2026-10-05", fallbackTitle: "x"))
        XCTAssertTrue(FinancialExpectationSeed.eligible(try Self.activity(kind: "income", amount: "5.00", note: nil, account: account, occurredAt: "2026-10-01T12:00:00Z")))
    }

    private static func activity(kind: String, amount: String?, note: String?, account: UUID, occurredAt: String) throws -> FinancialActivityDetail {
        let paired = ["transfer", "card_payment", "debt_payment", "payment_reversal"].contains(kind)
        let legs: [[String: Any]] = paired
            ? ["source", "destination"].map { ["record_id": UUID().uuidString, "record_revision": 1, "account_id": $0 == "source" ? account.uuidString : UUID().uuidString, "role": $0, "balance_movement_minor": 0, "coverage": []] }
            : [["record_id": UUID().uuidString, "record_revision": 1, "account_id": account.uuidString, "role": "single", "balance_movement_minor": 0, "coverage": []]]
        let raw: [String: Any] = [
            "activity_id": UUID().uuidString, "revision": 1, "kind": kind,
            "amount_minor": amount.map { Int64((Double($0)! * 100).rounded()) } as Any? ?? NSNull(), "amount": amount as Any? ?? NSNull(),
            "currency": "DOP", "currency_fraction_digits": 2, "occurred_at": occurredAt, "time_zone": "UTC",
            "note": note as Any? ?? NSNull(), "category_id": "housing", "recorded_at": occurredAt, "legs": legs,
        ]
        return try JSONDecoder().decode(FinancialActivityDetail.self, from: JSONSerialization.data(withJSONObject: raw))
    }

    private static func account(_ id: UUID, type: String, currency: String = "DOP", archived: Bool = false) throws -> FinancialAccount {
        let raw: [String: Any] = ["id": id.uuidString, "type": type, "nature": type == "credit_card" ? "liability" : "asset", "currency": currency,
            "currency_fraction_digits": 2, "archived": archived, "ownership_share_bps": 10000, "version": 1,
            "created_at": "2026-09-01T12:00:00Z", "updated_at": "2026-09-01T12:00:00Z",
            "balance": ["state": "unknown", "activity_since_tracking_minor": 0]]
        return try JSONDecoder().decode(FinancialAccount.self, from: JSONSerialization.data(withJSONObject: raw))
    }
}
