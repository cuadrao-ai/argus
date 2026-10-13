import Foundation
import XCTest
@testable import FinancialModels

/// Founder walk step 12: every percentage field reads the same way and never changes a value silently.
final class PercentInputTests: XCTestCase {
    private func interest(_ raw: String) -> Result<Decimal?, PercentInput.Problem> { PercentInput.parse(raw, .interest) }

    func testInterestAcceptsPlainNumbersEitherDecimalMarkAndAPercentSign() {
        let accepted: [(String, Decimal?)] = [
            ("", nil), ("   ", nil), ("0", 0), ("18", 18), ("18.5", Decimal(string: "18.5")), ("18,5", Decimal(string: "18.5")),
            (" 18.50 % ", Decimal(string: "18.5")), ("100", 100), ("100.00", 100), (".5", Decimal(string: "0.5")), ("7.", 7), ("%", nil),
        ]
        for (raw, value) in accepted { XCTAssertEqual(interest(raw), .success(value), raw) }
    }

    func testInterestNamesEveryRejectionInsteadOfUsingZero() {
        let rejected: [(String, PercentInput.Problem)] = [
            ("abc", .notNumber), ("1.2.3", .notNumber), ("1,2.3", .notNumber), ("-5", .notNumber), ("1e3", .notNumber),
            ("١٨", .notNumber), ("18 5", .notNumber), ("18.555", .decimals), ("100.01", .range), ("150", .range),
            ("99999999999999999999", .range),
        ]
        for (raw, problem) in rejected { XCTAssertEqual(interest(raw), .failure(problem), raw) }
    }

    func testShareRequiresAValueAboveZeroAndStoresBasisPoints() throws {
        XCTAssertEqual(PercentInput.parse("", .share), .failure(.required))
        XCTAssertEqual(PercentInput.parse("0", .share), .failure(.range))
        XCTAssertEqual(try AccountEntry.share("0.01"), 1)
        XCTAssertEqual(try AccountEntry.share("50,5"), 5050)
        XCTAssertEqual(try AccountEntry.share("100"), 10000)
        XCTAssertThrowsError(try AccountEntry.share("100.5"))
        XCTAssertThrowsError(try AccountEntry.share("abc"))
    }

    func testMessagesAreSpanishFirstAndNameTheRule() {
        XCTAssertEqual(PercentInput.message(.decimals, .interest, spanish: true), "Usa hasta 2 decimales.")
        XCTAssertEqual(PercentInput.message(.range, .interest, spanish: true), "Debe estar entre 0 y 100.")
        XCTAssertEqual(PercentInput.message(.range, .share, spanish: true), "Debe estar entre 0.01 y 100.")
        XCTAssertEqual(PercentInput.message(.notNumber, .interest, spanish: false), "Use numbers only, for example 18.5.")
    }
}
