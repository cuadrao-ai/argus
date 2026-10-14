import ArgusSession
import CuadraoBook
import XCTest
@testable import FinancialModels

private let moment = Date(timeIntervalSince1970: 1_791_000_000)
private let tzName = "America/Santo_Domingo"

private struct Fixture {
    let main = UUID(), card = UUID(), savings = UUID(), shelved = UUID()
    var book = DeviceBook.empty()

    init() throws {
        book = try book.addingAccount(BookAccountDraft(kind: .checking, currency: "DOP", nickname: "Main", amountText: "1000"), id: main, now: moment, zone: tzName)
        book = try book.addingAccount(BookAccountDraft(kind: .creditCard, currency: "DOP", nickname: "Card", amountText: "250.50"), id: card, now: moment, zone: tzName)
        book = try book.addingAccount(BookAccountDraft(kind: .savings, currency: "DOP", nickname: "Savings"), id: savings, now: moment, zone: tzName)
        book = try book.addingAccount(BookAccountDraft(kind: .cash, currency: "DOP", nickname: "Old wallet", amountText: "5"), id: shelved, now: moment, zone: tzName)
        book = try book.settingArchived(shelved, true)
        book = try book.recordingMovement(MovementDraft(kind: .expense, accountID: main, amountText: "20", occurredAt: moment.addingTimeInterval(60),
                                                        note: "Taxi", category: .transport), now: moment.addingTimeInterval(500), zone: tzName)
        book = try book.recordingMovement(MovementDraft(kind: .income, accountID: main, amountText: "300", occurredAt: moment.addingTimeInterval(120),
                                                        note: "Pay"), now: moment.addingTimeInterval(500), zone: tzName)
        book = try book.recordingMovement(MovementDraft(kind: .transfer, accountID: main, counterpartID: card, amountText: "50", occurredAt: moment.addingTimeInterval(180),
                                                        note: "Pay card"), now: moment.addingTimeInterval(500), zone: tzName)
    }

    func plan(existing: [String] = []) -> GuestClaimPlan { GuestClaimPlan.make(book: book, existingNicknames: existing) }
}

final class GuestClaimEngineTests: XCTestCase {
    func testMovesAccountsThenMovementsAndRecordsEachConfirmedItem() async throws {
        let fixture = try Fixture()
        let server = SampleGuestClaimServer()
        let saved = Saved()
        let engine = GuestClaimEngine(server: server, save: { saved.progress = $0 })
        let (result, progress) = await engine.run(plan: fixture.plan(), progress: GuestClaimProgress())
        XCTAssertTrue(result.completed)
        XCTAssertEqual(result.accountsMoved, 4)
        XCTAssertEqual(result.movementsMoved, 3)
        let created = await server.createdAccounts
        let confirmed = await server.confirmedMovements
        XCTAssertEqual(created, 4)
        XCTAssertEqual(confirmed, 3)
        let owner = await server.ownerID
        XCTAssertEqual(progress.owner(owner).accounts.count, 4)
        XCTAssertEqual(progress.owner(owner).movements.count, 3)
        XCTAssertEqual(saved.progress, progress, "the last saved progress is the final one")
    }

    func testSendsTheBookAsTheServerTakesIt() async throws {
        let fixture = try Fixture()
        let server = SampleGuestClaimServer(script: .init(existingNames: ["main"]))
        let engine = GuestClaimEngine(server: server)
        _ = await engine.run(plan: fixture.plan(existing: ["main"]), progress: GuestClaimProgress())
        let requests = await server.requests
        let byName = Dictionary(uniqueKeysWithValues: requests.compactMap { request in request.nickname.map { ($0, request) } })
        XCTAssertEqual(byName["Main (invitado)"]?.amount, "1000.00", "a taken name arrives marked, not merged")
        XCTAssertEqual(byName["Card"]?.amount, "250.50", "a debt is sent positive")
        XCTAssertEqual(byName["Card"]?.type, "credit_card")
        XCTAssertNil(byName["Savings"]?.amount, "an unknown balance is not sent as zero")
        XCTAssertNil(byName["Savings"]?.asOf)
        XCTAssertNotNil(byName["Main (invitado)"]?.asOf)
        XCTAssertEqual(byName["Main (invitado)"]?.timeZone, tzName)
        let commands = await server.commands
        XCTAssertEqual(commands.map(\.kind), [.expense, .income, .cardPayment], "oldest first; money moved into a credit card is a card payment")
        XCTAssertEqual(commands[0].categoryId, "transport")
        XCTAssertNil(commands[1].categoryId)
        XCTAssertNotNil(commands[2].sourceAccountId)
        XCTAssertNotNil(commands[2].destinationAccountId)
        XCTAssertNil(commands[2].accountId, "a payment names a source and a destination")
        XCTAssertEqual(commands[0].amount, "20.00")
        XCTAssertEqual(commands[0].timeZone, tzName)
        XCTAssertFalse(commands[0].expectedVersions.isEmpty, "the reviewed account version travels with the write")
    }

    func testATransferBetweenPlainAccountsStaysATransfer() async throws {
        let first = UUID(), second = UUID()
        var book = DeviceBook.empty()
        book = try book.addingAccount(BookAccountDraft(kind: .checking, currency: "DOP", nickname: "A", amountText: "100"), id: first, now: moment, zone: tzName)
        book = try book.addingAccount(BookAccountDraft(kind: .savings, currency: "DOP", nickname: "B", amountText: "0"), id: second, now: moment, zone: tzName)
        book = try book.recordingMovement(MovementDraft(kind: .transfer, accountID: first, counterpartID: second, amountText: "10",
                                                        occurredAt: moment.addingTimeInterval(60)), now: moment.addingTimeInterval(120), zone: tzName)
        let server = SampleGuestClaimServer()
        let (result, _) = await GuestClaimEngine(server: server).run(plan: GuestClaimPlan.make(book: book, existingNicknames: []), progress: GuestClaimProgress())
        XCTAssertEqual(result.movementsMoved, 1)
        XCTAssertEqual(result.movementsRefused, 0)
        let kinds = await server.commands.map(\.kind)
        XCTAssertEqual(kinds, [.transfer])
    }

    func testAPaymentIntoACardIsNotRefusedAsATransfer() async throws {
        let fixture = try Fixture()
        let server = SampleGuestClaimServer()
        let (result, _) = await GuestClaimEngine(server: server).run(plan: fixture.plan(), progress: GuestClaimProgress())
        XCTAssertEqual(result.movementsRefused, 0, "the server rejects a plain transfer into a card with 422; it goes as card_payment")
        XCTAssertEqual(result.movementsMoved, 3)
    }

    func testAnArchivedAccountIsArchivedAfterItIsCreated() async throws {
        let fixture = try Fixture()
        let server = SampleGuestClaimServer()
        _ = await GuestClaimEngine(server: server).run(plan: fixture.plan(), progress: GuestClaimProgress())
        let all = try await server.accounts()
        let wallet = try XCTUnwrap(all.first { $0.nickname == "Old wallet" })
        XCTAssertTrue(wallet.archived)
        XCTAssertEqual(all.filter(\.archived).count, 1)
    }

    func testRunningAgainWithItsProgressMovesNothingTwice() async throws {
        let fixture = try Fixture()
        let server = SampleGuestClaimServer()
        let engine = GuestClaimEngine(server: server)
        let (_, progress) = await engine.run(plan: fixture.plan(), progress: GuestClaimProgress())
        let (again, _) = await engine.run(plan: fixture.plan(), progress: progress)
        XCTAssertEqual(again.accountsMoved + again.movementsMoved, 0)
        let created = await server.createdAccounts
        let confirmed = await server.confirmedMovements
        XCTAssertEqual(created, 4)
        XCTAssertEqual(confirmed, 3)
    }

    func testALostProgressFileStillMovesNothingTwiceBecauseTheKeysAreStable() async throws {
        let fixture = try Fixture()
        let server = SampleGuestClaimServer()
        let engine = GuestClaimEngine(server: server)
        _ = await engine.run(plan: fixture.plan(), progress: GuestClaimProgress())
        let (again, _) = await engine.run(plan: fixture.plan(), progress: GuestClaimProgress())
        XCTAssertTrue(again.completed)
        let created = await server.createdAccounts
        let confirmed = await server.confirmedMovements
        let all = try await server.accounts()
        XCTAssertEqual(created, 4, "the server answered the repeated keys with the accounts it already made")
        XCTAssertEqual(confirmed, 3)
        XCTAssertEqual(all.count, 4)
    }

    func testAStoppedClaimKeepsWhatWasConfirmedAndContinuesOnRetry() async throws {
        let fixture = try Fixture()
        let server = SampleGuestClaimServer(script: .init(failCreateAfter: 2))
        let engine = GuestClaimEngine(server: server)
        let (first, progress) = await engine.run(plan: fixture.plan(), progress: GuestClaimProgress())
        XCTAssertEqual(first.stop, .unreachable)
        XCTAssertEqual(first.accountsMoved, 2)
        XCTAssertEqual(first.movementsMoved, 0, "no movement is sent while an account it needs is missing")
        let owner = await server.ownerID
        XCTAssertEqual(progress.owner(owner).accounts.count, 2)
        await server.setScript(.init())
        let (second, final) = await engine.run(plan: fixture.plan(), progress: progress)
        XCTAssertTrue(second.completed)
        XCTAssertEqual(second.accountsMoved, 2, "only the two still missing")
        XCTAssertEqual(second.movementsMoved, 3)
        XCTAssertEqual(final.owner(owner).accounts.count, 4)
        let created = await server.createdAccounts
        XCTAssertEqual(created, 4)
    }

    func testAMovementTheServerWillNotTakeStaysInTheBookAndTheRestContinue() async throws {
        let fixture = try Fixture()
        let server = SampleGuestClaimServer(script: .init(refuseNotes: ["Pay"]))
        let (result, progress) = await GuestClaimEngine(server: server).run(plan: fixture.plan(), progress: GuestClaimProgress())
        XCTAssertTrue(result.completed)
        XCTAssertEqual(result.movementsMoved, 2)
        XCTAssertEqual(result.movementsRefused, 1)
        let owner = await server.ownerID
        XCTAssertEqual(progress.owner(owner).refused.count, 1)
        let (again, _) = await GuestClaimEngine(server: server).run(plan: fixture.plan(), progress: progress)
        XCTAssertEqual(again.movementsRefused, 0, "a refused movement is not asked again on every run")
    }

    func testAnUnreachableMovementStopsTheClaimAndKeepsTheRest() async throws {
        let fixture = try Fixture()
        let server = SampleGuestClaimServer(script: .init(failConfirmAfter: 1))
        let (result, progress) = await GuestClaimEngine(server: server).run(plan: fixture.plan(), progress: GuestClaimProgress())
        XCTAssertEqual(result.stop, .unreachable)
        XCTAssertEqual(result.movementsMoved, 1)
        let owner = await server.ownerID
        XCTAssertEqual(progress.owner(owner).movements.count, 1)
    }

    func testNothingMovesWhenNobodyIsSignedIn() async throws {
        let fixture = try Fixture()
        let server = SampleGuestClaimServer(signedIn: false)
        let (result, progress) = await GuestClaimEngine(server: server).run(plan: fixture.plan(), progress: GuestClaimProgress())
        XCTAssertEqual(result.stop, .signedOut)
        XCTAssertEqual(progress, GuestClaimProgress())
        let created = await server.createdAccounts
        XCTAssertEqual(created, 0)
    }

    func testAnotherPersonOnTheSameIPhoneStartsFromNothing() async throws {
        let fixture = try Fixture()
        let first = SampleGuestClaimServer()
        let (_, progress) = await GuestClaimEngine(server: first).run(plan: fixture.plan(), progress: GuestClaimProgress())
        let second = SampleGuestClaimServer()
        let (result, both) = await GuestClaimEngine(server: second).run(plan: fixture.plan(), progress: progress)
        XCTAssertEqual(result.accountsMoved, 4)
        XCTAssertEqual(both.owners.count, 2)
    }

    func testKeysAreStableAndDistinctPerPersonKindAndItem() {
        let owner = UUID(), other = UUID(), item = UUID()
        let key = GuestClaimKeys.key(owner: owner, kind: "account", item: item)
        XCTAssertEqual(key, GuestClaimKeys.key(owner: owner, kind: "account", item: item))
        XCTAssertNotEqual(key, GuestClaimKeys.key(owner: other, kind: "account", item: item))
        XCTAssertNotEqual(key, GuestClaimKeys.key(owner: owner, kind: "movement", item: item))
        XCTAssertNotEqual(key, GuestClaimKeys.key(owner: owner, kind: "account", item: UUID()))
        XCTAssertEqual(key.uuidString[key.uuidString.index(key.uuidString.startIndex, offsetBy: 14)], "5", "a version 5 style id")
    }

    func testTheProgressFileSurvivesAReloadAndGoesWithTheBook() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("claim-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let file = GuestClaimProgressFile(directory: directory)
        XCTAssertEqual(file.load(), GuestClaimProgress())
        let owner = UUID(), guest = UUID(), server = UUID()
        let progress = GuestClaimProgress(owners: [owner: .init(accounts: [guest: server])])
        file.save(progress)
        XCTAssertEqual(file.load(), progress)
        try FileManager.default.removeItem(at: directory)
        file.save(progress)
        XCTAssertEqual(file.load(), GuestClaimProgress(), "a deleted book leaves no progress behind")
    }
}

private final class Saved: @unchecked Sendable {
    var progress = GuestClaimProgress()
}
