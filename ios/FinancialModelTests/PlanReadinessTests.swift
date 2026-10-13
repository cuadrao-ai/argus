import Foundation
import XCTest
import ArgusSession
@testable import FinancialModels

/// The founder's PRUEBA_MOVIL steps 10 to 12: each plan names what it still needs, and the rule agrees with the draft that saves.
@MainActor
final class PlanReadinessTests: XCTestCase {
    private let locale = Locale(identifier: "es_DO")
    private let bank = UUID(), cash = UUID(), card = UUID()

    private func missing(_ plan: CanvasPlan, _ details: ConnectedPlanDetails, creatingDebt: Bool = true) -> ConnectedPlanMissing? {
        ConnectedPlanReadiness.missing(plan, details, creatingDebt: creatingDebt, optionsLoaded: true)
    }

    func testBudgetStepTenNamesEachMissingChoiceThenSaves() {
        var plan = CanvasPlan(name: "", kind: .budget)
        var details = ConnectedPlanDetails()
        XCTAssertEqual(missing(plan, details), .name)
        plan.name = "Comida"
        XCTAssertEqual(missing(plan, details), .amount)
        plan.target = 5000
        XCTAssertEqual(missing(plan, details), .accounts)
        details.accountIDs = [bank, cash, card]
        XCTAssertEqual(missing(plan, details), .categories)
        details.categoryIDs = ["groceries"]
        XCTAssertNil(missing(plan, details))
        let draft = FinancialBudgetDraft(month: "2026-10", currency: "DOP")
        ConnectedPlanMapping.apply(plan, details, to: draft, digits: 2, locale: locale)
        XCTAssertTrue(draft.ready)
        XCTAssertEqual(ConnectedPlanReadiness.missing(plan, details, creatingDebt: true, optionsLoaded: false), .loading)
    }

    func testGoalStepElevenSavesWithoutAMonthlyAmountAndNamesAccountsWithOne() {
        var plan = CanvasPlan(name: "Viaje", kind: .goal)
        var details = ConnectedPlanDetails()
        plan.target = 20000
        XCTAssertNil(missing(plan, details))
        let draft = FinancialGoalDraft(start: "2026-10-13", currency: "DOP")
        ConnectedPlanMapping.apply(plan, details, to: draft, digits: 2, locale: locale)
        XCTAssertTrue(draft.ready, "a goal with no monthly amount needs no accounts")
        plan.monthly = 1000
        XCTAssertEqual(missing(plan, details), .destination)
        details.destinationID = bank
        XCTAssertEqual(missing(plan, details), .source)
        details.sourceID = bank
        XCTAssertEqual(missing(plan, details), .sameAccount)
        details.sourceID = cash
        XCTAssertNil(missing(plan, details))
        ConnectedPlanMapping.apply(plan, details, to: draft, digits: 2, locale: locale)
        XCTAssertTrue(draft.ready)
    }

    func testDebtStepTwelveNamesTheCardThePaymentAndThePayingAccount() {
        var plan = CanvasPlan(name: "Tarjeta", kind: .debt)
        var details = ConnectedPlanDetails()
        XCTAssertEqual(missing(plan, details), .debtAccount)
        details.debtAccountID = card
        XCTAssertEqual(missing(plan, details), .monthly)
        plan.monthly = 1000
        XCTAssertEqual(missing(plan, details), .source)
        details.sourceID = bank
        XCTAssertNil(missing(plan, details))
        XCTAssertNil(missing(plan, ConnectedPlanDetails(sourceID: bank), creatingDebt: false), "an edit keeps its card")
    }

    func testEveryReasonHasSpanishAndEnglishText() {
        let all: [ConnectedPlanMissing] = [.name, .amount, .monthly, .debtAccount, .accounts, .categories, .destination, .source, .sameAccount, .loading]
        for reason in all {
            XCTAssertFalse(reason.hint(spanish: true).isEmpty)
            XCTAssertFalse(reason.hint(spanish: false).isEmpty)
            XCTAssertNotEqual(reason.hint(spanish: true), reason.hint(spanish: false))
            XCTAssertFalse(reason.hint(spanish: true).contains("—"))
        }
    }
}
