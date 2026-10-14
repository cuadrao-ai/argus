#if DEBUG
import ArgusSession
import Foundation

/// A stand-in server for the claim, so its screens and its engine run without a network. It confirms what it is
/// sent in memory, answers a repeated key with the record it already made, and can be told to fail.
actor SampleGuestClaimServer: GuestClaimServer {
    struct Script: Sendable {
        /// Names the signed-in account already has.
        var existingNames: [String] = []
        /// After this many accounts were created, the next create fails as unreachable.
        var failCreateAfter: Int?
        /// A movement with one of these notes is not ready on the server and is refused.
        var refuseNotes: Set<String> = []
        /// After this many movements were confirmed, the next confirm fails as unreachable.
        var failConfirmAfter: Int?
        var delay: Duration = .zero
    }

    nonisolated let ownerID: UUID
    private(set) var script: Script
    private var accountsByID: [UUID: [String: Any]] = [:]
    private var accountsByKey: [UUID: UUID] = [:]
    private var confirmedKeys: Set<UUID> = []
    private(set) var createdAccounts = 0
    private(set) var confirmedMovements = 0
    private(set) var requests: [CreateFinancialAccountRequest] = []
    private(set) var commands: [FinancialActivityCommand] = []
    private let ownerSnapshot: Bool

    init(owner: UUID = UUID(), script: Script = Script(), signedIn: Bool = true) {
        ownerID = owner
        self.script = script
        ownerSnapshot = signedIn
        let formatter = ISO8601DateFormatter()
        let now = formatter.string(from: Date())
        for (index, name) in script.existingNames.enumerated() {
            let id = UUID()
            accountsByID[id] = Self.account(id: id, type: "checking", currency: "DOP", nickname: name, archived: false, version: 1, now: now + "#\(index)")
        }
    }

    func setScript(_ next: Script) { script = next }

    func owner() async -> UUID? { ownerSnapshot ? ownerID : nil }

    func accounts() async throws -> [FinancialAccount] { try accountsByID.values.map(Self.decode) }

    func createAccount(_ request: CreateFinancialAccountRequest) async throws -> FinancialAccount {
        try await pause()
        if let id = accountsByKey[request.idempotencyKey], let existing = accountsByID[id] { return try Self.decode(existing) }
        if let limit = script.failCreateAfter, createdAccounts >= limit { throw SessionFailure.unavailable }
        let id = UUID()
        let value = Self.account(id: id, type: request.type, currency: request.currency, nickname: request.nickname, archived: false,
                                 version: 1, now: ISO8601DateFormatter().string(from: Date()))
        accountsByID[id] = value
        accountsByKey[request.idempotencyKey] = id
        createdAccounts += 1
        requests.append(request)
        return try Self.decode(value)
    }

    func setArchived(_ id: UUID, version: Int) async throws -> FinancialAccount {
        guard var value = accountsByID[id] else { throw SessionFailure.rejected(status: 404, code: "not_found") }
        value["archived"] = true
        value["version"] = version + 1
        accountsByID[id] = value
        return try Self.decode(value)
    }

    func preview(_ command: FinancialActivityCommand) async throws -> FinancialActivityPreview {
        try await pause()
        // The real server answers 422 to a plain transfer into a credit card: it is a card payment.
        if command.kind == .transfer, let to = command.destinationAccountId, accountsByID[to]?["type"] as? String == "credit_card" {
            throw SessionFailure.rejected(status: 422, code: "card_payment_required")
        }
        let ready = !(command.note.map(script.refuseNotes.contains) ?? false)
        let encoder = JSONEncoder(); encoder.outputFormatting = .sortedKeys
        let reviewed = try JSONSerialization.jsonObject(with: encoder.encode(command))
        let body: [String: Any] = ["ready": ready, "expected_versions": [String: Int](), "affected_accounts": [Any](),
                                   "reviewed_request": reviewed, "preview_token": "token"]
        return try JSONDecoder().decode(FinancialActivityPreview.self, from: JSONSerialization.data(withJSONObject: body))
    }

    func confirm(_ write: PendingFinancialConfirmation) async throws -> FinancialActivityReceipt {
        try await pause()
        let command = try JSONDecoder().decode(FinancialActivityCommand.self, from: write.body)
        let replay = confirmedKeys.contains(write.key)
        if !replay {
            if let limit = script.failConfirmAfter, confirmedMovements >= limit { throw SessionFailure.unavailable }
            confirmedKeys.insert(write.key)
            confirmedMovements += 1
            commands.append(command)
        }
        let ids = [command.accountId, command.sourceAccountId, command.destinationAccountId].compactMap { $0 }
        for id in ids { if var value = accountsByID[id] { value["version"] = (value["version"] as? Int ?? 1) + (replay ? 0 : 1); accountsByID[id] = value } }
        let activity: [String: Any] = [
            "activity_id": UUID().uuidString, "revision": 1, "kind": command.kind.rawValue, "currency": "DOP",
            "currency_fraction_digits": 2, "occurred_at": command.occurredAt, "time_zone": command.timeZone,
            "recorded_at": command.occurredAt, "legs": [Any]()]
        let body: [String: Any] = ["activity": activity, "accounts": ids.compactMap { accountsByID[$0] }, "replayed": replay]
        return try JSONDecoder().decode(FinancialActivityReceipt.self, from: JSONSerialization.data(withJSONObject: body))
    }

    private func pause() async throws {
        if script.delay > .zero { try await Task.sleep(for: script.delay) }
    }

    private static func decode(_ value: [String: Any]) throws -> FinancialAccount {
        try JSONDecoder().decode(FinancialAccount.self, from: JSONSerialization.data(withJSONObject: value))
    }

    private static func account(id: UUID, type: String, currency: String, nickname: String?, archived: Bool, version: Int, now: String) -> [String: Any] {
        var value: [String: Any] = [
            "id": id.uuidString, "type": type, "nature": ["credit_card", "other_debt"].contains(type) ? "liability" : "asset",
            "currency": currency, "currency_fraction_digits": 2, "archived": archived, "ownership_share_bps": 10_000,
            "version": version, "created_at": "2026-10-14T12:00:00Z", "updated_at": "2026-10-14T12:00:00Z",
            "balance": ["state": "unknown", "activity_since_tracking_minor": 0]]
        if let nickname { value["nickname"] = nickname }
        return value
    }
}
#endif
