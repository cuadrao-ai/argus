import Auth
import CryptoKit
import Foundation

/// The exact request a person confirmed. The body includes the reviewed versions
/// and preview token; a retry sends these same bytes with the same key.
public struct PendingFinancialConfirmation: Codable, Equatable, Sendable {
    public let ownerId: UUID
    public let originAccountId: UUID?
    public let route: String
    public let path: String
    public let method: String
    public let body: Data
    public let key: UUID
    public let planOperation: FinancialPlanOperation?
    public let householdMembershipId: UUID?
    public let householdAuthorizationVersion: Int?
    public let householdOperation: HouseholdWriteOperation?

    public init(ownerId: UUID, originAccountId: UUID?, route: String, path: String,
                method: String, body: Data, key: UUID, planOperation: FinancialPlanOperation? = nil, householdMembershipId: UUID? = nil, householdAuthorizationVersion: Int? = nil, householdOperation: HouseholdWriteOperation? = nil) {
        self.ownerId = ownerId
        self.originAccountId = originAccountId
        self.route = route
        self.path = path
        self.method = method
        self.body = body
        self.key = key
        self.planOperation = planOperation
        self.householdMembershipId = householdMembershipId
        self.householdAuthorizationVersion = householdAuthorizationVersion
        self.householdOperation = householdOperation
    }
    enum CodingKeys: String, CodingKey {
        case ownerId, originAccountId, route, path, method, body, key, planOperation, householdMembershipId, householdAuthorizationVersion, householdOperation
    }
    public init(from decoder: any Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        ownerId = try c.decode(UUID.self, forKey: .ownerId); originAccountId = try c.decodeIfPresent(UUID.self, forKey: .originAccountId)
        route = try c.decode(String.self, forKey: .route); path = try c.decode(String.self, forKey: .path)
        method = try c.decode(String.self, forKey: .method); body = try c.decode(Data.self, forKey: .body); key = try c.decode(UUID.self, forKey: .key)
        planOperation = try c.decodeIfPresent(FinancialPlanOperation.self, forKey: .planOperation)
        householdMembershipId = try c.decodeIfPresent(UUID.self, forKey: .householdMembershipId)
        householdAuthorizationVersion = try c.decodeIfPresent(Int.self, forKey: .householdAuthorizationVersion)
        if let stored = try c.decodeIfPresent(HouseholdWriteOperation.self, forKey: .householdOperation) { householdOperation = stored }
        else if route == "households" {
            let parts = path.split(separator: "/")
            let exactPath = path == "/" + parts.joined(separator: "/")
            if exactPath, parts.count == 2, parts[1] == "activities", let id = UUID(uuidString: String(parts[0])), method == "POST" {
                householdOperation = .activity(householdId: id, activityId: nil)
            } else if exactPath, parts.count == 3, parts[1] == "activities", let id = UUID(uuidString: String(parts[0])), let activity = UUID(uuidString: String(parts[2])), method == "PATCH" {
                householdOperation = .activity(householdId: id, activityId: activity)
            } else { householdOperation = .management }
        } else { householdOperation = nil }
    }
}

public enum FinancialWriteJournalError: Error, Equatable, Sendable {
    case pendingConfirmation
    case invalidIdentity
    case storageUnavailable
}

/// One outstanding confirmed write per owner and API environment. It never
/// dispatches a request: recovery always requires an explicit user action.
public final class FinancialWriteJournal: @unchecked Sendable {
    private let lock = NSLock()
    private let storage: any AuthLocalStorage
    private let prefix: String

    public convenience init(configuration: SessionConfiguration, namespace: String = "") {
        self.init(storage: DeviceKeychain(service: configuration.keychainService), prefix: configuration.storagePrefix + namespace)
    }

    init(storage: any AuthLocalStorage, prefix: String) {
        self.storage = storage
        self.prefix = prefix
    }

    public func pending(for identity: SessionSnapshot) throws -> PendingFinancialConfirmation? {
        let owner = try Self.owner(identity)
        return try locked { try read(owner: owner) }
    }

    public func begin(_ write: PendingFinancialConfirmation, for identity: SessionSnapshot) throws {
        let owner = try Self.owner(identity)
        guard write.ownerId == owner, !write.body.isEmpty,
              write.method == "POST" || write.method == "PATCH" || write.method == "PUT" || write.method == "DELETE",
              !write.route.isEmpty, (write.path.isEmpty || write.path.hasPrefix("/")), !write.path.hasPrefix("//")
        else { throw FinancialWriteJournalError.invalidIdentity }
        try locked {
            if let existing = try read(owner: owner) {
                guard existing == write else { throw FinancialWriteJournalError.pendingConfirmation }
                return
            }
            do { try storage.store(key: storageKey(owner: owner), value: JSONEncoder().encode(write)) }
            catch { throw FinancialWriteJournalError.storageUnavailable }
        }
    }

    public func clear(_ write: PendingFinancialConfirmation, for identity: SessionSnapshot) throws {
        let owner = try Self.owner(identity)
        guard write.ownerId == owner else { throw FinancialWriteJournalError.invalidIdentity }
        try locked {
            guard let existing = try read(owner: owner), existing == write else { return }
            do { try storage.remove(key: storageKey(owner: owner)) }
            catch { throw FinancialWriteJournalError.storageUnavailable }
        }
    }

    private static func owner(_ identity: SessionSnapshot) throws -> UUID {
        guard identity.phase == .authenticated,
              let id = identity.profile?.id,
              let owner = UUID(uuidString: id)
        else { throw FinancialWriteJournalError.invalidIdentity }
        return owner
    }

    private func read(owner: UUID) throws -> PendingFinancialConfirmation? {
        do {
            guard let data = try storage.retrieve(key: storageKey(owner: owner)) else { return nil }
            let write = try JSONDecoder().decode(PendingFinancialConfirmation.self, from: data)
            guard write.ownerId == owner else { throw FinancialWriteJournalError.storageUnavailable }
            return write
        } catch { throw FinancialWriteJournalError.storageUnavailable }
    }

    private func storageKey(owner: UUID) -> String {
        let digest = SHA256.hash(data: Data(owner.uuidString.utf8)).map { String(format: "%02x", $0) }.joined()
        return prefix + ".financial-confirmation." + digest
    }

    private func locked<T>(_ operation: () throws -> T) rethrows -> T {
        lock.lock(); defer { lock.unlock() }
        return try operation()
    }
}
