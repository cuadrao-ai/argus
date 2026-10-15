import Foundation
import Testing
@testable import CuadraoBook

@Suite("Plan calculations")
struct CalculationTests {
    @Test func monthsToGoalCountsWholeMonthsRoundedUp() {
        #expect(PlanCalculator.monthsToGoal(remainingMinor: 100_000, monthlyMinor: 25_000) == 4)
        #expect(PlanCalculator.monthsToGoal(remainingMinor: 100_001, monthlyMinor: 25_000) == 5)
        #expect(PlanCalculator.monthsToGoal(remainingMinor: 1, monthlyMinor: 1_000_000) == 1)
        #expect(PlanCalculator.monthsToGoal(remainingMinor: 0, monthlyMinor: 0) == 0, "nothing left: already there")
        #expect(PlanCalculator.monthsToGoal(remainingMinor: 5, monthlyMinor: 0) == nil, "no contribution never arrives")
        #expect(PlanCalculator.monthsToGoal(remainingMinor: 1_300, monthlyMinor: 1) == nil, "beyond a hundred years is not stated")
        #expect(PlanCalculator.monthsToGoal(remainingMinor: 1_200, monthlyMinor: 1) == 1_200)
    }

    @Test func monthlyNeededRoundsUpToAWholeMinorUnit() {
        #expect(PlanCalculator.monthlyNeeded(remainingMinor: 100_000, months: 4) == 25_000)
        #expect(PlanCalculator.monthlyNeeded(remainingMinor: 100_000, months: 3) == 33_334)
        #expect(PlanCalculator.monthlyNeeded(remainingMinor: 100_000, months: 0) == nil)
        #expect(PlanCalculator.monthlyNeeded(remainingMinor: 0, months: 3) == nil)
        // Paying the needed amount really finishes in time, and one unit less does not.
        for (remaining, months) in [(100_000 as Int64, 7), (999_999, 12), (1, 3)] {
            let needed = PlanCalculator.monthlyNeeded(remainingMinor: remaining, months: months)!
            #expect(PlanCalculator.monthsToGoal(remainingMinor: remaining, monthlyMinor: needed)! <= months)
            if needed > 1 { #expect(PlanCalculator.monthsToGoal(remainingMinor: remaining, monthlyMinor: needed - 1)! > months || needed - 1 == 0) }
        }
    }

    @Test func monthEndPaceIsSpentOverDaysElapsedTimesDaysInMonthRoundedHalfEven() {
        #expect(PlanCalculator.monthEndPace(spentMinor: 14_000, elapsedDays: 14, totalDays: 31) == 31_000)
        #expect(PlanCalculator.monthEndPace(spentMinor: 100, elapsedDays: 3, totalDays: 30) == 1_000)
        #expect(PlanCalculator.monthEndPace(spentMinor: 5, elapsedDays: 2, totalDays: 31) == 78, "77.5 rounds to the even 78")
        #expect(PlanCalculator.monthEndPace(spentMinor: 7, elapsedDays: 2, totalDays: 31) == 108, "108.5 rounds to the even 108")
        #expect(PlanCalculator.monthEndPace(spentMinor: 0, elapsedDays: 5, totalDays: 30) == 0)
        #expect(PlanCalculator.monthEndPace(spentMinor: 10, elapsedDays: 0, totalDays: 30) == nil)
        #expect(PlanCalculator.monthEndPace(spentMinor: 10, elapsedDays: 31, totalDays: 30) == nil)
        #expect(PlanCalculator.monthEndPace(spentMinor: Limits.maximumMinor, elapsedDays: 1, totalDays: 31) == Limits.maximumMinor * 31)
    }

    @Test func theCompletionMonthIsReadInTheGivenZoneWithNoSampleDate() throws {
        let zone = try #require(TimeZone(identifier: "America/Santo_Domingo"))
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = zone
        let start = calendar.date(from: DateComponents(year: 2026, month: 11, day: 15))!
        let end = try #require(PlanCalculator.completionMonth(after: 3, from: start, zone: zone))
        #expect(calendar.component(.month, from: end) == 2)
        #expect(calendar.component(.year, from: end) == 2027)
    }

    @Test func totalsKeepAssetsOwedAndTheNetApartAfterShares() throws {
        let now = Date(timeIntervalSince1970: 1_791_000_000)
        var book = DeviceBook.empty()
        book = try book.addingAccount(BookAccountDraft(kind: .checking, currency: "USD", amountText: "1000"), id: UUID(), now: now, zone: "UTC")
        book = try book.addingAccount(BookAccountDraft(kind: .creditCard, currency: "USD", amountText: "250.50"), id: UUID(), now: now, zone: "UTC")
        book = try book.addingAccount(BookAccountDraft(kind: .property, currency: "USD", amountText: "1001", shareBps: 5_000), id: UUID(), now: now, zone: "UTC")
        book = try book.addingAccount(BookAccountDraft(kind: .cash, currency: "USD"), id: UUID(), now: now, zone: "UTC")
        book = try book.addingAccount(BookAccountDraft(kind: .cash, currency: "JPY", amountText: "500"), id: UUID(), now: now, zone: "UTC")
        let usd = try #require(book.totals(currency: "USD"))
        #expect(usd.assetsMinor == 100_000 + 50_050)
        #expect(usd.owedMinor == 25_050)
        #expect(usd.netMinor == 125_000)
        #expect(usd.knownAccounts == 3)
        #expect(usd.unknownAccounts == 1, "an unknown balance is counted, not guessed")
        #expect(usd.netMinor == book.netBalance(currency: "USD")?.minor, "the totals and the hero agree")
        let yen = try #require(book.totals(currency: "JPY"))
        #expect(yen.digits == 0)
        #expect(yen.netMinor == 500)
        #expect(book.totals(currency: "EUR") == nil)
    }
}

@Suite("Search index")
struct SearchIndexTests {
    private func entry(_ words: String..., section: SearchSection = .accounts, currency: String = "USD") -> SearchEntry {
        SearchEntry(id: UUID(), section: section, text: words, currency: currency)
    }

    @Test func caseAccentsAndWidthDoNotMatter() {
        let entries = [entry("Ahorros para el Año Nuevo"), entry("Cuenta corriente"), entry("ＡＨＯＲＲＯＳ")]
        #expect(SearchIndex.filter(entries, query: "AÑO").count == 1)
        #expect(SearchIndex.filter(entries, query: "ano nuevo").count == 1)
        #expect(SearchIndex.filter(entries, query: "ahorros").count == 2)
        #expect(SearchIndex.filter(entries, query: "corriénte").count == 1)
    }

    @Test func everyWordMustAppearAndAnEmptyQueryKeepsEverythingInOrder() {
        let entries = [entry("Main", "Checking", "USD"), entry("Savings", "USD"), entry("Cash", "JPY")]
        #expect(SearchIndex.filter(entries, query: "main usd").count == 1)
        #expect(SearchIndex.filter(entries, query: "usd").count == 2)
        #expect(SearchIndex.filter(entries, query: "main jpy").isEmpty)
        #expect(SearchIndex.filter(entries, query: "   ") == entries)
        #expect(SearchIndex.filter(entries, query: "") == entries)
        #expect(SearchIndex.filter(entries, query: "usd").map(\.id) == [entries[0].id, entries[1].id], "order is the host's")
    }

    @Test func aScopeAndACurrencyNarrowTheResults() {
        let account = entry("Main", section: .accounts)
        let spending = entry("Lunch", "Main", section: .activity)
        let plan = entry("Trip", section: .plans, currency: "EUR")
        let all = [account, spending, plan]
        #expect(SearchIndex.filter(all, query: "", scope: .accounts) == [account])
        #expect(SearchIndex.filter(all, query: "", scope: .activity) == [spending])
        #expect(SearchIndex.filter(all, query: "", scope: .plans) == [plan])
        #expect(SearchIndex.filter(all, query: "main", scope: .all) == [account, spending])
        #expect(SearchIndex.filter(all, query: "", currency: "EUR") == [plan])
        #expect(SearchIndex.filter(all, query: "main", scope: .activity, currency: "USD") == [spending])
        #expect(SearchIndex.filter(all, query: "main", scope: .plans).isEmpty)
    }

    @Test func amountsAreSearchableAsTheyAreWritten() {
        let entries = [entry("Coffee", "12.34", "12,34")]
        #expect(SearchIndex.filter(entries, query: "12.34").count == 1)
        #expect(SearchIndex.filter(entries, query: "12,34").count == 1)
        #expect(SearchIndex.filter(entries, query: "12.35").isEmpty)
    }
}
