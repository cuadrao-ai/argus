import Foundation

/// What moving the on-device book into a signed-in account would do, worked out before anything moves so the person
/// can read it first. Pure: it reads the book and the names the account already has, and sends nothing.
///
/// Accounts and their movements move. Plans (goals and budgets) and receipt files stay on this iPhone: the server's
/// goals are backed by account balances, not by amounts typed by hand, so a hand-counted goal has no server twin yet.
public struct GuestClaimPlan: Equatable, Sendable {
    public struct Account: Equatable, Identifiable, Sendable {
        public let id: UUID
        public let kind: AccountKind
        public let currency: String
        /// The name it will have in the account; nil when the person never named it.
        public let nickname: String?
        /// True when the name was already taken in the account and "(invitado)" was added.
        public let renamed: Bool
        /// The stated balance as the server takes it: positive for a debt, nil while the balance is unknown.
        public let amountText: String?
        public let asOf: Date?
        public let timeZone: String?
        public let shareBps: Int
        public let archived: Bool
    }

    public struct Movement: Equatable, Identifiable, Sendable {
        public let id: UUID
        public let kind: MovementKind
        public let accountID: UUID
        public let counterpartID: UUID?
        public let amountText: String
        public let occurredAt: Date
        public let timeZone: String
        public let note: String?
        public let category: ExpenseCategory?
    }

    /// In the order the book lists them, so the account shows them the same way.
    public let accounts: [Account]
    /// Oldest first, so each balance is built up the way it happened. Deleted movements are left out.
    public let movements: [Movement]
    /// Goals and budgets that stay on this iPhone.
    public let stayingPlans: Int

    public var isEmpty: Bool { accounts.isEmpty && movements.isEmpty }
    public var renamedAccounts: Int { accounts.filter(\.renamed).count }

    /// `existingNicknames` are the names the signed-in account already uses. `guestWord` is the word added to a name
    /// that is already taken: "(invitado)" in Spanish.
    public static func make(book: DeviceBook, existingNicknames: [String], guestWord: String = "invitado") -> GuestClaimPlan {
        var taken = Set(existingNicknames.map(Self.normalized))
        var accounts: [Account] = []
        for account in book.accounts {
            var nickname = account.nickname
            var renamed = false
            if let name = nickname {
                if taken.contains(Self.normalized(name)) {
                    nickname = Self.freeName(for: name, guestWord: guestWord, taken: taken)
                    renamed = true
                }
                taken.insert(Self.normalized(nickname ?? name))
            }
            accounts.append(Account(
                id: account.id, kind: account.kind, currency: account.currency, nickname: nickname, renamed: renamed,
                amountText: account.opening.map { MoneyFormatter.plain(abs($0.amountMinor), digits: account.digits) },
                asOf: account.opening?.asOf, timeZone: account.opening?.timeZone,
                shareBps: account.ownershipShareBps, archived: account.archived))
        }
        let known = Set(book.accounts.map(\.id))
        let movements = book.movements
            .filter { !$0.deleted && known.contains($0.accountID) && ($0.counterpartID.map(known.contains) ?? true) }
            .sorted { ($0.occurredAt, $0.createdAt) < ($1.occurredAt, $1.createdAt) }
            .map { movement -> Movement in
                let digits = book.account(movement.accountID)?.digits ?? 2
                return Movement(id: movement.id, kind: movement.kind, accountID: movement.accountID,
                                counterpartID: movement.counterpartID, amountText: MoneyFormatter.plain(movement.amountMinor, digits: digits),
                                occurredAt: movement.occurredAt, timeZone: movement.timeZone, note: movement.note,
                                category: movement.category)
            }
        return GuestClaimPlan(accounts: accounts, movements: movements, stayingPlans: book.plans.filter { !$0.archived }.count)
    }

    /// Names compare without case or accents, as a person reads them.
    static func normalized(_ name: String) -> String {
        name.trimmingCharacters(in: .whitespacesAndNewlines).folding(options: [.caseInsensitive, .diacriticInsensitive], locale: nil)
    }

    /// "Name (invitado)", then "Name (invitado 2)" and so on, cut so the whole name stays inside the nickname limit.
    private static func freeName(for name: String, guestWord: String, taken: Set<String>) -> String {
        var attempt = 1
        while true {
            let suffix = attempt == 1 ? " (\(guestWord))" : " (\(guestWord) \(attempt))"
            let room = max(1, Limits.nickname - suffix.unicodeScalars.count)
            let base = String(String.UnicodeScalarView(name.unicodeScalars.prefix(room))).trimmingCharacters(in: .whitespaces)
            let candidate = base + suffix
            if !taken.contains(normalized(candidate)) { return candidate }
            attempt += 1
        }
    }
}

/// What a claim has already put in the account, kept beside the book so a retry after a failure or a closed app
/// skips it. Keyed by the signed-in owner, so a different person signing in on this iPhone starts from nothing.
public struct GuestClaimProgress: Codable, Equatable, Sendable {
    public struct Owner: Codable, Equatable, Sendable {
        /// Book account id to the account id the server gave it.
        public var accounts: [UUID: UUID] = [:]
        /// Movements the server confirmed.
        public var movements: Set<UUID> = []
        /// Movements the server would not take as they are; they stay in the book and are counted for the person.
        public var refused: Set<UUID> = []

        public init(accounts: [UUID: UUID] = [:], movements: Set<UUID> = [], refused: Set<UUID> = []) {
            self.accounts = accounts
            self.movements = movements
            self.refused = refused
        }
    }

    public var owners: [UUID: Owner] = [:]

    public init(owners: [UUID: Owner] = [:]) { self.owners = owners }

    public func owner(_ id: UUID) -> Owner { owners[id] ?? Owner() }
}
