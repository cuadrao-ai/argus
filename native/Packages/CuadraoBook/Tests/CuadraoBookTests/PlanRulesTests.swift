import Foundation
import Testing
@testable import CuadraoBook

private let zone = "America/Santo_Domingo"
private var calendar: Calendar {
    var calendar = Calendar(identifier: .gregorian)
    calendar.timeZone = TimeZone(identifier: zone)!
    return calendar
}
/// 15 October 2026, noon in Santo Domingo.
private let now = calendar.date(from: DateComponents(year: 2026, month: 10, day: 15, hour: 12))!
private func day(_ month: Int, _ day: Int, hour: Int = 10) -> Date {
    calendar.date(from: DateComponents(year: 2026, month: month, day: day, hour: hour))!
}

private struct Fixture {
    var book = DeviceBook.empty()
    let main = UUID(), savings = UUID(), euro = UUID()

    init() throws {
        let opened = day(9, 1)
        book = try book.addingAccount(BookAccountDraft(kind: .checking, currency: "USD", nickname: "Main", amountText: "1000"), id: main, now: opened, zone: zone)
        book = try book.addingAccount(BookAccountDraft(kind: .savings, currency: "USD", nickname: "Savings", amountText: "500"), id: savings, now: opened, zone: zone)
        book = try book.addingAccount(BookAccountDraft(kind: .cash, currency: "EUR", nickname: "Euro", amountText: "100"), id: euro, now: opened, zone: zone)
    }

    func spend(_ account: UUID, _ amount: String, on date: Date, _ category: ExpenseCategory = .other) throws -> DeviceBook {
        try book.recordingMovement(MovementDraft(kind: .expense, accountID: account, amountText: amount, occurredAt: date, category: category), now: now, zone: zone)
    }
}

@Suite("Plan rules")
struct PlanRulesTests {
    @Test func aGoalNeedsANameATargetAndAMonthlyAmount() throws {
        let fixture = try Fixture()
        let draft = BookPlanDraft(kind: .goal, name: "  Trip  ", currency: "USD", targetText: "1500.50", monthlyText: "250")
        let book = try fixture.book.addingPlan(draft, id: UUID(), now: now, zone: zone)
        let plan = try #require(book.plans.first)
        #expect(plan.name == "Trip")
        #expect(plan.targetMinor == 150_050)
        #expect(plan.monthlyMinor == 25_000)
        #expect(plan.timeZone == zone)
        #expect(plan.digits == 2)
        var bad = draft
        bad.name = "   "
        #expect(throws: BookRuleError.planNameEmpty) { try fixture.book.addingPlan(bad, now: now, zone: zone) }
        bad = draft; bad.targetText = "0"
        #expect(throws: BookRuleError.amountNotPositive) { try fixture.book.addingPlan(bad, now: now, zone: zone) }
        bad = draft; bad.monthlyText = ""
        #expect(throws: BookRuleError.amount(.invalid)) { try fixture.book.addingPlan(bad, now: now, zone: zone) }
        bad = draft; bad.targetText = "1.234"
        #expect(throws: BookRuleError.amount(.precision(digits: 2))) { try fixture.book.addingPlan(bad, now: now, zone: zone) }
        bad = draft; bad.name = String(repeating: "x", count: 61)
        #expect(throws: BookRuleError.nicknameTooLong) { try fixture.book.addingPlan(bad, now: now, zone: zone) }
        bad = draft; bad.currency = "XXX"
        #expect(throws: BookRuleError.currencyUnsupported) { try fixture.book.addingPlan(bad, now: now, zone: zone) }
    }

    @Test func aGoalsProgressIsTheContributionsThatStillCount() throws {
        let fixture = try Fixture()
        let planID = UUID()
        var book = try fixture.book.addingPlan(BookPlanDraft(kind: .goal, name: "Trip", currency: "USD", targetText: "1000", monthlyText: "100"), id: planID, now: now, zone: zone)
        #expect(book.goalProgress(planID)?.savedMinor == 0)
        let first = UUID(), second = UUID()
        book = try book.addingContribution(to: planID, amountText: "150.25", occurredAt: day(10, 2), note: " Bonus ", id: first, now: now, zone: zone)
        book = try book.addingContribution(to: planID, amountText: "50", occurredAt: day(10, 10), id: second, now: now, zone: zone)
        let progress = try #require(book.goalProgress(planID))
        #expect(progress.savedMinor == 20_025)
        #expect(progress.remainingMinor == 79_975)
        #expect(!progress.reached)
        #expect(progress.fraction == Decimal(20_025) / Decimal(100_000))
        #expect(book.plan(planID)?.contributions.first?.note == "Bonus")
        book = try book.settingContributionDeleted(first, in: planID, true)
        #expect(book.goalProgress(planID)?.savedMinor == 5_000, "a deleted contribution stops counting")
        book = try book.settingContributionDeleted(first, in: planID, false)
        #expect(book.goalProgress(planID)?.savedMinor == 20_025)
        book = try book.addingContribution(to: planID, amountText: "900", occurredAt: day(10, 12), now: now, zone: zone)
        #expect(book.goalProgress(planID)?.reached == true)
        #expect(book.goalProgress(planID)?.fraction == 1, "the bar stops at full while the amounts keep the truth")
        #expect(book.goalProgress(planID)?.remainingMinor == 0)
        #expect(book.goalProgress(UUID()) == nil)
    }

    @Test func aContributionIsPositiveExactAndNeverFromTheFuture() throws {
        let fixture = try Fixture()
        let planID = UUID()
        let book = try fixture.book.addingPlan(BookPlanDraft(kind: .goal, name: "Trip", currency: "USD", targetText: "1000", monthlyText: "100"), id: planID, now: now, zone: zone)
        #expect(throws: BookRuleError.amountNotPositive) { try book.addingContribution(to: planID, amountText: "0", occurredAt: day(10, 1), now: now, zone: zone) }
        #expect(throws: BookRuleError.amount(.precision(digits: 2))) { try book.addingContribution(to: planID, amountText: "1.005", occurredAt: day(10, 1), now: now, zone: zone) }
        #expect(throws: BookRuleError.futureDate) { try book.addingContribution(to: planID, amountText: "5", occurredAt: day(10, 16), now: now, zone: zone) }
        #expect(throws: BookRuleError.noteTooLong) { try book.addingContribution(to: planID, amountText: "5", occurredAt: day(10, 1), note: String(repeating: "n", count: 201), now: now, zone: zone) }
        #expect(throws: BookRuleError.planNotFound) { try book.addingContribution(to: UUID(), amountText: "5", occurredAt: day(10, 1), now: now, zone: zone) }
        let archived = try book.settingPlanArchived(planID, true)
        #expect(throws: BookRuleError.planArchived) { try archived.addingContribution(to: planID, amountText: "5", occurredAt: day(10, 1), now: now, zone: zone) }
    }

    @Test func aBudgetCountsOnlyExpensesInItsScopeThisMonthInItsOwnZone() throws {
        var fixture = try Fixture()
        fixture.book = try fixture.spend(fixture.main, "100", on: day(10, 3), .groceries)
        fixture.book = try fixture.spend(fixture.savings, "40", on: day(10, 5), .dining)
        fixture.book = try fixture.spend(fixture.main, "999", on: day(9, 20), .groceries)      // last month
        fixture.book = try fixture.spend(fixture.euro, "7", on: day(10, 4), .groceries)         // another currency
        let all = UUID(), mainOnly = UUID(), groceriesOnly = UUID()
        fixture.book = try fixture.book.addingPlan(BookPlanDraft(kind: .budget, name: "All", currency: "USD", targetText: "500"), id: all, now: now, zone: zone)
        fixture.book = try fixture.book.addingPlan(BookPlanDraft(kind: .budget, name: "Main", currency: "USD", targetText: "500", accountScope: [fixture.main]), id: mainOnly, now: now, zone: zone)
        fixture.book = try fixture.book.addingPlan(BookPlanDraft(kind: .budget, name: "Food", currency: "USD", targetText: "90", categoryScope: [.groceries, .dining]), id: groceriesOnly, now: now, zone: zone)
        #expect(fixture.book.budgetStatus(all, now: now)?.spentMinor == 14_000, "every USD account, this month only")
        #expect(fixture.book.budgetStatus(mainOnly, now: now)?.spentMinor == 10_000)
        let food = try #require(fixture.book.budgetStatus(groceriesOnly, now: now))
        #expect(food.spentMinor == 14_000)
        #expect(food.isOver)
        #expect(food.remainingMinor == -5_000)
        #expect(food.fraction == 1)
        let status = try #require(fixture.book.budgetStatus(all, now: now))
        #expect(status.elapsedDays == 15)
        #expect(status.totalDays == 31)
        #expect(status.remainingMinor == 36_000)
        #expect(!status.isOver)
        // Next month starts clean.
        let november = day(11, 2)
        #expect(fixture.book.budgetStatus(all, now: november)?.spentMinor == 0)
        #expect(fixture.book.budgetStatus(UUID(), now: now) == nil)
        #expect(fixture.book.goalProgress(all) == nil, "a budget has no goal progress")
    }

    @Test func aDeletedOrFutureOrIncomeMovementIsNotSpending() throws {
        var fixture = try Fixture()
        let planID = UUID()
        fixture.book = try fixture.book.addingPlan(BookPlanDraft(kind: .budget, name: "All", currency: "USD", targetText: "500"), id: planID, now: now, zone: zone)
        let movementID = UUID()
        fixture.book = try fixture.book.recordingMovement(MovementDraft(kind: .expense, accountID: fixture.main, amountText: "30", occurredAt: day(10, 6)), id: movementID, now: now, zone: zone)
        fixture.book = try fixture.book.recordingMovement(MovementDraft(kind: .income, accountID: fixture.main, amountText: "70", occurredAt: day(10, 6)), now: now, zone: zone)
        #expect(fixture.book.budgetStatus(planID, now: now)?.spentMinor == 3_000)
        fixture.book = try fixture.book.settingMovementDeleted(movementID, true)
        #expect(fixture.book.budgetStatus(planID, now: now)?.spentMinor == 0)
    }

    @Test func aBudgetsScopeMustBeAccountsOfItsCurrency() throws {
        let fixture = try Fixture()
        let draft = BookPlanDraft(kind: .budget, name: "Mixed", currency: "USD", targetText: "10", accountScope: [fixture.euro])
        #expect(throws: BookRuleError.scopeInvalid) { try fixture.book.addingPlan(draft, now: now, zone: zone) }
        var unknown = draft
        unknown.accountScope = [UUID()]
        #expect(throws: BookRuleError.scopeInvalid) { try fixture.book.addingPlan(unknown, now: now, zone: zone) }
        var twice = draft
        twice.accountScope = [fixture.main, fixture.main]
        #expect(try fixture.book.addingPlan(twice, now: now, zone: zone).plans[0].accountScope == [fixture.main])
    }

    @Test func aPlanKeepsItsCurrencyAndKindButEverythingElseCanChange() throws {
        let fixture = try Fixture()
        let planID = UUID()
        let book = try fixture.book.addingPlan(BookPlanDraft(kind: .goal, name: "Trip", currency: "USD", targetText: "1000", monthlyText: "100"), id: planID, now: now, zone: zone)
        let edited = try book.editingPlan(planID, with: BookPlanDraft(kind: .goal, name: "Big trip", currency: "usd", targetText: "2000", monthlyText: "200", look: .sunshine))
        #expect(edited.plan(planID)?.name == "Big trip")
        #expect(edited.plan(planID)?.targetMinor == 200_000)
        #expect(edited.plan(planID)?.look == .sunshine)
        #expect(throws: BookRuleError.currencyLocked) { try book.editingPlan(planID, with: BookPlanDraft(kind: .goal, name: "Trip", currency: "EUR", targetText: "1", monthlyText: "1")) }
        #expect(throws: BookRuleError.planKindLocked) { try book.editingPlan(planID, with: BookPlanDraft(kind: .budget, name: "Trip", currency: "USD", targetText: "1")) }
        #expect(throws: BookRuleError.planNotFound) { try book.editingPlan(UUID(), with: BookPlanDraft(kind: .goal, name: "x", currency: "USD", targetText: "1", monthlyText: "1")) }
    }

    @Test func archivingKeepsAPlanAndReorderingMovesOnlyActiveOnes() throws {
        let fixture = try Fixture()
        let ids = (0..<3).map { _ in UUID() }
        var book = fixture.book
        for (index, id) in ids.enumerated() {
            book = try book.addingPlan(BookPlanDraft(kind: .goal, name: "P\(index)", currency: "USD", targetText: "10", monthlyText: "1"), id: id, now: now, zone: zone)
        }
        book = try book.settingPlanArchived(ids[1], true)
        #expect(book.activePlans.map(\.id) == [ids[0], ids[2]])
        #expect(book.archivedPlans.map(\.id) == [ids[1]])
        let reordered = try book.reorderingActivePlans([ids[2], ids[0]])
        #expect(reordered.plans.map(\.id) == [ids[2], ids[1], ids[0]])
        #expect(throws: BookRuleError.orderInvalid) { try book.reorderingActivePlans([ids[0]]) }
        book = try book.settingPlanArchived(ids[1], false)
        #expect(book.activePlans.map(\.id) == ids)
    }

    @Test func plansRoundTripThroughTheStore() async throws {
        var fixture = try Fixture()
        let planID = UUID()
        fixture.book = try fixture.book.addingPlan(BookPlanDraft(kind: .goal, name: "Trip", currency: "USD", targetText: "1000", monthlyText: "100"), id: planID, now: now, zone: zone)
        fixture.book = try fixture.book.addingContribution(to: planID, amountText: "25", occurredAt: day(10, 2), now: now, zone: zone)
        fixture.book = try fixture.book.addingPlan(BookPlanDraft(kind: .budget, name: "Food", currency: "USD", targetText: "300", accountScope: [fixture.main], categoryScope: [.groceries, .dining]), now: now, zone: zone)
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("book-" + UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = BookStore(directory: directory)
        _ = await store.open()
        try await store.save(fixture.book)
        #expect(await BookStore(directory: directory).open() == .existing(fixture.book))
    }

    @Test func aBookWrittenBeforePlansExistedStillOpens() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("book-" + UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        try Data(#"{"accounts":[],"movements":[],"revision":3,"schemaVersion":1,"settings":{}}"#.utf8).write(to: directory.appendingPathComponent("book.json"))
        #expect(await BookStore(directory: directory).open() == .existing(DeviceBook(revision: 3)))
    }
}
