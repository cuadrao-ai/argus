import Foundation
import XCTest
@testable import ArgusSession
@testable import FinancialModels

@MainActor
final class ConnectedDetailPresentationTests: XCTestCase {
    private let locale = Locale(identifier: "en_US")

    func testKnownZeroUnknownAndUndatedBalanceStayDifferent() throws {
        let zero = try account(position: 0)
        let unknown = try account(position: nil)
        let undated = try account(position: 1255, asOf: nil)
        XCTAssertEqual(row(zero).amount, "0.00")
        XCTAssertEqual(row(unknown).amount, "Balance unknown")
        XCTAssertEqual(detail(unknown).freshness, "No balance recorded")
        XCTAssertEqual(detail(undated).amount, "12.55")
        XCTAssertEqual(detail(undated).freshness, "Balance date unavailable")
        XCTAssertTrue(detail(zero).freshness.hasPrefix("As of "))
        XCTAssertTrue(detail(zero).freshness.contains("2026"))
        XCTAssertFalse(detail(zero).freshness.localizedCaseInsensitiveContains("today"))
    }

    func testCurrencyPrecisionAndLargeSignedAmountsKeepEveryDigit() throws {
        let cases: [(String, Int, Int64, String)] = [
            ("JPY", 0, 123456, "123,456"),
            ("KWD", 3, 123456, "123.456"),
            ("USD", 2, Int64.max, "92,233,720,368,547,758.07"),
            ("USD", 2, Int64.min, "-92,233,720,368,547,758.08"),
        ]
        for (currency, digits, position, expected) in cases {
            let value = try account(position: position, currency: currency, digits: digits)
            XCTAssertEqual(row(value).amount, expected, currency)
            XCTAssertEqual(detail(value).amount, expected, currency)
            XCTAssertEqual(detail(value).currency, currency)
            XCTAssertEqual(detail(value).amountAccessibilityLabel, currency + " " + expected)
        }
    }

    func testFractionalOwnershipIsShownWithoutChangingWholeBalance() throws {
        let cases = [(1, "0.01"), (1255, "12.55"), (9999, "99.99"), (10000, "100")]
        for (bps, percentage) in cases {
            let value = try account(position: 10000, share: bps)
            XCTAssertEqual(row(value).amount, "100.00")
            XCTAssertTrue(detail(value).notes.contains("Your share: " + percentage + "%"))
        }
        let spanish = ConnectedAccountPresentation.detail(try account(position: 10000, share: 1255), spanish: true, locale: Locale(identifier: "es_ES"))
        XCTAssertTrue(spanish.notes.contains("Tu parte: 12,55%"))
    }

    func testCreditAndArchivedStatusDoNotRewriteTheBalance() throws {
        let credit = try account(position: 1500, type: "credit_card", nature: "liability", archived: true, credit: 1500)
        XCTAssertEqual(row(credit).amount, "15.00")
        XCTAssertEqual(row(credit).amountCaption, "USD · credit")
        XCTAssertTrue(row(credit).note?.contains("Archived") == true)
        XCTAssertTrue(detail(credit).notes.contains("Credit balance in your favor"))
        XCTAssertTrue(detail(credit).notes.contains("Archived. Balance and history are kept."))
        let debt = try account(position: -1500, type: "credit_card", nature: "liability")
        XCTAssertEqual(row(debt).amount, "-15.00")
        XCTAssertEqual(row(debt).amountCaption, "USD · owed")
        XCTAssertTrue(detail(debt).notes.contains("Signed balance: a negative amount means money owed."))
    }

    func testUnknownArtworkKeepsTheCanonicalType() throws {
        let future = try account(position: nil, type: "future_type")
        XCTAssertNil(row(future).artwork)
        XCTAssertEqual(row(future).subtitle, "future_type")
    }

    func testLegDirectionsAndKindsRemainIndependent() {
        XCTAssertEqual(FinancialActivityPresentation.signedAmount(Int64.min, digits: 2, locale: locale), "−92,233,720,368,547,758.08")
        XCTAssertEqual(FinancialActivityPresentation.signedAmount(123456, digits: 3, locale: locale), "+123.456")
        XCTAssertEqual(FinancialActivityPresentation.signedAmount(0, digits: 0, locale: locale), "0")
        XCTAssertEqual(FinancialActivityPresentation.symbol(for: "transfer"), "arrow.left.arrow.right")
        XCTAssertEqual(FinancialActivityPresentation.symbol(for: "refund"), "arrow.uturn.backward")
        XCTAssertEqual(FinancialActivityPresentation.symbol(for: "future_kind"), "doc.text")
    }

    func testComingUpRowsShowTitleDateStatusAndAmountInTheAppLanguage() throws {
        let english = try strings("en"), spanish = try strings("es-419")
        let bill = try occurrence(kind: "bill", status: "planned", amount: "2100.00")
        let salary = try occurrence(kind: "income", status: "planned", amount: "38500.00")
        let review = try occurrence(kind: "bill", status: "needs_review", amount: "2100.00")
        XCTAssertEqual(PlanPresentation.upcomingRow(bill, locale: locale, text: { english[$0] ?? $0 }),
                       PlanUpcomingRow(title: "Internet hogar", detail: "Oct 10, 2026\u{00A0}· Planned", amount: "2,100.00 DOP", icon: "calendar"))
        XCTAssertEqual(PlanPresentation.upcomingRow(salary, locale: locale, text: { english[$0] ?? $0 }),
                       PlanUpcomingRow(title: "Internet hogar", detail: "Oct 10, 2026\u{00A0}· Planned", amount: "+38,500.00 DOP", icon: "arrow.down.left"))
        XCTAssertEqual(PlanPresentation.upcomingRow(salary, locale: locale, showsCurrency: false, text: { english[$0] ?? $0 }).amount,
                       "+38,500.00", "one currency in view: rows show bare signed numbers like the approved Preview")
        XCTAssertEqual(PlanPresentation.upcomingRow(review, locale: locale, text: { english[$0] ?? $0 }).detail,
                       "Oct 10, 2026\u{00A0}· Review the linked activity")
        let dominican = Locale(identifier: "es_DO")
        let spanishRow = PlanPresentation.upcomingRow(bill, locale: dominican, text: { spanish[$0] ?? $0 })
        XCTAssertEqual(spanishRow.detail, PlanPresentation.dateLabel("2026-10-10", locale: dominican) + "\u{00A0}· Previsto")
        XCTAssertFalse(spanishRow.detail.contains("Oct"), spanishRow.detail)
        XCTAssertNil(english["plan.home.disclosure"], "Home no longer carries the projection disclosure")
        XCTAssertNil(spanish["plan.home.disclosure"])
    }

    private func strings(_ language: String) throws -> [String: String] {
        let root = try XCTUnwrap(ProcessInfo.processInfo.environment["ARGUS_REPO_ROOT"])
        let url = URL(fileURLWithPath: root + "/ios/ArgusFoundation/Resources/Localizable.xcstrings")
        let catalog = try JSONSerialization.jsonObject(with: Data(contentsOf: url)) as! [String: Any]
        let entries = catalog["strings"] as! [String: [String: Any]]
        return entries.reduce(into: [:]) { values, entry in
            let locales = entry.value["localizations"] as! [String: [String: Any]]
            let unit = locales[language]?["stringUnit"] as? [String: String]
            values[entry.key] = unit?["value"]
        }
    }

    private func occurrence(kind: String, status: String, amount: String) throws -> FinancialPlanOccurrence {
        let payload: [String: Any] = [
            "id": "internet-2026-10-10", "expectation_id": UUID().uuidString, "expectation_version": 1,
            "kind": kind, "title": "Internet hogar", "currency": "DOP", "currency_fraction_digits": 2,
            "amount_minor": 210000, "amount": amount, "account_id": UUID().uuidString,
            "due_date": "2026-10-10", "projection_date": "2026-10-10", "status": status, "overdue": false,
        ]
        return try JSONDecoder().decode(FinancialPlanOccurrence.self, from: JSONSerialization.data(withJSONObject: payload))
    }

    private func row(_ account: FinancialAccount) -> CanvasAccountRowValue {
        ConnectedAccountPresentation.row(account, spanish: false, locale: locale)
    }
    private func detail(_ account: FinancialAccount) -> CanvasAccountDetailValue {
        ConnectedAccountPresentation.detail(account, spanish: false, locale: locale)
    }

    private func account(position: Int64?, currency: String = "USD", digits: Int = 2, type: String = "checking",
                         nature: String = "asset", share: Int = 10000, archived: Bool = false,
                         asOf: String? = "2026-07-13T12:34:00-04:00", credit: Int64? = nil) throws -> FinancialAccount {
        let balance: [String: Any] = [
            "state": position == nil ? "unknown" : "known",
            "amount_minor": position.map { $0 as Any } ?? NSNull(),
            "amount": position.map { AccountPresentation.decimal($0, digits: digits) as Any } ?? NSNull(),
            "as_of": asOf.map { $0 as Any } ?? NSNull(), "basis": "balance_check",
            "activity_since_tracking_minor": 0, "credit_minor": credit.map { $0 as Any } ?? NSNull(),
        ]
        let payload: [String: Any] = [
            "id": UUID().uuidString, "type": type, "nature": nature, "currency": currency,
            "currency_fraction_digits": digits, "nickname": "Account " + UUID().uuidString,
            "archived": archived, "ownership_share_bps": share, "version": 1,
            "created_at": "2026-07-13T16:34:00Z", "updated_at": "2026-07-13T16:34:00Z",
            "balance": balance, "opening": NSNull(), "asset": NSNull(),
        ]
        return try JSONDecoder().decode(FinancialAccount.self, from: JSONSerialization.data(withJSONObject: payload))
    }
}
