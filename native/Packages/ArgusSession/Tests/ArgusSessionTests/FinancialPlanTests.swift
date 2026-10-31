import Foundation
import XCTest
@testable import ArgusSession

final class FinancialPlanTests: XCTestCase {
    func testForecastPreservesUnknownTotalsAndOrderedSameDayShortfall() throws {
        let account = UUID()
        let raw = #"{"currency":"DOP","currency_fraction_digits":2,"account_ids":["\#(account)"],"unknown_account_ids":["\#(account)"],"known_starting_minor":"18446744073709551614","starting_minor":null,"expected_income_minor":"50","expected_bills_minor":"100","net_cash_change_minor":"-50","ending_minor":null,"first_shortfall_date":null,"as_of":null,"order":"bills_before_income","points":[{"date":"2026-09-29","occurrence_id":null,"change_minor":"0","known_balance_minor":"18446744073709551614","balance_minor":null},{"date":"2026-09-29","occurrence_id":"bill","change_minor":"-100","known_balance_minor":"18446744073709551514","balance_minor":null},{"date":"2026-09-29","occurrence_id":"income","change_minor":"50","known_balance_minor":"18446744073709551564","balance_minor":null}]}"#
        let forecast = try JSONDecoder().decode(FinancialForecastCurrency.self, from: Data(raw.utf8))
        XCTAssertNil(forecast.startingMinor)
        XCTAssertNil(forecast.endingMinor)
        XCTAssertEqual(forecast.knownStartingMinor, "18446744073709551614")
        XCTAssertEqual(forecast.points.map(\.occurrenceId), [nil, "bill", "income"])
        XCTAssertTrue(forecast.points.allSatisfy { $0.balanceMinor == nil })
    }

    func testPlanJournalRetainsTypedOperationAndOriginalVersionAcrossRelaunch() throws {
        let owner = UUID(), account = UUID()
        let identity = SessionSnapshot(phase: .authenticated, profile: .init(id: owner.uuidString,
            email: nil, displayName: nil, language: nil), revision: 1)
        let storage = MemoryStore()
        let operations: [FinancialPlanOperation] = [.createBudget, .editBudget(id: UUID(), version: 2), .createExpectation, .editExpectation(id: UUID(), version: 7),
            .selection(version: 4), .fulfill(occurrenceId: "opaque-occurrence", version: 3), .link(occurrenceId: "opaque-occurrence", version: 3)]
        for operation in operations {
            let journal = FinancialWriteJournal(storage: storage, prefix: "plan-test")
            let body = Data(#"{"expected_version":3,"reviewed":"exact bytes"}"#.utf8)
            let write = PendingFinancialConfirmation(ownerId: owner, originAccountId: account, route: "financial-plan",
                path: operation.path, method: operation.method, body: body, key: UUID(), planOperation: operation)
            try journal.begin(write, for: identity)
            let restored = FinancialWriteJournal(storage: storage, prefix: "plan-test")
            XCTAssertEqual(try restored.pending(for: identity), write)
            XCTAssertEqual(try restored.pending(for: identity)?.planOperation, operation)
            try restored.clear(write, for: identity)
        }
    }

    func testLegacyPendingEnvelopeRemainsRecoverable() throws {
        let owner = UUID(), account = UUID(), key = UUID()
        let raw = #"{"ownerId":"\#(owner)","originAccountId":"\#(account)","route":"financial-activities","path":"","method":"POST","body":"e30=","key":"\#(key)"}"#
        let legacy = try JSONDecoder().decode(PendingFinancialConfirmation.self, from: Data(raw.utf8))
        XCTAssertNil(legacy.planOperation)
        XCTAssertEqual(legacy.body, Data("{}".utf8))
    }
}
