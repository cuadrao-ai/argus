import Foundation
import Testing
@testable import CuadraoBook

private let zone = "America/Santo_Domingo"
private let start = Date(timeIntervalSince1970: 1_791_000_000)          // when balances are stated
private let hour: TimeInterval = 3_600
private let now = start.addingTimeInterval(10 * 24 * hour)

private struct Fixture {
    var book = DeviceBook.empty()
    let main = UUID(), savings = UUID(), other = UUID(), euro = UUID()

    init() throws {
        book = try book.addingAccount(BookAccountDraft(kind: .checking, currency: "USD", nickname: "Main", amountText: "1000"), id: main, now: start, zone: zone)
        book = try book.addingAccount(BookAccountDraft(kind: .savings, currency: "USD", nickname: "Savings", amountText: "500"), id: savings, now: start, zone: zone)
        book = try book.addingAccount(BookAccountDraft(kind: .cash, currency: "USD", nickname: "Unknown"), id: other, now: start, zone: zone)
        book = try book.addingAccount(BookAccountDraft(kind: .checking, currency: "EUR", nickname: "Euro", amountText: "10"), id: euro, now: start, zone: zone)
    }

    func record(_ kind: MovementKind, _ account: UUID, _ amount: String, counterpart: UUID? = nil, daysAfter: Double = 1,
                note: String = "", category: ExpenseCategory = .other, id: UUID = UUID()) throws -> DeviceBook {
        try book.recordingMovement(MovementDraft(kind: kind, accountID: account, counterpartID: counterpart, amountText: amount,
                                                 occurredAt: start.addingTimeInterval(daysAfter * 24 * hour), note: note, category: category),
                                   id: id, now: now, zone: zone)
    }
}

@Suite("Movement rules")
struct MovementRulesTests {
    @Test func anExpenseLowersAndAnIncomeRaisesTheDerivedBalance() throws {
        var fixture = try Fixture()
        fixture.book = try fixture.record(.expense, fixture.main, "12.34")
        #expect(fixture.book.balance(of: fixture.main)?.minor == 98_766)
        fixture.book = try fixture.record(.income, fixture.main, "50")
        #expect(fixture.book.balance(of: fixture.main)?.minor == 103_766)
        #expect(fixture.book.account(fixture.main)?.openingBalance?.minor == 100_000, "the stated balance is not rewritten")
    }

    @Test func aTransferMovesMoneyBetweenTwoAccountsOfTheSameCurrencyOnly() throws {
        var fixture = try Fixture()
        fixture.book = try fixture.record(.transfer, fixture.main, "200", counterpart: fixture.savings)
        #expect(fixture.book.balance(of: fixture.main)?.minor == 80_000)
        #expect(fixture.book.balance(of: fixture.savings)?.minor == 70_000)
        #expect(fixture.book.netBalance(currency: "USD")?.minor == 150_000, "a transfer changes no total")
        #expect(throws: BookRuleError.transferCurrencyMismatch) { try fixture.record(.transfer, fixture.main, "1", counterpart: fixture.euro) }
        #expect(throws: BookRuleError.transferSameAccount) { try fixture.record(.transfer, fixture.main, "1", counterpart: fixture.main) }
        #expect(throws: BookRuleError.accountNotFound) { try fixture.record(.transfer, fixture.main, "1", counterpart: nil) }
    }

    @Test func aMovementOnAnUnknownBalanceStaysUnknown() throws {
        var fixture = try Fixture()
        fixture.book = try fixture.record(.expense, fixture.other, "20", daysAfter: 2)
        #expect(fixture.book.balance(of: fixture.other) == nil, "twenty spent from an unknown balance is still unknown, not minus twenty")
        let net = try #require(fixture.book.netBalance(currency: "USD"))
        #expect(net.minor == 150_000)
        #expect(net.knownAccounts == 2)
        #expect(net.unknownAccounts == 1)
        #expect(net.isPartial)
    }

    @Test func aMovementMustBePositiveExactAndNotInTheFuture() throws {
        let fixture = try Fixture()
        #expect(throws: BookRuleError.amountNotPositive) { try fixture.record(.expense, fixture.main, "0") }
        #expect(throws: BookRuleError.amountNotPositive) { try fixture.record(.expense, fixture.main, "-5") }
        #expect(throws: BookRuleError.amount(.precision(digits: 2))) { try fixture.record(.expense, fixture.main, "1.005") }
        #expect(throws: BookRuleError.amountTooLarge) { try fixture.record(.expense, fixture.main, "10000000000000.01") }
        #expect(throws: BookRuleError.futureDate) { try fixture.record(.expense, fixture.main, "1", daysAfter: 11) }
        #expect(try fixture.record(.expense, fixture.main, "1", daysAfter: 10).movements.count == 1, "right now is allowed")
    }

    @Test func aMovementCannotPredateTheBalanceItWouldAlreadyBeInside() throws {
        let fixture = try Fixture()
        #expect(throws: BookRuleError.beforeTracking) { try fixture.record(.expense, fixture.main, "1", daysAfter: -1) }
        #expect(throws: BookRuleError.beforeTracking) { try fixture.record(.transfer, fixture.other, "1", counterpart: fixture.main, daysAfter: -1) }
        // An account with no stated balance has no start to predate.
        let free = try fixture.book.addingAccount(BookAccountDraft(kind: .cash, currency: "DOP"), id: UUID(), now: start, zone: zone)
        let id = try #require(free.accounts.last?.id)
        let early = MovementDraft(kind: .expense, accountID: id, amountText: "5", occurredAt: start.addingTimeInterval(-30 * 24 * hour))
        #expect(try free.recordingMovement(early, now: now, zone: zone).movements.count == 1)
    }

    @Test func anArchivedAccountTakesNoNewMovements() throws {
        var fixture = try Fixture()
        fixture.book = try fixture.book.settingArchived(fixture.savings, true)
        #expect(throws: BookRuleError.accountArchived) { try fixture.record(.expense, fixture.savings, "1") }
        #expect(throws: BookRuleError.accountArchived) { try fixture.record(.transfer, fixture.main, "1", counterpart: fixture.savings) }
    }

    @Test func notesAreBoundedAndOnlyExpensesCarryACategory() throws {
        let fixture = try Fixture()
        #expect(throws: BookRuleError.noteTooLong) { try fixture.record(.expense, fixture.main, "1", note: String(repeating: "x", count: 201)) }
        let income = try fixture.record(.income, fixture.main, "1", category: .groceries).movements[0]
        #expect(income.category == nil)
        let expense = try fixture.record(.expense, fixture.main, "1", note: "  Milk  ", category: .groceries).movements[0]
        #expect(expense.category == .groceries)
        #expect(expense.note == "Milk")
        #expect(expense.timeZone == zone, "the device zone is stored with the instant")
    }

    @Test func editingChangesAMovementAndDeletingIsReversible() throws {
        let fixture = try Fixture()
        let id = UUID()
        var book = try fixture.record(.expense, fixture.main, "10", id: id)
        let draft = MovementDraft(kind: .expense, accountID: fixture.main, amountText: "25", occurredAt: start.addingTimeInterval(2 * 24 * hour), note: "Fixed")
        book = try book.editingMovement(id, with: draft, now: now, zone: zone)
        #expect(book.balance(of: fixture.main)?.minor == 97_500)
        book = try book.settingMovementDeleted(id, true)
        #expect(book.balance(of: fixture.main)?.minor == 100_000, "a deleted movement no longer counts")
        #expect(book.liveMovements().isEmpty)
        #expect(book.movements.count == 1, "it stays in the book so the delete can be undone")
        #expect(throws: BookRuleError.movementNotFound) { try book.editingMovement(id, with: draft, now: now, zone: zone) }
        book = try book.settingMovementDeleted(id, false)
        #expect(book.balance(of: fixture.main)?.minor == 97_500)
        #expect(throws: BookRuleError.movementNotFound) { try book.settingMovementDeleted(UUID(), true) }
    }

    @Test func movementsFixTheCurrencyAndTypeEvenAfterTheyAreDeleted() throws {
        var fixture = try Fixture()
        let id = UUID()
        fixture.book = try fixture.record(.expense, fixture.other, "5", daysAfter: 2, id: id)
        #expect(fixture.book.hasRecords(fixture.other))
        let change = BookAccountDraft(kind: .cash, currency: "EUR", nickname: "Unknown", amountText: "")
        #expect(throws: BookRuleError.currencyLocked) { try fixture.book.editingAccount(fixture.other, with: change) }
        fixture.book = try fixture.book.settingMovementDeleted(id, true)
        #expect(fixture.book.hasRecords(fixture.other), "history is not forgotten")
    }

    @Test func restatingTheBalanceStartsTrackingAgainFromNow() throws {
        var fixture = try Fixture()
        fixture.book = try fixture.record(.expense, fixture.main, "100", daysAfter: 1)
        let current = try #require(fixture.book.balance(of: fixture.main)?.minor)
        #expect(current == 90_000)
        let same = BookAccountDraft(kind: .checking, currency: "USD", nickname: "Main", amountText: "900")
        let kept = try fixture.book.editingAccount(fixture.main, with: same, now: now, zone: zone)
        #expect(kept.account(fixture.main)?.opening?.asOf == start, "the balance the person reads is unchanged, so nothing restarts")
        let corrected = BookAccountDraft(kind: .checking, currency: "USD", nickname: "Main", amountText: "850")
        let restated = try fixture.book.editingAccount(fixture.main, with: corrected, now: now, zone: zone)
        #expect(restated.account(fixture.main)?.opening?.asOf == now)
        #expect(restated.balance(of: fixture.main)?.minor == 85_000, "the earlier expense is inside the new balance, not applied twice")
    }

    @Test func theNetBalanceAppliesOwnershipSharesAndKeepsCurrenciesApart() throws {
        var fixture = try Fixture()
        let house = UUID()
        fixture.book = try fixture.book.addingAccount(BookAccountDraft(kind: .property, currency: "USD", amountText: "1001", shareBps: 5_000), id: house, now: start, zone: zone)
        let usd = try #require(fixture.book.netBalance(currency: "USD"))
        #expect(usd.minor == 200_050, "half of 1001.00 added to the other accounts")
        #expect(fixture.book.netBalance(currency: "EUR")?.minor == 1_000)
        #expect(fixture.book.netBalance(currency: "JPY") == nil)
        #expect(fixture.book.currencies == ["USD", "EUR"], "the first account's currency leads until one is preferred")
        fixture.book = try fixture.book.settingPrimaryCurrency("EUR")
        #expect(fixture.book.currencies == ["EUR", "USD"], "the preferred currency leads")
    }

    @Test func aCreditCardPaymentRaisesTheDebtsBalanceTowardZero() throws {
        var fixture = try Fixture()
        let card = UUID()
        fixture.book = try fixture.book.addingAccount(BookAccountDraft(kind: .creditCard, currency: "USD", amountText: "300"), id: card, now: start, zone: zone)
        #expect(fixture.book.balance(of: card)?.minor == -30_000)
        fixture.book = try fixture.record(.transfer, fixture.main, "100", counterpart: card)
        #expect(fixture.book.balance(of: card)?.minor == -20_000, "owing 200 now")
        fixture.book = try fixture.record(.expense, card, "50")
        #expect(fixture.book.balance(of: card)?.minor == -25_000, "a purchase on the card raises what is owed")
    }

    @Test func dailyBalancesFollowEachDayAndHoldBetweenEvents() throws {
        var fixture = try Fixture()
        fixture.book = try fixture.record(.expense, fixture.main, "100", daysAfter: 2)
        fixture.book = try fixture.record(.income, fixture.savings, "40", daysAfter: 5)
        let utc = try #require(TimeZone(identifier: "UTC"))
        let series = try #require(fixture.book.dailyBalances(currency: "USD", zone: utc, now: now))
        #expect(series.first?.minor == 150_000, "the day balances were stated")
        #expect(series.last?.minor == fixture.book.netBalance(currency: "USD")?.minor, "today's point is the hero")
        #expect(series.map(\.day) == series.map(\.day).sorted())
        #expect(Set(series.map(\.day)).count == series.count, "one point per day")
        #expect(series.contains { $0.minor == 140_000 }, "the day of the expense")
        #expect(series.contains { $0.minor == 144_000 }, "the day of the income")
        #expect(fixture.book.dailyBalances(currency: "JPY", zone: utc, now: now)?.isEmpty == true)
    }

    @Test func spendingBeginsWhereCoverageBeginsAndNeverClaimsZeroBeforeIt() throws {
        var fixture = try Fixture()
        fixture.book = try fixture.record(.expense, fixture.main, "30", daysAfter: 1, category: .groceries)
        fixture.book = try fixture.record(.expense, fixture.main, "10", daysAfter: 2, category: .dining)
        fixture.book = try fixture.record(.expense, fixture.savings, "5", daysAfter: 2, category: .groceries)
        fixture.book = try fixture.record(.income, fixture.main, "99", daysAfter: 2)
        fixture.book = try fixture.book.settingArchived(fixture.other, true)
        let window = DateInterval(start: start, end: start.addingTimeInterval(5 * 24 * hour))
        guard case .recorded(let summary)? = fixture.book.spending(currency: "USD", in: window) else { Issue.record("expected recorded"); return }
        #expect(summary.totalMinor == 4_500, "income and transfers are not spending")
        #expect(summary.byCategory.map(\.category) == [.groceries, .dining])
        #expect(summary.byCategory.map(\.minor) == [3_500, 1_000])
        #expect(summary.coverageStart == nil, "coverage began before the window")
        #expect(fixture.book.spending(currency: "USD", in: DateInterval(start: start.addingTimeInterval(-40 * 24 * hour), end: start.addingTimeInterval(-10 * 24 * hour))) == .noData,
                "before coverage there is no data, not a known zero")
        let partial = fixture.book.spending(currency: "USD", in: DateInterval(start: start.addingTimeInterval(-5 * 24 * hour), end: start.addingTimeInterval(5 * 24 * hour)))
        guard case .recorded(let straddling)? = partial else { Issue.record("expected recorded"); return }
        #expect(straddling.coverageStart == start, "coverage starts inside this window")
        #expect(fixture.book.spending(currency: "JPY", in: window) == nil)
    }

    @Test func aCurrencyWithAnUntrackedAccountHasNoSpendingCoverage() throws {
        var fixture = try Fixture()
        fixture.book = try fixture.book.settingArchived(fixture.other, false)
        #expect(fixture.book.spendingCoverageStart(currency: "USD") == nil, "the unknown cash account has no start yet")
        fixture.book = try fixture.record(.expense, fixture.other, "5", daysAfter: 3)
        #expect(fixture.book.spendingCoverageStart(currency: "USD") == start.addingTimeInterval(3 * 24 * hour), "the latest of the starts")
    }

    @Test func aBookWithMovementsRoundTripsThroughTheStore() async throws {
        var fixture = try Fixture()
        fixture.book = try fixture.record(.expense, fixture.main, "12.34", note: "Lunch", category: .dining)
        fixture.book = try fixture.record(.transfer, fixture.main, "5", counterpart: fixture.savings)
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("book-" + UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = BookStore(directory: directory)
        _ = await store.open()
        try await store.save(fixture.book)
        #expect(await BookStore(directory: directory).open() == .existing(fixture.book))
    }
}
