import Foundation
import Testing
@testable import CuadraoBook

private let moment = Date(timeIntervalSince1970: 1_791_000_000)
private let later = Date(timeIntervalSince1970: 1_791_000_500)
private let zone = "America/Santo_Domingo"

private func make(_ kind: AccountKind = .checking, currency: String = "USD", name: String = "", amount: String = "",
                  share: Int = 10_000, in book: DeviceBook = .empty(), id: UUID = UUID()) throws -> DeviceBook {
    try book.addingAccount(BookAccountDraft(kind: kind, currency: currency, nickname: name, amountText: amount, shareBps: share),
                           id: id, now: moment, zone: zone)
}

@Suite("Account rules")
struct AccountRulesTests {
    @Test func aBlankBalanceIsUnknownAndZeroIsKnown() throws {
        let unknown = try make(amount: "").accounts[0]
        let zero = try make(amount: "0").accounts[0]
        #expect(unknown.opening == nil)
        #expect(unknown.openingBalance == nil)
        #expect(zero.openingBalance == Money(minor: 0, currency: "USD", digits: 2))
        #expect(try make(amount: "   ").accounts[0].opening == nil, "spaces are blank too")
    }

    @Test func amountsKeepTheCurrencysExactDigits() throws {
        #expect(try make(currency: "USD", amount: "1234.56").accounts[0].openingBalance?.minor == 123_456)
        #expect(try make(currency: "JPY", amount: "15000").accounts[0].openingBalance?.minor == 15_000)
        #expect(try make(currency: "KWD", amount: "12.345").accounts[0].openingBalance?.minor == 12_345)
        #expect(try make(currency: "KWD", amount: "12.345").accounts[0].digits == 3)
        #expect(try make(currency: "JPY", amount: "15000").accounts[0].digits == 0)
        #expect(throws: BookRuleError.amount(.precision(digits: 0))) { try make(currency: "JPY", amount: "1.5") }
        #expect(throws: BookRuleError.amount(.precision(digits: 3))) { try make(currency: "KWD", amount: "12.3456") }
        #expect(throws: BookRuleError.amount(.precision(digits: 2))) { try make(currency: "DOP", amount: "0.001") }
        #expect(throws: BookRuleError.amount(.invalid)) { try make(amount: "12,5") }
    }

    @Test func aDebtIsTypedPositiveAndStoredNegativeOnce() throws {
        let card = try make(.creditCard, currency: "DOP", amount: "250.50").accounts[0]
        #expect(card.openingBalance?.minor == -25_050)
        #expect(card.openingBalance?.plain == "-250.50")
        #expect(throws: BookRuleError.negativeAmount) { try make(.otherDebt, amount: "-5") }
        #expect(throws: BookRuleError.negativeAmount) { try make(.property, amount: "-5") }
        #expect(try make(.checking, amount: "-5").accounts[0].openingBalance?.minor == -500, "an overdrawn checking account is allowed")
    }

    @Test func aShareExistsOnlyForOptionalAssets() throws {
        #expect(try make(.property, amount: "100000", share: 5_000).accounts[0].ownershipShareBps == 5_000)
        #expect(try make(.checking, share: 5_000).accounts[0].ownershipShareBps == 10_000, "other types are always whole")
        #expect(throws: BookRuleError.shareInvalid) { try make(.vehicle, share: 0) }
        #expect(throws: BookRuleError.shareInvalid) { try make(.vehicle, share: 10_001) }
    }

    @Test func nicknamesAreTrimmedAndBoundedByCodePoints() throws {
        #expect(try make(name: "  Everyday  ").accounts[0].nickname == "Everyday")
        #expect(try make(name: "   ").accounts[0].nickname == nil)
        #expect(try make(name: String(repeating: "a", count: 60)).accounts[0].nickname?.count == 60)
        #expect(throws: BookRuleError.nicknameTooLong) { try make(name: String(repeating: "a", count: 61)) }
        #expect(throws: BookRuleError.nicknameTooLong) { try make(name: String(repeating: "\u{1F600}", count: 61)) }
    }

    @Test func limitsAndUnsupportedCurrenciesAreRefused() throws {
        #expect(throws: BookRuleError.currencyUnsupported) { try make(currency: "XXX") }
        #expect(throws: BookRuleError.amountTooLarge) { try make(currency: "USD", amount: "10000000000000.01") }
        #expect(try make(currency: "USD", amount: "10000000000000.00").accounts[0].openingBalance?.minor == Limits.maximumMinor)
        var book = DeviceBook.empty()
        for _ in 0..<Limits.accounts { book = try make(in: book) }
        #expect(throws: BookRuleError.accountLimit) { try make(in: book) }
    }

    @Test func currencyAndTypeAreFixedOnceABalanceIsStated() throws {
        let id = UUID()
        let book = try make(.checking, currency: "USD", name: "Main", amount: "10", id: id)
        let change = BookAccountDraft(kind: .checking, currency: "EUR", nickname: "Main", amountText: "10")
        #expect(throws: BookRuleError.currencyLocked) { try book.editingAccount(id, with: change) }
        let retype = BookAccountDraft(kind: .savings, currency: "USD", nickname: "Main", amountText: "10")
        #expect(throws: BookRuleError.kindLocked) { try book.editingAccount(id, with: retype) }
        let rename = BookAccountDraft(kind: .checking, currency: "usd", nickname: "Renamed", amountText: "10")
        #expect(try book.editingAccount(id, with: rename).accounts[0].nickname == "Renamed", "lower case is the same currency")
    }

    @Test func anAccountWithoutABalanceMayChangeCurrencyAndTypeAndTakesTheNewDigits() throws {
        let id = UUID()
        let book = try make(.checking, currency: "USD", id: id)
        let edited = try book.editingAccount(id, with: BookAccountDraft(kind: .cash, currency: "JPY", nickname: "", amountText: "500"))
        #expect(edited.accounts[0].kind == .cash)
        #expect(edited.accounts[0].digits == 0)
        #expect(edited.accounts[0].openingBalance?.minor == 500)
    }

    @Test func clearingTheAmountReturnsToUnknownAndAnUnchangedAmountKeepsItsStart() throws {
        let id = UUID()
        let book = try make(.checking, currency: "USD", amount: "10", id: id)
        let same = BookAccountDraft(kind: .checking, currency: "USD", nickname: "X", amountText: "10.00")
        #expect(try book.editingAccount(id, with: same, now: later, zone: zone).accounts[0].opening?.asOf == moment, "tracking start unchanged")
        let revised = BookAccountDraft(kind: .checking, currency: "USD", nickname: "X", amountText: "11")
        #expect(try book.editingAccount(id, with: revised, now: later, zone: zone).accounts[0].opening?.asOf == later, "a new amount starts tracking now")
        let cleared = BookAccountDraft(kind: .checking, currency: "USD", nickname: "X", amountText: "")
        #expect(try book.editingAccount(id, with: cleared).accounts[0].opening == nil)
    }

    @Test func theStartInstantAndZoneAreStored() throws {
        let opening = try #require(try make(amount: "5").accounts[0].opening)
        #expect(opening.asOf == moment)
        #expect(opening.timeZone == zone)
    }

    @Test func archivingKeepsTheAccountAndItsPlace() throws {
        let ids = [UUID(), UUID(), UUID()]
        var book = DeviceBook.empty()
        for (index, id) in ids.enumerated() { book = try make(name: "A\(index)", in: book, id: id) }
        book = try book.settingArchived(ids[1], true)
        #expect(book.accounts.map(\.id) == ids)
        #expect(book.activeAccounts.map(\.id) == [ids[0], ids[2]])
        #expect(book.archivedAccounts.map(\.id) == [ids[1]])
        book = try book.settingArchived(ids[1], false)
        #expect(book.activeAccounts.map(\.id) == ids, "restored where it was")
        #expect(try book.settingArchived(ids[1], false) == book, "no change, no new revision")
        #expect(throws: BookRuleError.accountNotFound) { try book.settingArchived(UUID(), true) }
    }

    @Test func reorderingMovesOnlyActiveAccountsAndLeavesArchivedInPlace() throws {
        let ids = (0..<4).map { _ in UUID() }
        var book = DeviceBook.empty()
        for (index, id) in ids.enumerated() { book = try make(name: "A\(index)", in: book, id: id) }
        book = try book.settingArchived(ids[1], true)
        let reordered = try book.reorderingActive([ids[3], ids[2], ids[0]])
        #expect(reordered.accounts.map(\.id) == [ids[3], ids[1], ids[2], ids[0]])
        #expect(reordered.activeAccounts.map(\.id) == [ids[3], ids[2], ids[0]])
        #expect(throws: BookRuleError.orderInvalid) { try book.reorderingActive([ids[0], ids[2]]) }
        #expect(throws: BookRuleError.orderInvalid) { try book.reorderingActive([ids[0], ids[1], ids[2]]) }
        #expect(throws: BookRuleError.orderInvalid) { try book.reorderingActive([ids[0], ids[0], ids[2]]) }
    }

    @Test func everyChangeBumpsTheRevision() throws {
        let id = UUID()
        var book = try make(id: id)
        #expect(book.revision == 1)
        book = try book.renamingAccount(id, to: "New")
        book = try book.settingArchived(id, true)
        #expect(book.revision == 3)
    }

    @Test func aStoredBookKeepsEachAccountsOwnDigitsEvenIfTheTableLaterDisagrees() throws {
        let json = """
        {"schemaVersion":1,"revision":2,"settings":{},"accounts":[{"id":"\(UUID().uuidString)","kind":"cash","currency":"JPY",
        "digits":2,"archived":false,"ownershipShareBps":10000,"createdAt":"2026-10-01T00:00:00Z",
        "opening":{"amountMinor":123456,"asOf":"2026-10-01T00:00:00Z","timeZone":"Asia/Tokyo"}}]}
        """
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        let book = try decoder.decode(DeviceBook.self, from: Data(json.utf8))
        #expect(CurrencyTable.digits("JPY") == 0)
        #expect(book.accounts[0].openingBalance?.plain == "1234.56", "read with the digits it was written with")
    }

    @Test func aBookWithAccountsRoundTripsThroughTheStore() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("book-" + UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        var book = try make(.checking, currency: "USD", name: "Main", amount: "1234.56")
        book = try make(.creditCard, currency: "KWD", amount: "12.345", in: book)
        book = try make(.cash, currency: "JPY", amount: "15000", in: book)
        let store = BookStore(directory: directory)
        _ = await store.open()
        try await store.save(book)
        #expect(await BookStore(directory: directory).open() == .existing(book))
    }

    @Test func aBookWrittenBeforeAccountsExistedStillOpens() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("book-" + UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        try Data(#"{"revision":3,"schemaVersion":1,"settings":{"primaryCurrency":"DOP"}}"#.utf8)
            .write(to: directory.appendingPathComponent("book.json"))
        let opened = await BookStore(directory: directory).open()
        #expect(opened == .existing(DeviceBook(revision: 3, settings: BookSettings(primaryCurrency: "DOP"))))
    }
}
