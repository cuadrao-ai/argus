import Foundation
import XCTest
@testable import ArgusSession
@testable import FinancialModels

@MainActor
final class FinancialModelTests: XCTestCase {
    func testHomeDoesNotTreatAnUnreadOrRetiredAccountListAsFirstUse() async throws {
        let fixture = try PresentationFixture()
        let identity = try await fixture.login()
        let accounts = AccountsModel(controller: fixture.client)
        accounts.bind(identity)
        XCTAssertFalse(accounts.hasLoaded)
        await accounts.load()
        XCTAssertTrue(accounts.hasLoaded)
        XCTAssertFalse(accounts.accounts.isEmpty)
        accounts.bind(nil)
        XCTAssertFalse(accounts.hasLoaded, "another session must not inherit a successful empty/read state")
        accounts.bind(identity)
        await fixture.server.readReply("/api/v1/financial-accounts", body: "{}", status: 503)
        await accounts.load()
        XCTAssertNotNil(accounts.errorKey)
        XCTAssertFalse(accounts.hasLoaded, "a failed initial read must show recovery, not the first-account invitation")
    }

    func testServerFailuresStayConnectionErrorsWhileValidationKeepsItsMessage() {
        for (mapper, validationKey) in [(FinancialEditor.message, "accounts.error.amount_invalid"), (FinancialActivityEditor.message, "loop.error.amount_invalid")] {
            XCTAssertEqual(mapper(SessionFailure.rejected(status: 503, code: "storage_unavailable")), "loop.error.connection")
            XCTAssertEqual(mapper(SessionFailure.rejected(status: 422, code: "amount_invalid")), validationKey)
        }
    }

    func testRedactedOriginalHasUnknownDisplayAndCannotOpenCorrectionOrReturn() async throws {
        let fixture = try PresentationFixture(); let identity = try await fixture.login()
        let accounts = AccountsModel(controller: fixture.client)
        let loop = FinancialLoopModel(controller: fixture.client, accounts: accounts, journal: fixture.journal)
        accounts.bind(identity); loop.bind(identity); await accounts.load()
        let account = try XCTUnwrap(accounts.accounts.first)
        let redacted = try MoneyActivityWireFixture.detail(source: UUID(), destination: account.id, redacted: true)
        XCTAssertEqual(AccountPresentation.amount(redacted.amount, locale: Locale(identifier: "es_419")), NSLocalizedString("accounts.unknown", comment: ""))
        loop.correct(redacted); XCTAssertNil(loop.activityEditor)
        loop.returnPayment(redacted); XCTAssertNil(loop.activityEditor)
        loop.record(account, correcting: redacted); XCTAssertNil(loop.activityEditor)
        let full = try MoneyActivityWireFixture.detail(source: account.id, destination: UUID(), redacted: false)
        loop.correct(full)
        let editor = try XCTUnwrap(loop.activityEditor)
        XCTAssertEqual(editor.amount, AccountPresentation.amount(MoneyActivityWireFixture.amount, locale: .current))
        XCTAssertEqual(editor.sourceAccountId, account.id)
    }
    func testCanCorrectMatchesTheCorrectionGate() async throws {
        let fixture = try PresentationFixture(); let identity = try await fixture.login()
        let accounts = AccountsModel(controller: fixture.client)
        let loop = FinancialLoopModel(controller: fixture.client, accounts: accounts, journal: fixture.journal)
        accounts.bind(identity); loop.bind(identity); await accounts.load()
        let account = try XCTUnwrap(accounts.accounts.first)
        let full = try MoneyActivityWireFixture.detail(source: account.id, destination: UUID(), redacted: false)
        let redacted = try MoneyActivityWireFixture.detail(source: account.id, destination: UUID(), redacted: true)
        let unknownAccount = try MoneyActivityWireFixture.detail(source: UUID(), destination: UUID(), redacted: false)
        XCTAssertTrue(loop.canCorrect(full))
        XCTAssertFalse(loop.canCorrect(redacted), "a redacted original cannot be corrected")
        XCTAssertFalse(loop.canCorrect(unknownAccount), "an account outside this list cannot host the correction")
        loop.correct(unknownAccount); XCTAssertNil(loop.activityEditor)
        loop.correct(full); XCTAssertNotNil(loop.activityEditor)
    }
    func testDetail401RetiresSessionAndClosesAccountIdentity() async throws {
        let fixture = try PresentationFixture()
        let identity = try await fixture.login()
        let accounts = AccountsModel(controller: fixture.client)
        let loop = FinancialLoopModel(controller: fixture.client, accounts: accounts, journal: fixture.journal)
        accounts.bind(identity); loop.bind(identity)
        var returnedToSignIn = false
        loop.sessionChanged = { snapshot in
            accounts.bind(snapshot)
            returnedToSignIn = snapshot.phase != .authenticated
        }
        let row = try JSONDecoder().decode(FinancialActivity.self, from: Data(PresentationServer.activityRow.utf8))
        await fixture.server.expireIdentity()
        do { _ = try await loop.detail(row); XCTFail("Expired detail must fail") }
        catch { XCTAssertTrue(returnedToSignIn) }
        XCTAssertNil(accounts.identity)
    }

    func testDefinitivePendingRejectionShowsRecoveryErrorOnAccounts() async throws {
        let fixture = try PresentationFixture()
        let identity = try await fixture.login()
        let account = try fixture.account()
        let accounts = AccountsModel(controller: fixture.client)
        let loop = FinancialLoopModel(controller: fixture.client, accounts: accounts, journal: fixture.journal)
        accounts.bind(identity); loop.bind(identity); accounts.select(account)
        loop.record(account)
        let editor = try XCTUnwrap(loop.activityEditor)
        await editor.load(); editor.amount = "20.00"
        await editor.review(locale: Locale(identifier: "en_US"))
        await fixture.server.failNextCommit(500)
        await editor.confirm()
        XCTAssertNotNil(loop.pendingConfirmation)
        await fixture.server.failNextCommit(409)
        await loop.retryPending()
        XCTAssertNil(loop.pendingConfirmation)
        XCTAssertNotNil(loop.recoveryErrorKey)
        XCTAssertNil(try fixture.journal.pending(for: identity))
    }

    func testCanonicalConfirmedWriteSurvivesRelaunchAndCannotReachAnotherOwner() async throws {
        let fixture = try PresentationFixture()
        let alice = try await fixture.login()
        let account = try fixture.account()
        let accounts = AccountsModel(controller: fixture.client)
        let loop = FinancialLoopModel(controller: fixture.client, accounts: accounts, journal: fixture.journal)
        accounts.bind(alice); loop.bind(alice); accounts.select(account)
        loop.record(account)
        let editor = try XCTUnwrap(loop.activityEditor)
        await editor.load()
        editor.amount = "20.00"
        await editor.review(locale: Locale(identifier: "en_US"))
        XCTAssertTrue(editor.canConfirm)
        await fixture.server.failNextCommit(500)
        await editor.confirm()
        XCTAssertEqual(editor.phase, .uncertain)
        XCTAssertNotNil(loop.pendingConfirmation)
        let firstCount = await fixture.server.canonicalCommits.count
        XCTAssertEqual(firstCount, 1)

        let reopened = try fixture.reopened()
        let restored = try await reopened.restore()
        let reopenedAccounts = AccountsModel(controller: reopened)
        let reopenedJournal = FinancialWriteJournal(storage: fixture.storage, prefix: fixture.configuration.storagePrefix)
        let reopenedLoop = FinancialLoopModel(controller: reopened, accounts: reopenedAccounts, journal: reopenedJournal)
        reopenedAccounts.bind(restored); reopenedLoop.bind(restored)
        XCTAssertNotNil(reopenedLoop.pendingConfirmation)
        let reopenCount = await fixture.server.canonicalCommits.count
        XCTAssertEqual(reopenCount, 1, "Opening the app must not submit a request")

        _ = try await reopened.signOut()
        let bob = try await reopened.login(email: "bob@example.test", password: "synthetic-password", captchaToken: "synthetic-captcha")
        reopenedAccounts.bind(bob); reopenedLoop.bind(bob)
        XCTAssertNil(reopenedLoop.pendingConfirmation)
        await reopenedLoop.retryPending()
        let bobCount = await fixture.server.canonicalCommits.count
        XCTAssertEqual(bobCount, 1)

        _ = try await reopened.signOut()
        let aliceAgain = try await reopened.login(email: "alice@example.test", password: "synthetic-password", captchaToken: "synthetic-captcha")
        reopenedAccounts.bind(aliceAgain); reopenedLoop.bind(aliceAgain)
        XCTAssertNotNil(reopenedLoop.pendingConfirmation)
        await reopenedLoop.retryPending()
        XCTAssertNil(reopenedLoop.pendingConfirmation)
        let commits = await fixture.server.canonicalCommits
        XCTAssertEqual(commits.count, 2)
        if commits.count == 2 {
            XCTAssertEqual(commits[0].httpBody, commits[1].httpBody)
            XCTAssertEqual(commits[0].value(forHTTPHeaderField: "Idempotency-Key"), commits[1].value(forHTTPHeaderField: "Idempotency-Key"))
        }
        XCTAssertEqual(reopenedAccounts.accounts.first { $0.id == account.id }?.balance.amount, "80.00")
        XCTAssertNil(reopenedAccounts.selected, "Recovering a write does not navigate the Accounts tab")
    }

    func testRenameSendsOnlyTheNicknameAgainstTheReadVersion() async throws {
        let fixture = try PresentationFixture()
        let identity = try await fixture.login()
        let model = AccountsModel(controller: fixture.client)
        model.bind(identity)
        await model.load()
        let account = try XCTUnwrap(model.accounts.first)
        model.rename(account)
        XCTAssertEqual(model.draft?.mode, .rename)
        model.draft?.nickname = "Everyday"
        await model.save()
        XCTAssertNil(model.errorKey)
        XCTAssertNil(model.draft, "An accepted rename closes the sheet")
        let patches = await fixture.server.archivePatches
        XCTAssertEqual(patches.count, 1)
        let payload = try XCTUnwrap(JSONSerialization.jsonObject(with: XCTUnwrap(patches.first?.httpBody)) as? [String: Any])
        XCTAssertEqual(Set(payload.keys), ["expected_version", "nickname"], "Rename never resends type, currency or ownership")
        XCTAssertEqual(payload["nickname"] as? String, "Everyday")
        XCTAssertEqual(payload["expected_version"] as? Int, account.version)
    }

    func testCanvasEntryCreatesOneRequestWithTheConnectedTypeAndPlainAmount() async throws {
        XCTAssertEqual(CanvasAccountKind.allCases.map { ConnectedAccountPresentation.type($0) },
                       ["cash", "checking", "savings", "investment", "credit_card", "other_debt", "property", "vehicle", "other_asset"])
        for kind in CanvasAccountKind.allCases {
            XCTAssertEqual(ConnectedAccountPresentation.artwork(ConnectedAccountPresentation.type(kind)), kind)
        }
        let cases: [(CanvasAccountEntry, type: String, amount: String?, share: Int)] = [
            (CanvasAccountEntry(kind: .property, name: "  Casa  ", amount: "8000000.5", currency: "USD", share: 50), "property", "8000000.5", 5000),
            (CanvasAccountEntry(kind: .checking, name: "Banco", amount: "-25.50", currency: "DOP", share: 50), "checking", "-25.50", 10000),
            (CanvasAccountEntry(kind: .card, name: "", amount: "", currency: "DOP"), "credit_card", nil, 10000),
        ]
        for (entry, type, amount, share) in cases {
            let fixture = try PresentationFixture()
            let identity = try await fixture.login()
            let model = AccountsModel(controller: fixture.client)
            model.bind(identity)
            let created = try fixture.account()
            var sent: [CreateFinancialAccountRequest] = []
            model.confirmCreate = { request in sent.append(request); return created }
            model.create()
            model.draft?.apply(entry)
            await model.save(locale: Locale(identifier: "en_US_POSIX"))
            XCTAssertNil(model.errorKey)
            XCTAssertEqual(sent.count, 1)
            XCTAssertEqual(sent.first?.type, type)
            XCTAssertEqual(sent.first?.nickname, entry.trimmedName)
            XCTAssertEqual(sent.first?.currency, entry.currency)
            XCTAssertEqual(sent.first?.amount, amount)
            XCTAssertEqual(sent.first?.ownershipShareBps, share, "Only assets carry a partial share")
            XCTAssertEqual(model.selected?.id, created.id, "A created account opens its detail")
        }
    }

    func testArchiveReloadAndRestorePreserveBalanceAndListPlacement() async throws {
        for unknown in [false, true] {
            let fixture = try PresentationFixture()
            await fixture.server.setUnknownBalance(unknown)
            let identity = try await fixture.login()
            let model = AccountsModel(controller: fixture.client)
            model.bind(identity)
            await model.load()
            let original = try XCTUnwrap(AccountPresentation.accounts(model.accounts, archived: false).first)
            XCTAssertTrue(AccountPresentation.accounts(model.accounts, archived: true).isEmpty)
            await model.archive(original)
            model.back()
            await model.load()
            XCTAssertTrue(AccountPresentation.accounts(model.accounts, archived: false).isEmpty)
            let archived = try XCTUnwrap(AccountPresentation.accounts(model.accounts, archived: true).first)
            XCTAssertEqual(archived.id, original.id)
            XCTAssertEqual(archived.balance, original.balance)
            XCTAssertEqual(model.accounts.count, 1, "Archiving must retain the canonical record")
            await model.open(archived)
            await model.archive(try XCTUnwrap(model.selected))
            model.back()
            await model.load()
            let restored = try XCTUnwrap(AccountPresentation.accounts(model.accounts, archived: false).first)
            XCTAssertEqual(restored.id, original.id)
            XCTAssertEqual(restored.balance, original.balance)
            XCTAssertTrue(AccountPresentation.accounts(model.accounts, archived: true).isEmpty)
            let patches = await fixture.server.archivePatches
            XCTAssertEqual(patches.count, 2)
            for request in patches {
                let payload = try XCTUnwrap(JSONSerialization.jsonObject(with: XCTUnwrap(request.httpBody)) as? [String: Any])
                XCTAssertEqual(Set(payload.keys), ["archived", "expected_version"])
            }
        }
    }

    func testArchiveRecoveryRefreshesOperationAccountAndPreservesOtherSelection() async throws {
        for status in [409, 503] {
            let fixture = try PresentationFixture()
            let identity = try await fixture.login()
            let model = AccountsModel(controller: fixture.client)
            model.bind(identity)
            let target = try fixture.account()
            let selected = try JSONDecoder().decode(FinancialAccount.self, from: Data(PresentationServer.account(updated: false)
                .replacingOccurrences(of: target.id.uuidString, with: UUID().uuidString).utf8))
            model.upsert(target); model.select(selected)
            for archived in [true, false] {
                await fixture.server.failArchiveResponse(status)
                await model.archive(try XCTUnwrap(model.accounts.first { $0.id == target.id }))
                let refreshed = try XCTUnwrap(model.accounts.first { $0.id == target.id })
                XCTAssertEqual(refreshed.archived, archived, "Recovery must read the write target for status \(status)")
                XCTAssertEqual(model.selected?.id, selected.id)
                XCTAssertEqual(model.selected?.version, selected.version)
                XCTAssertNotNil(model.errorKey)
                await model.refresh(target.id)
                XCTAssertNil(model.errorKey, "A successful detail retry clears the visible error")
                XCTAssertEqual(model.selected?.id, selected.id, "Retry must retain Accounts navigation")
            }
            let reads = await fixture.server.financialReads
            XCTAssertEqual(reads, Array(repeating: "/api/v1/financial-accounts/" + target.id.uuidString, count: 4))
        }
    }

    func testUncertainSaveFreezesDraftAndReplaysAcceptedOperation() async throws {
        for status in [500, 408] {
            let fixture = try PresentationFixture()
            let identity = try await fixture.login()
            var saved: FinancialAccount?
            let editor = FinancialEditor(account: try fixture.account(), kind: .expense(nil), controller: fixture.client, identity: identity) { saved = $0 }
            editor.amount = "20.00"
            await editor.review(locale: Locale(identifier: "en_US"))
            XCTAssertTrue(editor.canConfirm)
            await fixture.server.failNextCommit(status)
            await editor.confirm()
            XCTAssertEqual(editor.phase, .uncertain)
            XCTAssertFalse(editor.canEdit)
            editor.edit()
            XCTAssertEqual(editor.phase, .uncertain)
            await editor.confirm()
            XCTAssertEqual(editor.phase, .saved)
            XCTAssertEqual(saved?.balance.amount, "80.00")
            let commits = await fixture.server.commits
            XCTAssertEqual(commits.count, 2)
            XCTAssertEqual(commits[0].httpBody, commits[1].httpBody)
            XCTAssertEqual(commits[0].value(forHTTPHeaderField: "Idempotency-Key"), commits[1].value(forHTTPHeaderField: "Idempotency-Key"))
        }
    }

    func testDateChangeDropsObsoleteCoverageAndPriorAnswerCanBeCorrected() async throws {
        let fixture = try PresentationFixture()
        let identity = try await fixture.login()
        let observation = UUID()
        let raw = #"{"record_id":"\#(UUID())","revision":1,"kind":"expense","amount_minor":2000,"amount":"20.00","balance_movement_minor":-2000,"occurred_at":"2026-09-01T12:00:00Z","time_zone":"UTC","recorded_at":"2026-09-01T12:00:00Z","coverage":[{"observation_id":"\#(observation)","included":true}]}"#
        let activity = try JSONDecoder().decode(FinancialActivity.self, from: Data(raw.utf8))
        let editor = FinancialEditor(account: try fixture.account(), kind: .expense(activity), controller: fixture.client, identity: identity) { _ in }
        editor.reason = "Date correction"
        editor.date = try XCTUnwrap(ISO8601DateFormatter().date(from: "2026-09-02T12:00:00Z"))
        await editor.review(locale: Locale(identifier: "en_US"))
        var previews = await fixture.server.previews
        var payload = try JSONDecoder().decode(ExpenseRequest.self, from: XCTUnwrap(previews.last?.httpBody))
        XCTAssertTrue(payload.coverage.isEmpty)
        editor.answer(observation, included: false)
        await editor.review(locale: Locale(identifier: "en_US"))
        previews = await fixture.server.previews
        payload = try JSONDecoder().decode(ExpenseRequest.self, from: XCTUnwrap(previews.last?.httpBody))
        XCTAssertEqual(payload.coverage, [.init(observationId: observation, included: false)])
    }

    func testExpiredIdentityDuringConfirmReturnsToSignIn() async throws {
        let fixture = try PresentationFixture()
        let identity = try await fixture.login()
        let accounts = AccountsModel(controller: fixture.client)
        let loop = FinancialLoopModel(controller: fixture.client, accounts: accounts, journal: fixture.journal)
        accounts.bind(identity); loop.bind(identity)
        var returnedToSignIn = false
        loop.sessionChanged = { snapshot in
            accounts.bind(snapshot)
            returnedToSignIn = snapshot.phase != .authenticated
        }
        loop.expense(try fixture.account())
        let editor = try XCTUnwrap(loop.editor)
        editor.amount = "20.00"; await editor.review(locale: Locale(identifier: "en_US"))
        await fixture.server.expireIdentity()
        await editor.confirm()
        XCTAssertTrue(returnedToSignIn)
        XCTAssertEqual(editor.phase, .retired)
        XCTAssertNil(loop.editor)
        XCTAssertNil(accounts.identity)
        XCTAssertFalse(editor.canConfirm)
    }

    func testPostSaveHomeWinsOverEarlierRead() async throws {
        let fixture = try PresentationFixture()
        let identity = try await fixture.login()
        let accounts = AccountsModel(controller: fixture.client)
        let loop = FinancialLoopModel(controller: fixture.client, accounts: accounts, journal: fixture.journal)
        accounts.bind(identity); loop.bind(identity); accounts.select(try fixture.account())
        let gate = RequestGate()
        await fixture.server.holdNextHome(gate)
        let earlier = Task { await loop.refresh() }
        await gate.waitUntilStarted()
        loop.expense(try fixture.account())
        let editor = try XCTUnwrap(loop.editor)
        editor.amount = "20.00"
        await editor.review(locale: Locale(identifier: "en_US")); await editor.confirm()
        XCTAssertEqual(accounts.selected?.balance.amount, "80.00")
        XCTAssertEqual(loop.home?.currencies.first?.netWorthMinor, "8000")
        await gate.release(); await earlier.value
        XCTAssertEqual(loop.home?.currencies.first?.netWorthMinor, "8000")
    }

    func testOldEditorCannotInjectDataAfterOwnerSwitch() async throws {
        let fixture = try PresentationFixture()
        let identity = try await fixture.login()
        let accounts = AccountsModel(controller: fixture.client)
        let loop = FinancialLoopModel(controller: fixture.client, accounts: accounts, journal: fixture.journal)
        accounts.bind(identity); loop.bind(identity)
        loop.expense(try fixture.account())
        let editor = try XCTUnwrap(loop.editor)
        editor.amount = "20.00"; await editor.review(locale: Locale(identifier: "en_US"))
        let gate = RequestGate(); await fixture.server.holdCommit(gate)
        let saving = Task { await editor.confirm() }
        await gate.waitUntilStarted()
        _ = try await fixture.client.signOut()
        let second = try await fixture.login(email: "bob@example.test")
        accounts.bind(second); loop.bind(second)
        await gate.release(); await saving.value
        XCTAssertNil(accounts.selected)
        XCTAssertTrue(accounts.accounts.isEmpty)
        XCTAssertNil(loop.home)
        XCTAssertNil(loop.editor)
    }
}

private struct PresentationFixture {
    let server = PresentationServer()
    let client: SessionController
    let journal: FinancialWriteJournal
    let storage: MemoryStore
    let configuration: SessionConfiguration
    init() throws {
        let config = try SessionConfiguration(argusAPIURL: URL(string: "https://api.example.test")!, supabaseURL: URL(string: "https://auth.example.test")!, publicAnonKey: "sb_publishable_test", keychainService: UUID().uuidString)
        let server = self.server
        let storage = MemoryStore()
        self.configuration = config
        self.storage = storage
        client = try SessionController(configuration: config, storage: storage, fetch: { try await server.send($0) })
        journal = FinancialWriteJournal(storage: storage, prefix: config.storagePrefix)
    }
    func reopened() throws -> SessionController {
        let server = self.server
        return try SessionController(configuration: configuration, storage: storage, fetch: { try await server.send($0) })
    }
    func login(email: String = "alice@example.test") async throws -> SessionSnapshot {
        try await client.login(email: email, password: "synthetic-password", captchaToken: "synthetic-captcha")
    }
    func account() throws -> FinancialAccount { try JSONDecoder().decode(FinancialAccount.self, from: Data(PresentationServer.account(updated: false).utf8)) }
}

private actor PresentationServer {
    let auth = AuthServer()
    static let id = UUID()
    static let activityID = UUID()
    static let cashID = UUID()
    static var activityRow: String {
        #"{"record_id":"\#(activityID)","activity_id":"\#(activityID)","revision":1,"kind":"expense","amount_minor":2000,"amount":"20.00","balance_movement_minor":-2000,"occurred_at":"2026-09-01T12:00:00Z","time_zone":"UTC","recorded_at":"2026-09-01T12:00:00Z","coverage":[]}"#
    }
    private var updated = false
    private var archived = false
    private var unknownBalance = false
    private var accountVersion = 1
    private(set) var archivePatches: [URLRequest] = []
    private(set) var financialReads: [String] = []
    private var archiveResponseStatus: Int?
    func failArchiveResponse(_ status: Int) { archiveResponseStatus = status }
    func setUnknownBalance(_ value: Bool) { unknownBalance = value }
    private var nextStatus: Int?
    private var expired = false
    private var homeGate: RequestGate?
    private var commitGate: RequestGate?
    private(set) var commits: [URLRequest] = []
    private(set) var canonicalCommits: [URLRequest] = []
    private(set) var previews: [URLRequest] = []
    func expireIdentity() { expired = true }
    func failNextCommit(_ status: Int) { nextStatus = status }
    func holdNextHome(_ gate: RequestGate) { homeGate = gate }
    func holdCommit(_ gate: RequestGate) { commitGate = gate }
    private var readReplies: [String: (Int, String)] = [:]
    private var readGates: [String: RequestGate] = [:]
    func readReply(_ path: String, body: String, status: Int = 200, gate: RequestGate? = nil) {
        readReplies[path] = (status, body)
        readGates[path] = gate
    }
    private var searchReplies: [(Int, String)] = []
    private var searchGate: RequestGate?
    private(set) var searches: [URLRequest] = []
    func replies(_ values: [(Int, String)]) { searchReplies = values }
    func holdSearch(_ gate: RequestGate) { searchGate = gate }
    static func searchPage(_ ids: [UUID], cursor: String? = nil) -> String {
        let items = ids.map { id in
            "{\"kind\":\"account\",\"account\":" + account(updated: false).replacingOccurrences(of: Self.id.uuidString, with: id.uuidString) + "}"
        }.joined(separator: ",")
        return "{\"items\":[" + items + "],\"next_cursor\":" + (cursor.map { "\"" + $0 + "\"" } ?? "null") + "}"
    }
    private func search(_ request: URLRequest) async -> (Data, URLResponse) {
        searches.append(request)
        let reply = searchReplies.isEmpty ? (200, Self.searchPage([Self.id])) : searchReplies.removeFirst()
        if let gate = searchGate { searchGate = nil; await gate.enter() }
        return (Data(reply.1.utf8), HTTPURLResponse(url: request.url!, statusCode: reply.0, httpVersion: nil, headerFields: nil)!)
    }
    func send(_ request: URLRequest) async throws -> (Data, URLResponse) {
        let path = request.url!.path
        guard path.contains("/financial-") else { return try await auth.send(request) }
        let readKey = path + (request.url!.query.map { "?" + $0 } ?? "")
        if request.httpMethod == "GET" { financialReads.append(readKey) }
        if request.httpMethod == "GET", let reply = readReplies[readKey] {
            if let gate = readGates.removeValue(forKey: readKey) { await gate.enter() }
            return (Data(reply.1.utf8), HTTPURLResponse(url: request.url!, statusCode: reply.0, httpVersion: nil, headerFields: nil)!)
        }
        if path.contains("/financial-search") { return await search(request) }
        if path.contains("/financial-plan") { return try await plan(request) }
        if path.contains("/financial-activities") {
            return try canonical(request)
        }
        var status = 200
        let body: String
        if request.httpMethod == "PATCH", path.hasSuffix(Self.id.uuidString) {
            let payload = try JSONSerialization.jsonObject(with: request.httpBody!) as! [String: Any]
            if let value = payload["archived"] as? Bool { archived = value }
            accountVersion += 1
            archivePatches.append(request)
            // A concurrent matching write (409), or an accepted write with a lost response (503).
            status = archiveResponseStatus ?? 200; archiveResponseStatus = nil
            body = accountRecord()
        } else if path.hasSuffix("/financial-accounts") {
            body = "{\"accounts\":[" + accountRecord() + "]}"
        } else if path.hasSuffix(Self.id.uuidString), request.httpMethod == "GET" {
            body = accountRecord()
        } else if path.hasSuffix("/financial-home") {
            let amount = updated ? "8000" : "10000"
            body = #"{"currencies":[{"currency":"DOP","currency_fraction_digits":2,"assets_minor":"\#(amount)","cash_minor":"\#(amount)","other_assets_minor":"0","debts_minor":"0","net_worth_minor":"\#(amount)","recorded_spending_minor":"2000","known_accounts":1,"unknown_accounts":0,"as_of":null}],"recent_activity":[],"recorded_at":"2026-09-01T12:00:00Z"}"#
            if let gate = homeGate { homeGate = nil; await gate.enter() }
        } else if path.hasSuffix("/preview") {
            previews.append(request)
            body = #"{"account_version":1,"ready":true,"observations":[],"before":\#(Self.balance(false)),"after":\#(Self.balance(true)),"preview_token":"reviewed"}"#
        } else if request.httpMethod == "POST" {
            commits.append(request); updated = true
            if let gate = commitGate { commitGate = nil; await gate.enter() }
            status = expired ? 401 : nextStatus ?? 200; nextStatus = nil
            body = #"{"account":\#(Self.account(updated:true)),"activity":{"record_id":"\#(Self.activityID)","revision":1,"kind":"expense","amount_minor":2000,"amount":"20.00","balance_movement_minor":-2000,"occurred_at":"2026-09-01T12:00:00Z","time_zone":"UTC","recorded_at":"2026-09-01T12:00:00Z","coverage":[]},"replayed":true}"#
        } else { body = #"{"items":[],"next_cursor":null}"# }
        return (Data(body.utf8), HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: nil, headerFields: nil)!)
    }
    static let expectationId = UUID()
    private(set) var planCommits: [URLRequest] = []
    static var expectation: String {
        #"{"id":"\#(expectationId)","version":1,"kind":"bill","title":"Synthetic rent","currency":"DOP","currency_fraction_digits":2,"amount_minor":2000,"amount":"20.00","account_id":"\#(id)","schedule":{"cadence":"monthly","start_date":"2026-01-31","end_date":null,"month_days":[]},"archived":false,"earliest_effective_date":"2026-09-29"}"#
    }
    static func planProjection(updated: Bool) -> String {
        let amount = updated ? "8000" : "10000"
        let home = #"{"currencies":[{"currency":"DOP","currency_fraction_digits":2,"assets_minor":"\#(amount)","cash_minor":"\#(amount)","other_assets_minor":"0","debts_minor":"0","net_worth_minor":"\#(amount)","recorded_spending_minor":"2000","known_accounts":1,"unknown_accounts":0,"as_of":null}],"recent_activity":[],"recorded_at":"2026-09-01T12:00:00Z"}"#
        return #"{"home":\#(home),"selection":{"version":0,"account_ids":[],"time_zone":"America/Santo_Domingo"},"accounts":[\#(account(updated:false))],"expectations":[\#(expectation)],"occurrences":[],"currencies":[],"start_date":"2026-09-29","end_date":"2026-10-29","coverage":"recorded_and_expected","has_expectations":true}"#
    }
    private func plan(_ request: URLRequest) async throws -> (Data, URLResponse) {
        let body: String
        var status = 200
        if request.httpMethod == "GET" {
            body = Self.planProjection(updated: updated)
            if let gate = homeGate { homeGate = nil; await gate.enter() }
        }
        else {
            planCommits.append(request)
            status = nextStatus ?? 200; nextStatus = nil
            if request.url!.path.hasSuffix("/selection") {
                body = #"{"selection":{"version":1,"account_ids":[],"time_zone":"America/Santo_Domingo"},"replayed":true}"#
            } else { body = #"{"expectation":\#(Self.expectation),"replayed":true}"# }
        }
        return (Data(body.utf8), HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: nil, headerFields: nil)!)
    }

    private func canonical(_ request: URLRequest) throws -> (Data, URLResponse) {
        let path = request.url!.path
        let body: String
        var status = 200
        if expired, request.httpMethod == "GET" {
            status = 401
            body = #"{"code":"unauthorized"}"#
        } else if path.hasSuffix("/options") {
            let cash = Self.account(updated: false)
                .replacingOccurrences(of: Self.id.uuidString, with: Self.cashID.uuidString)
                .replacingOccurrences(of: "\"type\":\"checking\"", with: "\"type\":\"cash\"")
            body = #"{"accounts":[\#(accountRecord()),\#(cash)],"eligibility":{"expense":["cash","checking","savings","credit_card"],"income":["cash","checking","savings","investment"],"transfer":["cash","checking","savings","investment"],"card_payment":["cash","checking","savings","investment"],"refund":["cash","checking","savings","credit_card"]},"destination_eligibility":{"transfer":["cash","checking","savings","investment"],"card_payment":["credit_card"]},"categories":["groceries"],"sources":["salary"]}"#
        } else if path.hasSuffix("/purchases") {
            body = #"{"items":[]}"#
        } else if path.hasSuffix("/preview") {
            let payload = try JSONSerialization.jsonObject(with: request.httpBody!) as! [String: Any]
            let ids = [payload["account_id"], payload["source_account_id"], payload["destination_account_id"]]
                .compactMap { $0 as? String }
            let effects = ids.map { id in
                #"{"account_id":"\#(id)","currency":"DOP","currency_fraction_digits":2,"before":\#(Self.balance(false)),"after":\#(Self.balance(true)),"observations":[],"unexplained_before":{},"unexplained_after":{}}"#
            }.joined(separator: ",")
            let reviewed = String(data: try JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys]), encoding: .utf8)!
            body = #"{"ready":true,"expected_versions":{},"affected_accounts":[\#(effects)],"reviewed_request":\#(reviewed),"preview_token":"reviewed"}"#
        } else if request.httpMethod == "POST" || request.httpMethod == "PATCH" {
            canonicalCommits.append(request)
            status = nextStatus ?? 200; nextStatus = nil
            if status == 200 || status >= 500 { updated = true }
            let payload = try JSONSerialization.jsonObject(with: request.httpBody!) as! [String: Any]
            let kind = payload["kind"] as? String ?? "expense"
            let accountID = payload["account_id"] as? String ?? Self.id.uuidString
            let date = payload["occurred_at"] as? String ?? "2026-09-01T12:00:00Z"
            let zone = payload["time_zone"] as? String ?? "UTC"
            let activity = #"{"activity_id":"\#(Self.activityID)","revision":1,"kind":"\#(kind)","amount_minor":2000,"amount":"20.00","currency":"DOP","currency_fraction_digits":2,"occurred_at":"\#(date)","time_zone":"\#(zone)","note":null,"category_id":null,"source_id":null,"purchase_activity_id":null,"purchase_revision":null,"reason":null,"recorded_at":"2026-09-01T12:00:00Z","recorded_by":null,"legs":[{"record_id":"\#(Self.activityID)","record_revision":1,"account_id":"\#(accountID)","role":"single","balance_movement_minor":-2000,"coverage":[]}]}"#
            body = #"{"activity":\#(activity),"accounts":[\#(Self.account(updated: true))],"replayed":\#(canonicalCommits.count > 1)}"#
        } else {
            body = #"{"items":[],"next_cursor":null}"#
        }
        return (Data(body.utf8), HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: nil, headerFields: nil)!)
    }
    private func accountRecord() -> String {
        var record = Self.account(updated: updated)
            .replacingOccurrences(of: "\"archived\":false", with: "\"archived\":\(archived)")
            .replacingOccurrences(of: "\"version\":1", with: "\"version\":\(accountVersion)")
        if unknownBalance {
            record = record.replacingOccurrences(of: Self.balance(updated), with: #"{"state":"unknown","amount_minor":null,"amount":null,"as_of":null,"basis":null,"activity_since_tracking_minor":0}"#)
        }
        return record
    }
    static func balance(_ updated: Bool) -> String {
        #"{"state":"known","amount_minor":\#(updated ? 8000 : 10000),"amount":"\#(updated ? "80.00" : "100.00")","as_of":"2026-09-01T12:00:00Z","basis":"opening","activity_since_tracking_minor":\#(updated ? -2000 : 0)}"#
    }
    static func account(updated: Bool) -> String {
        #"{"id":"\#(id)","type":"checking","nature":"asset","currency":"DOP","currency_fraction_digits":2,"nickname":"Synthetic","archived":false,"ownership_share_bps":10000,"version":\#(updated ? 2 : 1),"created_at":"2026-09-01T12:00:00Z","updated_at":"2026-09-01T12:00:00Z","balance":\#(balance(updated)),"opening":null}"#
    }
}

@MainActor
extension FinancialModelTests {
    func testPlanTitleAndAmountEditDoesNotRewritePastSchedule() throws {
        let expectation = try JSONDecoder().decode(FinancialExpectation.self, from: Data(PresentationServer.expectation.utf8))
        let draft = FinancialExpectationDraft(expectation: expectation)
        draft.title = "Revised rent"; draft.amount = "25.50"
        XCTAssertFalse(draft.structuralChange)
        let command = try draft.command(locale: Locale(identifier: "en_US"))
        let payload = try XCTUnwrap(JSONSerialization.jsonObject(with: JSONEncoder().encode(command)) as? [String: Any])
        XCTAssertNil(payload["schedule"])
        XCTAssertNil(payload["effective_date"])
        XCTAssertNil(payload["kind"])
        XCTAssertNil(payload["account_id"], "Omitting an unchanged account preserves pending occurrence identity")
        XCTAssertEqual(payload["amount"] as? String, "25.50")
        XCTAssertEqual(payload["expected_version"] as? Int, expectation.version)
        draft.accountId = nil
        XCTAssertTrue(draft.structuralChange)
        let moved = try XCTUnwrap(JSONSerialization.jsonObject(with: JSONEncoder().encode(draft.command(locale: Locale(identifier: "en_US")))) as? [String: Any])
        XCTAssertNil(moved["schedule"], "An account-only edit must let the server choose the next safe scheduled date")
        XCTAssertTrue(moved["account_id"] is NSNull)
        XCTAssertEqual(moved["effective_date"] as? String, expectation.earliestEffectiveDate)
    }

    func testSeededMonthlyDraftKeepsTheMovementDayAnchorAfterClamping() throws {
        let checking = UUID()
        let legs: [[String: Any]] = [["record_id": UUID().uuidString, "record_revision": 1, "account_id": checking.uuidString,
                                      "role": "single", "balance_movement_minor": -35000, "coverage": []]]
        let raw: [String: Any] = ["activity_id": UUID().uuidString, "revision": 1, "kind": "expense", "amount_minor": 35000, "amount": "350.00",
            "currency": "DOP", "currency_fraction_digits": 2, "occurred_at": "2026-01-31T15:00:00Z", "time_zone": "UTC",
            "note": "Rent", "recorded_at": "2026-01-31T15:00:00Z", "legs": legs]
        let activity = try JSONDecoder().decode(FinancialActivityDetail.self, from: JSONSerialization.data(withJSONObject: raw))
        let account: [String: Any] = ["id": checking.uuidString, "type": "checking", "nature": "asset", "currency": "DOP", "currency_fraction_digits": 2,
            "archived": false, "ownership_share_bps": 10000, "version": 1, "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:00Z",
            "balance": ["state": "unknown", "activity_since_tracking_minor": 0]]
        let accounts = [try JSONDecoder().decode(FinancialAccount.self, from: JSONSerialization.data(withJSONObject: account))]
        let seed = try XCTUnwrap(FinancialExpectationSeed(activity: activity, accounts: accounts, today: "2026-02-15", fallbackTitle: "Housing"))
        let draft = FinancialExpectationDraft(seed: seed)
        XCTAssertTrue(draft.seededFromActivity)
        XCTAssertTrue(draft.ready)
        let payload = try XCTUnwrap(JSONSerialization.jsonObject(with: JSONEncoder().encode(draft.command(locale: Locale(identifier: "en_US")))) as? [String: Any])
        XCTAssertEqual(payload["kind"] as? String, "bill")
        XCTAssertEqual(payload["title"] as? String, "Rent")
        XCTAssertEqual(payload["currency"] as? String, "DOP")
        XCTAssertEqual(payload["amount"] as? String, "350.00")
        XCTAssertEqual(payload["account_id"] as? String, checking.uuidString)
        let schedule = try XCTUnwrap(payload["schedule"] as? [String: Any])
        XCTAssertEqual(schedule["cadence"] as? String, "monthly")
        XCTAssertEqual(schedule["start_date"] as? String, "2026-02-28", "first date clamps to February")
        XCTAssertEqual(schedule["month_days"] as? [Int], [31], "the anchor stays on the 31st so March is not stuck on the 28th")
        XCTAssertNil(schedule["end_date"], "no end date is prepared")
        XCTAssertNil(payload["expected_version"])
    }

    private static func planWindow(endDate: String, occurrences: [String]) -> String {
        let home = #"{"currencies":[{"currency":"DOP","currency_fraction_digits":2,"assets_minor":"10000","cash_minor":"10000","other_assets_minor":"0","debts_minor":"0","net_worth_minor":"10000","recorded_spending_minor":"0","known_accounts":1,"unknown_accounts":0,"as_of":null}],"recent_activity":[],"recorded_at":"2026-10-05T12:00:00Z"}"#
        return #"{"home":\#(home),"selection":{"version":0,"account_ids":["\#(PresentationServer.id)"],"time_zone":"America/Santo_Domingo"},"accounts":[\#(PresentationServer.account(updated:false))],"expectations":[\#(PresentationServer.expectation)],"occurrences":[\#(occurrences.joined(separator: ","))],"currencies":[],"budgets":[],"start_date":"2026-10-05","end_date":"\#(endDate)","coverage":"recorded_and_expected","has_expectations":true}"#
    }
    private static func occurrence(id: String, dueDate: String) -> String {
        #"{"id":"\#(id)","expectation_id":"\#(PresentationServer.expectationId)","expectation_version":1,"kind":"bill","title":"Synthetic rent","currency":"DOP","currency_fraction_digits":2,"amount_minor":2000,"amount":"20.00","account_id":"\#(PresentationServer.id)","due_date":"\#(dueDate)","projection_date":"\#(dueDate)","status":"planned","overdue":false}"#
    }

    func testOccurrenceOpenedFromHomeSurvivesARefreshOutsidePlansWindow() async throws {
        let fixture = try PresentationFixture()
        let identity = try await fixture.login()
        let accounts = AccountsModel(controller: fixture.client)
        let loop = FinancialLoopModel(controller: fixture.client, accounts: accounts, journal: fixture.journal)
        accounts.bind(identity); loop.bind(identity)
        let rent = Self.occurrence(id: "rent-2026-10-25", dueDate: "2026-10-25")
        await fixture.server.readReply("/api/v1/financial-plan", body: Self.planWindow(endDate: "2026-11-04", occurrences: [rent]))
        await fixture.server.readReply("/api/v1/financial-plan?end_date=2026-10-12", body: Self.planWindow(endDate: "2026-10-12", occurrences: []))
        await loop.plan.refresh()
        let opened = try XCTUnwrap(loop.plan.homeProjection?.occurrences.first)
        await loop.plan.open(opened)
        XCTAssertEqual(loop.plan.selectedOccurrence?.id, "rent-2026-10-25")
        await loop.plan.refresh(until: "2026-10-12")
        XCTAssertEqual(loop.plan.projection?.endDate, "2026-10-12")
        XCTAssertEqual(loop.plan.projection?.occurrences.count, 0)
        XCTAssertEqual(loop.plan.homeProjection?.endDate, "2026-11-04")
        XCTAssertEqual(loop.plan.selectedOccurrence?.id, "rent-2026-10-25", "the Home occurrence sheet stays open")
        await fixture.server.readReply("/api/v1/financial-plan", body: Self.planWindow(endDate: "2026-11-04", occurrences: []))
        await loop.plan.refresh(until: "2026-10-12")
        XCTAssertNil(loop.plan.selectedOccurrence, "gone from both windows closes the sheet")
    }

    func testPlanAndHomeReadsFailIndependently() async throws {
        let fixture = try PresentationFixture()
        let identity = try await fixture.login()
        let accounts = AccountsModel(controller: fixture.client)
        let loop = FinancialLoopModel(controller: fixture.client, accounts: accounts, journal: fixture.journal)
        accounts.bind(identity); loop.bind(identity)
        await fixture.server.readReply("/api/v1/financial-plan", body: Self.planWindow(endDate: "2026-11-04", occurrences: []))
        await fixture.server.readReply("/api/v1/financial-plan?end_date=2026-10-12", body: Self.planWindow(endDate: "2026-10-12", occurrences: []))
        await loop.plan.refresh()
        XCTAssertEqual(loop.plan.homeProjection?.endDate, "2026-11-04")
        await fixture.server.readReply("/api/v1/financial-plan", body: #"{"code":"unavailable"}"#, status: 503)
        await loop.plan.refresh(until: "2026-10-12")
        XCTAssertEqual(loop.plan.projection?.endDate, "2026-10-12", "Plan keeps its own successful read")
        XCTAssertNil(loop.plan.errorKey)
        XCTAssertEqual(loop.plan.homeProjection?.endDate, "2026-11-04", "Home keeps its last good window")
        XCTAssertEqual(loop.plan.homeErrorKey, "loop.error.connection")
        await fixture.server.readReply("/api/v1/financial-plan", body: Self.planWindow(endDate: "2026-11-05", occurrences: []))
        await fixture.server.readReply("/api/v1/financial-plan?end_date=2026-10-12", body: #"{"code":"unavailable"}"#, status: 503)
        await loop.plan.refresh(until: "2026-10-12")
        XCTAssertEqual(loop.plan.projection?.endDate, "2026-10-12", "Plan keeps its last good projection")
        XCTAssertEqual(loop.plan.errorKey, "loop.error.connection")
        XCTAssertEqual(loop.plan.homeProjection?.endDate, "2026-11-05", "Home reads on even when Plan's read fails")
        XCTAssertNil(loop.plan.homeErrorKey)
    }

    func testSharedDefaultWindowFailureShowsOnHomeAndPlan() async throws {
        let fixture = try PresentationFixture()
        let identity = try await fixture.login()
        let accounts = AccountsModel(controller: fixture.client)
        let loop = FinancialLoopModel(controller: fixture.client, accounts: accounts, journal: fixture.journal)
        accounts.bind(identity); loop.bind(identity)
        await fixture.server.readReply("/api/v1/financial-plan", body: #"{"code":"unavailable"}"#, status: 503)
        await loop.plan.refresh()
        XCTAssertNil(loop.plan.homeProjection)
        XCTAssertEqual(loop.plan.homeErrorKey, "loop.error.connection", "Home offers its own retry when the shared read fails")
        XCTAssertEqual(loop.plan.errorKey, "loop.error.connection")
        await fixture.server.readReply("/api/v1/financial-plan", body: Self.planWindow(endDate: "2026-11-04", occurrences: []))
        await loop.plan.refresh()
        XCTAssertEqual(loop.plan.homeProjection?.endDate, "2026-11-04")
        XCTAssertNil(loop.plan.homeErrorKey)
        XCTAssertNil(loop.plan.errorKey)
    }

    func testPlanConfirmationSurvivesRelaunchAndDifferentOwnerCannotReplay() async throws {
        let fixture = try PresentationFixture()
        let alice = try await fixture.login()
        let accounts = AccountsModel(controller: fixture.client)
        let loop = FinancialLoopModel(controller: fixture.client, accounts: accounts, journal: fixture.journal)
        accounts.bind(alice); loop.bind(alice)
        await loop.plan.refresh()
        XCTAssertNotNil(loop.plan.projection)
        loop.plan.create()
        let draft = try XCTUnwrap(loop.plan.draft)
        draft.title = "Test bill"; draft.amount = "12.34"
        await fixture.server.failNextCommit(500)
        await loop.plan.save(locale: Locale(identifier: "en_US"))
        let pending = try XCTUnwrap(loop.pendingConfirmation)
        XCTAssertEqual(pending.planOperation, .createExpectation)
        XCTAssertNotNil(try fixture.journal.pending(for: alice))
        let reopened = try fixture.reopened()
        let restored = try await reopened.restore()
        let reopenedAccounts = AccountsModel(controller: reopened)
        let reopenedLoop = FinancialLoopModel(controller: reopened, accounts: reopenedAccounts, journal: fixture.journal)
        reopenedAccounts.bind(restored); reopenedLoop.bind(restored)
        XCTAssertEqual(reopenedLoop.pendingConfirmation, pending)
        let beforeRetry = await fixture.server.planCommits.count
        XCTAssertEqual(beforeRetry, 1)
        _ = try await reopened.signOut()
        let bob = try await reopened.login(email: "bob@example.test", password: "synthetic", captchaToken: "synthetic")
        reopenedAccounts.bind(bob); reopenedLoop.bind(bob)
        XCTAssertNil(reopenedLoop.plan.projection)
        XCTAssertNil(reopenedLoop.plan.draft)
        XCTAssertNil(reopenedLoop.pendingConfirmation)
        await reopenedLoop.retryPending()
        let bobCount = await fixture.server.planCommits.count
        XCTAssertEqual(bobCount, 1)
        _ = try await reopened.signOut()
        let aliceAgain = try await reopened.login(email: "alice@example.test", password: "synthetic", captchaToken: "synthetic")
        reopenedAccounts.bind(aliceAgain); reopenedLoop.bind(aliceAgain)
        await reopenedLoop.retryPending()
        XCTAssertNil(reopenedLoop.pendingConfirmation)
        XCTAssertNotNil(reopenedLoop.home)
        XCTAssertNotNil(reopenedLoop.plan.projection)
        XCTAssertEqual(reopenedLoop.home?.currencies.first?.netWorthMinor,
                       reopenedLoop.plan.projection?.home.currencies.first?.netWorthMinor)
        let commits = await fixture.server.planCommits
        XCTAssertEqual(commits.count, 2)
        XCTAssertEqual(commits.first?.httpBody, commits.last?.httpBody)
        XCTAssertEqual(commits.first?.value(forHTTPHeaderField: "Idempotency-Key"), commits.last?.value(forHTTPHeaderField: "Idempotency-Key"))
    }

    func testEmptyPlanSelectionIsAnExplicitJournaledPut() async throws {
        let fixture = try PresentationFixture()
        let identity = try await fixture.login()
        let accounts = AccountsModel(controller: fixture.client)
        let loop = FinancialLoopModel(controller: fixture.client, accounts: accounts, journal: fixture.journal)
        accounts.bind(identity); loop.bind(identity)
        await loop.plan.refresh()
        await fixture.server.failNextCommit(500)
        let saved = await loop.plan.selectAccounts([], timeZone: "America/Santo_Domingo")
        XCTAssertFalse(saved)
        let pending = try XCTUnwrap(loop.pendingConfirmation)
        XCTAssertEqual(pending.method, "PUT")
        XCTAssertEqual(pending.planOperation, .selection(version: 0))
        let payload = try XCTUnwrap(JSONSerialization.jsonObject(with: pending.body) as? [String: Any])
        XCTAssertEqual(payload["account_ids"] as? [String], [])
        await loop.retryPending()
        XCTAssertNil(loop.pendingConfirmation)
        let commits = await fixture.server.planCommits
        XCTAssertEqual(commits.first?.httpBody, commits.last?.httpBody)
    }
}

@MainActor
extension FinancialModelTests {
    func testSearchRelaunchRefetchesLoadedPagesAndOnlyPersistsOrigin() async throws {
        let fixture = try PresentationFixture()
        let identity = try await fixture.login()
        let name = UUID().uuidString
        let defaults = try XCTUnwrap(UserDefaults(suiteName: name))
        defer { defaults.removePersistentDomain(forName: name) }
        let model = FinancialSearchModel(controller: fixture.client, defaults: defaults)
        model.bind(identity); model.update(query: "Café %_\\", scope: .accounts, currency: .some("DOP"))
        let second = UUID()
        let pages = [(200, PresentationServer.searchPage([PresentationServer.id], cursor: "next")), (200, PresentationServer.searchPage([second]))]
        await fixture.server.replies(pages)
        await model.refresh(); await model.more()
        XCTAssertEqual(model.items.count, 2)
        model.remember(anchor: model.items[1].id, offset: -19)
        let reopened = FinancialSearchModel(controller: fixture.client, defaults: defaults)
        reopened.bind(identity)
        XCTAssertTrue(reopened.items.isEmpty)
        XCTAssertEqual(reopened.origin, model.origin)
        await fixture.server.replies(pages)
        await reopened.activate()
        XCTAssertEqual(reopened.items.map(\.recordID), [PresentationServer.id, second])
        XCTAssertEqual(reopened.origin.anchorOffset, -19)
        let restoration = try XCTUnwrap(reopened.restoration)
        reopened.remember(anchor: reopened.items[0].id, offset: 54)
        XCTAssertEqual(reopened.origin.anchor, model.origin.anchor, "Initial layout cannot replace the saved deep-scroll anchor")
        XCTAssertEqual(reopened.origin.anchorOffset, -19)
        reopened.restored(UUID())
        XCTAssertNotNil(reopened.restoration)
        reopened.restored(restoration.id)
        reopened.remember(anchor: reopened.items[1].id, offset: -20)
        XCTAssertEqual(reopened.origin.anchorOffset, -20)
        let key = "financial.search.origin." + identity.profile!.id
        let saved = String(data: try XCTUnwrap(defaults.data(forKey: key)), encoding: .utf8)!
        XCTAssertFalse(saved.contains("Synthetic")); XCTAssertFalse(saved.contains("amount"))
        let requests = await fixture.server.searches
        let values = URLComponents(url: requests[0].url!, resolvingAgainstBaseURL: false)!.queryItems!
        XCTAssertEqual(values.first { $0.name == "q" }?.value, "Café %_\\")
        XCTAssertEqual(values.first { $0.name == "kind" }?.value, "account")
        model.bind(nil)
        XCTAssertNil(defaults.data(forKey: key))
        XCTAssertTrue(model.items.isEmpty)
    }

    func testSearchPlansScopeReadsEveryPlanKindAndRelaunchReplaysIt() async throws {
        let fixture = try PresentationFixture()
        let identity = try await fixture.login()
        let name = UUID().uuidString
        let defaults = try XCTUnwrap(UserDefaults(suiteName: name))
        defer { defaults.removePersistentDomain(forName: name) }
        let model = FinancialSearchModel(controller: fixture.client, defaults: defaults)
        model.bind(identity); model.update(scope: .plans)
        let bill = UUID(), laterBill = UUID(), goal = UUID()
        let pages = [(200, PresentationServer.searchPage([bill], cursor: "bills-2")), (200, PresentationServer.searchPage([laterBill])),
            (200, PresentationServer.searchPage([])), (200, PresentationServer.searchPage([goal])), (200, PresentationServer.searchPage([]))]
        await fixture.server.replies(pages)
        await model.activate()
        XCTAssertEqual(model.items.map(\.recordID), [bill])
        XCTAssertEqual(model.cursor, "bills-2")
        await model.more()
        XCTAssertEqual(model.items.map(\.recordID), [bill, laterBill, goal])
        XCTAssertNil(model.cursor)
        func sent(_ requests: [URLRequest]) -> [String] {
            requests.map { request in
                let values = URLComponents(url: request.url!, resolvingAgainstBaseURL: false)!.queryItems ?? []
                return [values.first { $0.name == "kind" }?.value, values.first { $0.name == "cursor" }?.value]
                    .compactMap { $0 }.joined(separator: "@")
            }
        }
        let expected = ["expectation", "expectation@bills-2", "budget", "goal", "debt"]
        let first = await fixture.server.searches
        XCTAssertEqual(sent(first), expected)
        let reopened = FinancialSearchModel(controller: fixture.client, defaults: defaults)
        reopened.bind(identity)
        XCTAssertEqual(reopened.origin.scope, .plans)
        await fixture.server.replies(pages)
        await reopened.activate()
        XCTAssertEqual(reopened.items.map(\.recordID), [bill, laterBill, goal])
        let all = await fixture.server.searches
        XCTAssertEqual(sent(Array(all.dropFirst(first.count))), expected)
    }

    func testUnchangedSearchControlsRetainLoadedPagesAndScrollOrigin() async throws {
        let fixture = try PresentationFixture()
        let identity = try await fixture.login()
        let name = UUID().uuidString
        let defaults = try XCTUnwrap(UserDefaults(suiteName: name))
        defer { defaults.removePersistentDomain(forName: name) }
        let model = FinancialSearchModel(controller: fixture.client, defaults: defaults)
        model.bind(identity)
        model.update(query: "Synthetic", scope: .accounts, currency: .some("DOP"))
        await fixture.server.replies([(200, PresentationServer.searchPage([PresentationServer.id], cursor: "next")),
            (200, PresentationServer.searchPage([UUID()], cursor: "third"))])
        await model.activate(); await model.more()
        let ids = model.items.map(\.id)
        model.remember(anchor: ids[1], offset: -19)
        let origin = model.origin
        model.update(query: origin.query)
        model.update(scope: origin.scope)
        model.update(currency: .some(origin.currency))
        model.update()
        XCTAssertEqual(model.items.map(\.id), ids)
        XCTAssertEqual(model.origin, origin)
        XCTAssertEqual(model.cursor, "third")
        await model.activate()
        let searches = await fixture.server.searches
        XCTAssertEqual(searches.count, 2, "Repeated control values must not invalidate a loaded search")
        model.update(currency: .some(nil))
        XCTAssertEqual(model.items.map(\.id), ids)
        XCTAssertNil(model.cursor)
        XCTAssertEqual(model.origin.pages, 1)
        XCTAssertNil(model.origin.currency)
    }

    func testSearchFilterChangeKeepsRowsUntilTheReplacementLands() async throws {
        let fixture = try PresentationFixture()
        let identity = try await fixture.login()
        let model = FinancialSearchModel(controller: fixture.client, defaults: UserDefaults(suiteName: UUID().uuidString)!)
        model.bind(identity)
        let shown = UUID(), replacement = UUID()
        await fixture.server.replies([(200, PresentationServer.searchPage([shown], cursor: "next"))])
        await model.activate()
        model.remember(anchor: model.items[0].id, offset: -12)
        model.update(scope: .accounts)
        XCTAssertEqual(model.items.map(\.recordID), [shown], "A filter change cannot blank the rows it is replacing")
        XCTAssertNil(model.cursor)
        XCTAssertFalse(model.loading)
        XCTAssertNil(model.origin.anchor)
        XCTAssertEqual(model.origin.pages, 1)
        model.remember(anchor: model.items[0].id, offset: -30)
        XCTAssertNil(model.origin.anchor, "A row from the previous filter cannot become the new scroll origin")
        let gate = RequestGate(); await fixture.server.holdSearch(gate)
        await fixture.server.replies([(200, PresentationServer.searchPage([replacement]))])
        let pending = Task { await model.activate() }
        await gate.waitUntilStarted()
        XCTAssertTrue(model.loading)
        XCTAssertEqual(model.items.map(\.recordID), [shown])
        await gate.release(); await pending.value
        XCTAssertEqual(model.items.map(\.recordID), [replacement])
        XCTAssertNil(model.restoration)
        model.update(query: "unreachable")
        await fixture.server.replies([(503, #"{"code":"unavailable"}"#)])
        await model.activate()
        XCTAssertTrue(model.items.isEmpty, "A failed filter change cannot leave the previous filter's rows on screen")
        XCTAssertEqual(model.errorKey, "search.error")
    }

    func testSearchRestorationWaitsForLayoutAndAllowsRemovedRowBoundary() {
        let saved = FinancialScrollRestoration(anchor: "account.saved", offset: -51)
        XCTAssertEqual(saved.adjustment(rowOffset: 0, contentOffset: 1000, minimum: 0, maximum: 1000), .waitForLayout)
        XCTAssertEqual(saved.adjustment(rowOffset: 0, contentOffset: 1000, minimum: 0, maximum: 1100), .move(1051))
        XCTAssertEqual(saved.adjustment(rowOffset: -51, contentOffset: 1051, minimum: 0, maximum: 1100), .complete)
        let fallback = FinancialScrollRestoration(anchor: "account.survivor", offset: -51, permitsBoundaryFallback: true)
        XCTAssertEqual(fallback.adjustment(rowOffset: 0, contentOffset: 800, minimum: 0, maximum: 800), .complete)
    }

    func testSearchRemovedAnchorAndExplicitScrollReleaseRestoration() async throws {
        let fixture = try PresentationFixture()
        let identity = try await fixture.login()
        let name = UUID().uuidString
        let defaults = try XCTUnwrap(UserDefaults(suiteName: name))
        defer { defaults.removePersistentDomain(forName: name) }
        let model = FinancialSearchModel(controller: fixture.client, defaults: defaults)
        model.bind(identity)
        let first = UUID(), last = UUID()
        await fixture.server.replies([(200, PresentationServer.searchPage([first, last]))])
        await model.activate()
        model.remember(anchor: model.items[1].id, offset: -51)
        await fixture.server.replies([(200, PresentationServer.searchPage([first]))])
        await model.refresh()
        let replacement = try XCTUnwrap(model.restoration)
        XCTAssertEqual(replacement.anchor, model.items[0].id)
        XCTAssertTrue(replacement.permitsBoundaryFallback)
        model.restored(replacement.id)
        model.remember(anchor: model.items[0].id, offset: -10)
        await fixture.server.replies([(200, PresentationServer.searchPage([first]))])
        await model.refresh()
        XCTAssertEqual(model.restoration?.permitsBoundaryFallback, false)
        model.userScrolled()
        model.remember(anchor: model.items[0].id, offset: -25)
        XCTAssertNil(model.restoration)
        XCTAssertEqual(model.origin.anchorOffset, -25)
        let reopened = FinancialSearchModel(controller: fixture.client, defaults: defaults)
        reopened.bind(identity)
        XCTAssertEqual(reopened.origin.anchorOffset, -25, "User scrolling must persist after an interrupted restoration")
        await fixture.server.replies([(200, PresentationServer.searchPage([first]))])
        await model.refresh()
        XCTAssertNotNil(model.restoration)
        await fixture.server.replies([(200, PresentationServer.searchPage([]))])
        await model.refresh()
        XCTAssertNil(model.restoration, "An empty result must retire an obsolete scroll target")
        XCTAssertNil(model.origin.anchor)
    }

    func testSearchNewQueryAndOwnerRejectDelayedOldResults() async throws {
        let fixture = try PresentationFixture()
        let identity = try await fixture.login()
        let defaults = try XCTUnwrap(UserDefaults(suiteName: UUID().uuidString))
        let model = FinancialSearchModel(controller: fixture.client, defaults: defaults)
        model.bind(identity)
        let gate = RequestGate(); await fixture.server.holdSearch(gate)
        let stale = Task { await model.refresh() }
        await gate.waitUntilStarted()
        model.update(query: "unmatched")
        await fixture.server.replies([(200, PresentationServer.searchPage([]))])
        await model.refresh()
        await gate.release(); await stale.value
        XCTAssertTrue(model.items.isEmpty)
        XCTAssertEqual(model.origin.query, "unmatched")
        let ownerGate = RequestGate(); await fixture.server.holdSearch(ownerGate)
        let oldOwner = Task { await model.refresh() }
        await ownerGate.waitUntilStarted()
        _ = try await fixture.client.signOut()
        let bob = try await fixture.login(email: "bob@example.test")
        model.bind(bob)
        await ownerGate.release(); await oldOwner.value
        XCTAssertTrue(model.items.isEmpty)
        XCTAssertEqual(model.ownerID, bob.profile?.id)
        XCTAssertEqual(model.origin.query, "")
        XCTAssertFalse(model.loading)
    }

    func testSearchStaleCursorRestartsOnceAndRetainsContextOnFailure() async throws {
        let fixture = try PresentationFixture()
        let identity = try await fixture.login()
        let model = FinancialSearchModel(controller: fixture.client, defaults: UserDefaults(suiteName: UUID().uuidString)!)
        model.bind(identity)
        let first = PresentationServer.id, second = UUID()
        await fixture.server.replies([(200, PresentationServer.searchPage([first], cursor: "old"))])
        await model.refresh()
        model.remember(anchor: model.items[0].id, offset: -9)
        await fixture.server.replies([(409, #"{"code":"financial_search_stale_cursor"}"#),
            (200, PresentationServer.searchPage([second], cursor: "fresh")),
            (200, PresentationServer.searchPage([UUID()]))])
        await model.more()
        XCTAssertEqual(model.items.count, 2)
        XCTAssertFalse(model.items.contains { $0.recordID == first })
        XCTAssertEqual(model.origin.anchor, model.items[0].id)
        XCTAssertEqual(model.origin.anchorOffset, -9)
        let retained = model.items.map(\.id)
        await fixture.server.replies([(503, #"{"code":"unavailable"}"#)])
        await model.refresh()
        XCTAssertEqual(model.items.map(\.id), retained)
        XCTAssertEqual(model.errorKey, "search.error")
        model.update(query: "different")
        XCTAssertEqual(model.items.map(\.id), retained)
        XCTAssertNil(model.cursor)
        XCTAssertNil(model.errorKey)
        await fixture.server.replies([(200, PresentationServer.searchPage([first], cursor: "stale")),
            (409, #"{"code":"financial_search_stale_cursor"}"#),
            (200, PresentationServer.searchPage([first], cursor: "stale-again")),
            (409, #"{"code":"financial_search_stale_cursor"}"#)])
        await model.refresh(); await model.more()
        XCTAssertEqual(model.errorKey, "search.error")
        XCTAssertFalse(model.loading)
    }
}

@MainActor
extension FinancialModelTests {
    func testSearchOriginChangesRetireDelayedAccountAndExpectationOpens() async throws {
        for field in ["query", "kind", "currency"] {
            for expectation in [false, true] {
                let fixture = try PresentationFixture()
                let identity = try await fixture.login()
                let accounts = AccountsModel(controller: fixture.client)
                let loop = FinancialLoopModel(controller: fixture.client, accounts: accounts, journal: fixture.journal)
                let search = FinancialSearchModel(controller: fixture.client, defaults: UserDefaults(suiteName: UUID().uuidString)!)
                accounts.bind(identity); loop.bind(identity); search.bind(identity)
                let hit: FinancialSearchHit
                let path: String
                let body: String
                if expectation {
                    let item = try JSONDecoder().decode(FinancialExpectation.self, from: Data(PresentationServer.expectation.utf8))
                    hit = .expectation(item); path = "/api/v1/financial-plan/expectations/" + item.id.uuidString
                    body = PresentationServer.expectation
                } else {
                    let item = try fixture.account()
                    hit = .account(item); path = "/api/v1/financial-accounts/" + item.id.uuidString
                    body = PresentationServer.account(updated: false)
                }
                let gate = RequestGate()
                await fixture.server.readReply(path, body: body, gate: gate)
                let pending = Task { await search.open(hit, accounts: accounts, loop: loop) }
                await gate.waitUntilStarted()
                XCTAssertTrue(search.opening)
                switch field {
                case "query": search.update(query: "A newer search")
                case "kind": search.update(scope: .activity)
                default: search.update(currency: .some("USD"))
                }
                XCTAssertFalse(search.opening)
                await gate.release(); await pending.value
                XCTAssertNil(search.destination)
                XCTAssertNil(loop.plan.draft)
                XCTAssertNil(accounts.selected)
                XCTAssertNil(search.destinationError)
            }
        }
    }

    func testSearchAccountNavigationAndAcceptedEditsPreserveAccountsSelection() async throws {
        let fixture = try PresentationFixture()
        let identity = try await fixture.login()
        let accounts = AccountsModel(controller: fixture.client)
        let loop = FinancialLoopModel(controller: fixture.client, accounts: accounts, journal: fixture.journal)
        let search = FinancialSearchModel(controller: fixture.client, defaults: UserDefaults(suiteName: UUID().uuidString)!)
        accounts.bind(identity); loop.bind(identity); search.bind(identity)
        let first = try fixture.account()
        let second = try JSONDecoder().decode(FinancialAccount.self, from: Data(PresentationServer.account(updated: false)
            .replacingOccurrences(of: first.id.uuidString, with: UUID().uuidString).utf8))
        accounts.select(second)
        await search.open(.account(first), accounts: accounts, loop: loop)
        XCTAssertEqual(accounts.selected?.id, second.id)
        guard case .account(let opened) = search.destination else { return XCTFail("Search must retain its own account destination") }
        XCTAssertEqual(opened, first.id)
        accounts.back()
        XCTAssertNil(accounts.selected)
        XCTAssertNotNil(accounts.accounts.first { $0.id == first.id })
        accounts.select(second)
        let updated = try JSONDecoder().decode(FinancialAccount.self, from: Data(PresentationServer.account(updated: true).utf8))
        accounts.accept(updated)
        XCTAssertEqual(accounts.selected?.id, second.id)
        XCTAssertEqual(accounts.accounts.first { $0.id == first.id }?.balance.amount, "80.00")
        accounts.back(); accounts.accept(updated)
        XCTAssertNil(accounts.selected, "A Search edit cannot navigate Accounts from its list")
    }
}

@MainActor
extension FinancialModelTests {
    func testConcurrentAccountDetailsKeepActivityChecksAndPaginationIsolated() async throws {
        let fixture = try PresentationFixture()
        let identity = try await fixture.login()
        let accounts = AccountsModel(controller: fixture.client)
        let loop = FinancialLoopModel(controller: fixture.client, accounts: accounts, journal: fixture.journal)
        accounts.bind(identity); loop.bind(identity)
        let first = try fixture.account()
        let second = try JSONDecoder().decode(FinancialAccount.self, from: Data(PresentationServer.account(updated: false)
            .replacingOccurrences(of: first.id.uuidString, with: UUID().uuidString).utf8))
        let firstRow = UUID(), secondRow = UUID(), firstCheck = UUID(), secondCheck = UUID()
        func activities(_ id: UUID, cursor: String? = nil) -> String {
            let row = PresentationServer.activityRow.replacingOccurrences(of: PresentationServer.activityID.uuidString, with: id.uuidString)
            return "{\"items\":[" + row + "],\"next_cursor\":" + (cursor.map { "\"" + $0 + "\"" } ?? "null") + "}"
        }
        func checks(_ id: UUID) -> String {
            #"{"items":[{"record_id":"\#(id)","revision":1,"kind":"balance_check","as_of":"2026-09-01T12:00:00Z","time_zone":"UTC","source":"manual","observed_amount_minor":10000,"recorded_at":"2026-09-01T12:00:00Z"}],"next_cursor":null}"#
        }
        let a = "/api/v1/financial-accounts/" + first.id.uuidString
        let b = "/api/v1/financial-accounts/" + second.id.uuidString
        let held = RequestGate()
        await fixture.server.readReply(a + "/activity", body: activities(firstRow, cursor: "a-next"), gate: held)
        await fixture.server.readReply(a + "/balance-checks", body: checks(firstCheck))
        await fixture.server.readReply(b + "/activity", body: activities(secondRow, cursor: "b-next"))
        await fixture.server.readReply(b + "/balance-checks", body: checks(secondCheck))
        let firstRead = Task { await loop.open(first) }
        await held.waitUntilStarted()
        await loop.open(second)
        XCTAssertEqual(loop.read(second.id).activity.map(\.recordId), [secondRow])
        await held.release(); await firstRead.value
        XCTAssertEqual(loop.read(first.id).activity.map(\.recordId), [firstRow])
        XCTAssertEqual(loop.read(first.id).checks.map(\.recordId), [firstCheck])
        XCTAssertEqual(loop.read(second.id).activity.map(\.recordId), [secondRow])
        XCTAssertEqual(loop.read(second.id).checks.map(\.recordId), [secondCheck])

        let delayedPage = RequestGate(), obsolete = UUID(), nextB = UUID(), refreshedA = UUID()
        await fixture.server.readReply(a + "/activity?cursor=a-next", body: activities(obsolete), gate: delayedPage)
        await fixture.server.readReply(b + "/activity?cursor=b-next", body: activities(nextB))
        let oldPage = Task { await loop.more(first, checks: false) }
        await delayedPage.waitUntilStarted()
        await loop.more(second, checks: false)
        XCTAssertEqual(loop.read(second.id).activity.map(\.recordId), [secondRow, nextB])
        await fixture.server.readReply(a + "/activity", body: activities(refreshedA))
        await loop.open(first)
        await delayedPage.release(); await oldPage.value
        XCTAssertEqual(loop.read(first.id).activity.map(\.recordId), [refreshedA])
        XCTAssertFalse(loop.read(first.id).loadingMore)
        XCTAssertEqual(loop.read(second.id).checks.map(\.recordId), [secondCheck])
        await fixture.server.readReply(b + "/activity", body: #"{"code":"unavailable"}"#, status: 503)
        await loop.open(second)
        XCTAssertNotNil(loop.read(second.id).errorKey)
        XCTAssertNil(loop.read(first.id).errorKey)
        loop.bind(nil)
        XCTAssertTrue(loop.accountReads.isEmpty)
    }
}
