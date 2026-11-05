import Foundation
import Testing
@testable import CuadraoBook

private let moment = Date(timeIntervalSince1970: 1_791_000_000)
private let zone = "America/Santo_Domingo"

private func book(_ build: (inout DeviceBook) throws -> Void) rethrows -> DeviceBook {
    var value = DeviceBook.empty()
    try build(&value)
    return value
}

private func add(_ book: inout DeviceBook, _ kind: AccountKind = .checking, _ name: String, currency: String = "DOP",
                 amount: String = "", id: UUID = UUID()) throws {
    book = try book.addingAccount(BookAccountDraft(kind: kind, currency: currency, nickname: name, amountText: amount),
                                  id: id, now: moment, zone: zone)
}

@Suite("Guest claim plan")
struct GuestClaimTests {
    @Test func countsWhatWillMoveAndWhatStays() throws {
        let main = UUID(), card = UUID()
        var value = DeviceBook.empty()
        try add(&value, .checking, "Main", amount: "1000", id: main)
        try add(&value, .creditCard, "Card", amount: "250.50", id: card)
        value = try value.recordingMovement(MovementDraft(kind: .expense, accountID: main, amountText: "20", occurredAt: moment.addingTimeInterval(60)),
                                            now: moment.addingTimeInterval(120), zone: zone)
        value = try value.addingPlan(BookPlanDraft(kind: .budget, name: "Food", currency: "DOP", targetText: "300"), now: moment, zone: zone)
        let plan = GuestClaimPlan.make(book: value, existingNicknames: [])
        #expect(plan.accounts.count == 2)
        #expect(plan.movements.count == 1)
        #expect(plan.stayingPlans == 1)
        #expect(plan.renamedAccounts == 0)
        #expect(!plan.isEmpty)
        #expect(GuestClaimPlan.make(book: .empty(), existingNicknames: ["x"]).isEmpty)
    }

    @Test func aDebtGoesAsAPositiveAmountAndAnUnknownBalanceStaysUnknown() throws {
        var value = DeviceBook.empty()
        try add(&value, .creditCard, "Card", amount: "250.50")
        try add(&value, .cash, "Wallet", amount: "")
        try add(&value, .savings, "Zero", amount: "0")
        let plan = GuestClaimPlan.make(book: value, existingNicknames: [])
        #expect(plan.accounts[0].amountText == "250.50", "the server takes a debt typed positive")
        #expect(plan.accounts[1].amountText == nil, "an unknown balance is not zero")
        #expect(plan.accounts[1].asOf == nil)
        #expect(plan.accounts[2].amountText == "0.00", "zero is a known balance")
        #expect(plan.accounts[0].asOf == moment)
        #expect(plan.accounts[0].timeZone == zone)
    }

    @Test func aTakenNameComesInAsInvitadoAndTheCopyIsNeverSilentlyMerged() throws {
        var value = DeviceBook.empty()
        try add(&value, .checking, "Main")
        try add(&value, .savings, "Ahorros del año")
        try add(&value, .cash, "Wallet")
        let plan = GuestClaimPlan.make(book: value, existingNicknames: ["main", " AHORROS DEL AÑO "])
        #expect(plan.accounts.map(\.nickname) == ["Main (invitado)", "Ahorros del año (invitado)", "Wallet"])
        #expect(plan.accounts.map(\.renamed) == [true, true, false])
        #expect(plan.renamedAccounts == 2)
        let accents = GuestClaimPlan.make(book: value, existingNicknames: ["ahorros del ano"])
        #expect(accents.accounts[1].renamed, "accents and case do not make a different name")
    }

    @Test func aSecondCollisionGetsANumberAndTwoGuestAccountsNeverShareAName() throws {
        var value = DeviceBook.empty()
        try add(&value, .checking, "Main")
        try add(&value, .checking, "Main")
        let plan = GuestClaimPlan.make(book: value, existingNicknames: ["Main", "Main (invitado)"])
        #expect(plan.accounts.map(\.nickname) == ["Main (invitado 2)", "Main (invitado 3)"])
        let twoGuests = GuestClaimPlan.make(book: value, existingNicknames: [])
        #expect(twoGuests.accounts.map(\.nickname) == ["Main", "Main (invitado)"], "the second guest Main would repeat the first")
    }

    @Test func theNewNameStaysInsideTheNicknameLimit() throws {
        let long = String(repeating: "a", count: Limits.nickname)
        var value = DeviceBook.empty()
        try add(&value, .checking, long)
        let plan = GuestClaimPlan.make(book: value, existingNicknames: [long])
        let name = try #require(plan.accounts[0].nickname)
        #expect(name.unicodeScalars.count <= Limits.nickname)
        #expect(name.hasSuffix(" (invitado)"))
    }

    @Test func englishUsesItsOwnWord() throws {
        var value = DeviceBook.empty()
        try add(&value, .checking, "Main")
        #expect(GuestClaimPlan.make(book: value, existingNicknames: ["Main"], guestWord: "guest").accounts[0].nickname == "Main (guest)")
    }

    @Test func deletedMovementsAreLeftOutAndTheRestGoOldestFirst() throws {
        let main = UUID(), other = UUID()
        var value = DeviceBook.empty()
        try add(&value, .checking, "Main", amount: "100", id: main)
        try add(&value, .savings, "Other", amount: "0", id: other)
        let first = UUID(), second = UUID(), gone = UUID()
        value = try value.recordingMovement(MovementDraft(kind: .income, accountID: main, amountText: "5", occurredAt: moment.addingTimeInterval(300)), id: second, now: moment.addingTimeInterval(400), zone: zone)
        value = try value.recordingMovement(MovementDraft(kind: .expense, accountID: main, amountText: "1", occurredAt: moment.addingTimeInterval(100)), id: first, now: moment.addingTimeInterval(400), zone: zone)
        value = try value.recordingMovement(MovementDraft(kind: .transfer, accountID: main, counterpartID: other, amountText: "2.50", occurredAt: moment.addingTimeInterval(200)), id: gone, now: moment.addingTimeInterval(400), zone: zone)
        value = try value.settingMovementDeleted(gone, true)
        let plan = GuestClaimPlan.make(book: value, existingNicknames: [])
        #expect(plan.movements.map(\.id) == [first, second])
        #expect(plan.movements[0].amountText == "1.00")
        #expect(plan.movements[0].category == .other)
        #expect(plan.movements[1].category == nil, "only an expense carries a category")
    }

    @Test func aTransferKeepsItsTwoAccountsAndTheCurrencyDigits() throws {
        let a = UUID(), b = UUID()
        var value = DeviceBook.empty()
        try add(&value, .checking, "A", currency: "USD", amount: "10", id: a)
        try add(&value, .savings, "B", currency: "USD", amount: "0", id: b)
        value = try value.recordingMovement(MovementDraft(kind: .transfer, accountID: a, counterpartID: b, amountText: "2.5", occurredAt: moment.addingTimeInterval(10)), now: moment.addingTimeInterval(20), zone: zone)
        let item = try #require(GuestClaimPlan.make(book: value, existingNicknames: []).movements.first)
        #expect(item.accountID == a)
        #expect(item.counterpartID == b)
        #expect(item.counterpartKind == .savings, "the receiving account's type travels with the movement")
        #expect(item.amountText == "2.50")
    }

    @Test func archivedAccountsAndUnnamedAccountsKeepTheirState() throws {
        let id = UUID()
        var value = DeviceBook.empty()
        try add(&value, .cash, "", id: id)
        value = try value.settingArchived(id, true)
        let plan = GuestClaimPlan.make(book: value, existingNicknames: [""])
        #expect(plan.accounts[0].archived)
        #expect(plan.accounts[0].nickname == nil, "an unnamed account is not renamed")
        #expect(!plan.accounts[0].renamed)
    }

    @Test func progressIsKeptPerOwnerAndRoundTrips() throws {
        let owner = UUID(), stranger = UUID(), guest = UUID(), server = UUID(), movement = UUID()
        var progress = GuestClaimProgress()
        progress.owners[owner] = .init(accounts: [guest: server], movements: [movement], refused: [])
        let data = try JSONEncoder().encode(progress)
        let back = try JSONDecoder().decode(GuestClaimProgress.self, from: data)
        #expect(back == progress)
        #expect(back.owner(owner).accounts[guest] == server)
        #expect(back.owner(stranger) == GuestClaimProgress.Owner(), "another person starts from nothing")
    }
}
