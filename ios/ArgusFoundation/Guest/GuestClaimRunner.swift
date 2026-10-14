import ArgusSession
import CryptoKit
import CuadraoBook
import Foundation

/// The server calls a claim needs, so the engine runs the same against the real session and against a test double.
protocol GuestClaimServer: Sendable {
    /// The signed-in person, or nil when no one is signed in.
    func owner() async -> UUID?
    func accounts() async throws -> [FinancialAccount]
    func createAccount(_ request: CreateFinancialAccountRequest) async throws -> FinancialAccount
    func setArchived(_ id: UUID, version: Int) async throws -> FinancialAccount
    func preview(_ command: FinancialActivityCommand) async throws -> FinancialActivityPreview
    func confirm(_ write: PendingFinancialConfirmation) async throws -> FinancialActivityReceipt
}

/// Stable keys: the same book item for the same person always sends the same key, so a retry after a dropped
/// answer or a closed app returns the record the server already made instead of making a second one.
enum GuestClaimKeys {
    static func key(owner: UUID, kind: String, item: UUID) -> UUID {
        let digest = SHA256.hash(data: Data("cuadrao.guest-claim.\(owner.uuidString).\(kind).\(item.uuidString)".utf8))
        var bytes = Array(digest.prefix(16))
        bytes[6] = (bytes[6] & 0x0F) | 0x50
        bytes[8] = (bytes[8] & 0x3F) | 0x80
        return UUID(uuid: (bytes[0], bytes[1], bytes[2], bytes[3], bytes[4], bytes[5], bytes[6], bytes[7],
                           bytes[8], bytes[9], bytes[10], bytes[11], bytes[12], bytes[13], bytes[14], bytes[15]))
    }
}

/// Where a claim stopped, in words the screen can turn into a sentence.
enum GuestClaimStop: Equatable, Sendable {
    /// Nobody is signed in, or the session changed under the claim.
    case signedOut
    /// The server turned an account down; the movements that need it cannot follow.
    case accountRefused(name: String?)
    /// No answer or a server error. Everything confirmed so far is kept, and trying again continues from there.
    case unreachable
}

struct GuestClaimResult: Equatable, Sendable {
    var accountsMoved = 0
    var movementsMoved = 0
    /// Movements the server would not take as they are. They stay in the book.
    var movementsRefused = 0
    var stop: GuestClaimStop?
    var completed: Bool { stop == nil }
}

/// Moves a `GuestClaimPlan` into the signed-in account, one confirmed item at a time. The book is only read here:
/// nothing in it is changed or removed. What the server confirmed is written to the progress file after each item.
struct GuestClaimEngine {
    let server: any GuestClaimServer
    /// Called with the progress after every confirmed item.
    var save: @Sendable (GuestClaimProgress) -> Void = { _ in }
    /// Called after each item with how many of the total are done.
    var report: @Sendable (_ done: Int, _ total: Int) -> Void = { _, _ in }

    func run(plan: GuestClaimPlan, progress start: GuestClaimProgress) async -> (GuestClaimResult, GuestClaimProgress) {
        var result = GuestClaimResult()
        var progress = start
        guard let owner = await server.owner() else { result.stop = .signedOut; return (result, progress) }
        var mine = progress.owner(owner)
        let total = plan.accounts.count + plan.movements.count
        var done = plan.accounts.filter { mine.accounts[$0.id] != nil }.count
            + plan.movements.filter { mine.movements.contains($0.id) || mine.refused.contains($0.id) }.count
        report(done, total)
        var versions: [UUID: Int] = [:]
        do {
            for account in try await server.accounts() { versions[account.id] = account.version }
        } catch { result.stop = Self.stop(for: error); return (result, progress) }

        func commit() { progress.owners[owner] = mine; save(progress) }

        for account in plan.accounts where mine.accounts[account.id] == nil {
            do {
                var created = try await server.createAccount(Self.request(account, key: GuestClaimKeys.key(owner: owner, kind: "account", item: account.id)))
                if account.archived, !created.archived { created = try await server.setArchived(created.id, version: created.version) }
                mine.accounts[account.id] = created.id
                versions[created.id] = created.version
                result.accountsMoved += 1
                done += 1
                commit(); report(done, total)
            } catch {
                result.stop = Self.stop(for: error, account: account.nickname); commit(); return (result, progress)
            }
        }

        for movement in plan.movements where !mine.movements.contains(movement.id) && !mine.refused.contains(movement.id) {
            guard let from = mine.accounts[movement.accountID],
                  movement.counterpartID == nil || mine.accounts[movement.counterpartID!] != nil else {
                mine.refused.insert(movement.id); result.movementsRefused += 1; done += 1; commit(); report(done, total); continue
            }
            let to = movement.counterpartID.flatMap { mine.accounts[$0] }
            do {
                let receipt = try await Self.move(movement, from: from, to: to, owner: owner, versions: versions, server: server)
                for account in receipt.accounts { versions[account.id] = account.version }
                mine.movements.insert(movement.id)
                result.movementsMoved += 1
            } catch let error as SessionFailure {
                if case .rejected(let status, _) = error, (400..<500).contains(status), status != 408, status != 401, status != 429 {
                    mine.refused.insert(movement.id); result.movementsRefused += 1
                } else { result.stop = Self.stop(for: error); commit(); return (result, progress) }
            } catch Refusal.notReady {
                mine.refused.insert(movement.id); result.movementsRefused += 1
            } catch { result.stop = .unreachable; commit(); return (result, progress) }
            done += 1
            commit(); report(done, total)
        }
        return (result, progress)
    }

    private enum Refusal: Error { case notReady }

    private static func move(_ movement: GuestClaimPlan.Movement, from: UUID, to: UUID?, owner: UUID, versions: [UUID: Int],
                             server: any GuestClaimServer) async throws -> FinancialActivityReceipt {
        let formatter = ISO8601DateFormatter()
        formatter.timeZone = TimeZone(identifier: movement.timeZone) ?? .gmt
        let paired = movement.kind == .transfer
        var involved = [from]
        if let to { involved.append(to) }
        let command = FinancialActivityCommand(
            kind: paired ? .transfer : (movement.kind == .income ? .income : .expense),
            accountId: paired ? nil : from, sourceAccountId: paired ? from : nil, destinationAccountId: paired ? to : nil,
            amount: movement.amountText, occurredAt: formatter.string(from: movement.occurredAt), timeZone: movement.timeZone,
            note: movement.note, categoryId: movement.kind == .expense ? movement.category?.rawValue : nil,
            expectedVersions: involved.reduce(into: [String: Int]()) { values, id in versions[id].map { values[id.uuidString] = $0 } })
        let preview = try await server.preview(command)
        guard preview.ready, var reviewed = preview.reviewedRequest, let token = preview.previewToken else { throw Refusal.notReady }
        reviewed.previewToken = token
        let encoder = JSONEncoder(); encoder.outputFormatting = .sortedKeys
        let write = PendingFinancialConfirmation(
            ownerId: owner, originAccountId: from, route: "financial-activities", path: "", method: "POST",
            body: try encoder.encode(reviewed), key: GuestClaimKeys.key(owner: owner, kind: "movement", item: movement.id))
        return try await server.confirm(write)
    }

    static func request(_ account: GuestClaimPlan.Account, key: UUID) -> CreateFinancialAccountRequest {
        let formatter = ISO8601DateFormatter()
        return CreateFinancialAccountRequest(
            type: account.kind.rawValue, currency: account.currency, nickname: account.nickname, amount: account.amountText,
            asOf: account.amountText == nil ? nil : account.asOf.map { formatter.string(from: $0) },
            timeZone: account.amountText == nil ? nil : account.timeZone, ownershipShareBps: account.shareBps, idempotencyKey: key)
    }

    private static func stop(for error: Error, account: String? = nil) -> GuestClaimStop {
        guard let failure = error as? SessionFailure else { return .unreachable }
        switch failure {
        case .unauthorized, .staleOperation, .credentialValidationRequired, .pendingSignOut: return .signedOut
        case .rejected(let status, _) where (400..<500).contains(status) && status != 408 && status != 429:
            return status == 401 ? .signedOut : .accountRefused(name: account)
        default: return .unreachable
        }
    }
}

/// The claim's progress, kept in the book's own folder so deleting the book removes it too.
struct GuestClaimProgressFile {
    let directory: URL
    private var url: URL { directory.appendingPathComponent("guest-claim.json") }

    func load() -> GuestClaimProgress {
        (try? JSONDecoder().decode(GuestClaimProgress.self, from: Data(contentsOf: url))) ?? GuestClaimProgress()
    }

    func save(_ progress: GuestClaimProgress) {
        guard let data = try? JSONEncoder().encode(progress), FileManager.default.fileExists(atPath: directory.path) else { return }
        try? data.write(to: url, options: [.atomic])
    }
}
