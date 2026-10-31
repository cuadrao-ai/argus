import Foundation

/// The nine account types, with the server's ids (`ACCOUNT_TYPES`).
public enum AccountKind: String, Codable, CaseIterable, Sendable {
    case cash, checking, savings, investment
    case creditCard = "credit_card"
    case otherDebt = "other_debt"
    case property, vehicle
    case otherAsset = "other_asset"

    /// A liability's typed amount owed is stored negative, once, here and nowhere else.
    public var isLiability: Bool { self == .creditCard || self == .otherDebt }
    /// Property, vehicle and other assets are estimates the person owns a share of.
    public var isOptionalAsset: Bool { self == .property || self == .vehicle || self == .otherAsset }
}

/// A balance the person stated, from which movements will be counted. The account has none until then:
/// an unknown balance is not zero.
public struct Opening: Codable, Equatable, Sendable {
    /// Owner-signed minor units: negative when money is owed.
    public var amountMinor: Int64
    /// The instant tracking starts; movements before it do not change the balance.
    public var asOf: Date
    /// The device's IANA zone when it was stated.
    public var timeZone: String

    public init(amountMinor: Int64, asOf: Date, timeZone: String) {
        self.amountMinor = amountMinor
        self.asOf = asOf
        self.timeZone = timeZone
    }
}

public struct BookAccount: Codable, Equatable, Identifiable, Sendable {
    public let id: UUID
    public var kind: AccountKind
    public var currency: String
    /// Fixed when the currency is chosen, so a later table change cannot reread stored amounts.
    public var digits: Int
    public var nickname: String?
    public var archived: Bool
    public var ownershipShareBps: Int
    public var opening: Opening?
    public let createdAt: Date

    public init(id: UUID, kind: AccountKind, currency: String, digits: Int, nickname: String?, archived: Bool = false,
                ownershipShareBps: Int = Ownership.fullShareBps, opening: Opening? = nil, createdAt: Date) {
        self.id = id
        self.kind = kind
        self.currency = currency
        self.digits = digits
        self.nickname = nickname
        self.archived = archived
        self.ownershipShareBps = ownershipShareBps
        self.opening = opening
        self.createdAt = createdAt
    }

    /// The balance as first stated, before any movement. `DeviceBook.balance(of:)` is what the person reads now.
    public var openingBalance: Money? {
        opening.map { Money(minor: $0.amountMinor, currency: currency, digits: digits) }
    }
}

/// What the account form collects. Amount text is as typed; blank means the balance stays unknown.
public struct BookAccountDraft: Equatable, Sendable {
    public var kind: AccountKind
    public var currency: String
    public var nickname: String
    public var amountText: String
    public var shareBps: Int

    public init(kind: AccountKind, currency: String, nickname: String = "", amountText: String = "",
                shareBps: Int = Ownership.fullShareBps) {
        self.kind = kind
        self.currency = currency
        self.nickname = nickname
        self.amountText = amountText
        self.shareBps = shareBps
    }
}

extension DeviceBook {
    public func account(_ id: UUID) -> BookAccount? { accounts.first { $0.id == id } }
    public var activeAccounts: [BookAccount] { accounts.filter { !$0.archived } }
    public var archivedAccounts: [BookAccount] { accounts.filter(\.archived) }

    /// Whether anything depends on the account's currency and type: a stated balance or a movement, deleted or not.
    public func hasRecords(_ id: UUID) -> Bool {
        account(id)?.opening != nil || movements.contains { $0.effect(on: id) != nil }
    }

    public func addingAccount(_ draft: BookAccountDraft, id: UUID = UUID(), now: Date = Date(),
                              zone: String = TimeZone.current.identifier) throws -> DeviceBook {
        guard accounts.count < Limits.accounts else { throw BookRuleError.accountLimit }
        guard let currency = CurrencyTable.currency(draft.currency) else { throw BookRuleError.currencyUnsupported }
        let share = try Self.share(draft.shareBps, kind: draft.kind)
        var account = BookAccount(id: id, kind: draft.kind, currency: currency.code, digits: currency.digits,
                                  nickname: try Self.nickname(draft.nickname), ownershipShareBps: share, createdAt: Self.wholeSeconds(now))
        account.opening = try Self.opening(draft.amountText, kind: draft.kind, digits: currency.digits, now: now, zone: zone)
        var next = self
        next.accounts.append(account)
        next.revision += 1
        return next
    }

    /// Edits name, type, currency and the stated balance together, as the form does. Blank amount clears the balance
    /// back to unknown. The currency and the type are kept once the account has a stated balance.
    public func editingAccount(_ id: UUID, with draft: BookAccountDraft, now: Date = Date(),
                               zone: String = TimeZone.current.identifier) throws -> DeviceBook {
        guard let index = accounts.firstIndex(where: { $0.id == id }) else { throw BookRuleError.accountNotFound }
        var account = accounts[index]
        let locked = hasRecords(id)
        if draft.kind != account.kind {
            guard !locked else { throw BookRuleError.kindLocked }
        }
        let code = draft.currency.trimmingCharacters(in: .whitespaces).uppercased()
        if code != account.currency {
            guard !locked else { throw BookRuleError.currencyLocked }
            guard let currency = CurrencyTable.currency(code) else { throw BookRuleError.currencyUnsupported }
            account.currency = currency.code
            account.digits = currency.digits
        }
        account.kind = draft.kind
        account.nickname = try Self.nickname(draft.nickname)
        if account.kind.isOptionalAsset { account.ownershipShareBps = try Self.share(draft.shareBps, kind: account.kind) }
        let stated = try Self.opening(draft.amountText, kind: account.kind, digits: account.digits, now: now, zone: zone)
        // An amount equal to the balance the person reads now keeps the tracking start; a different or newly stated
        // one starts tracking now, so earlier movements are already inside it.
        if let stated, let current = account.opening, stated.amountMinor == balance(of: id)?.minor {
            account.opening = current
        } else {
            account.opening = stated
        }
        var next = self
        next.accounts[index] = account
        next.revision += 1
        return next
    }

    public func renamingAccount(_ id: UUID, to nickname: String) throws -> DeviceBook {
        guard let index = accounts.firstIndex(where: { $0.id == id }) else { throw BookRuleError.accountNotFound }
        var next = self
        next.accounts[index].nickname = try Self.nickname(nickname)
        next.revision += 1
        return next
    }

    public func settingArchived(_ id: UUID, _ archived: Bool) throws -> DeviceBook {
        guard let index = accounts.firstIndex(where: { $0.id == id }) else { throw BookRuleError.accountNotFound }
        guard accounts[index].archived != archived else { return self }
        var next = self
        next.accounts[index].archived = archived
        next.revision += 1
        return next
    }

    /// Puts the active accounts in the given order. Archived accounts stay where they are in the list.
    public func reorderingActive(_ ids: [UUID]) throws -> DeviceBook {
        let active = activeAccounts
        guard ids.count == active.count, Set(ids) == Set(active.map(\.id)) else { throw BookRuleError.orderInvalid }
        let ordered = ids.compactMap { id in active.first { $0.id == id } }
        var queue = ordered[...]
        var next = self
        next.accounts = accounts.map { account in
            guard !account.archived, let replacement = queue.popFirst() else { return account }
            return replacement
        }
        next.revision += 1
        return next
    }

    // MARK: Validation shared by the rules above

    static func nickname(_ text: String) throws -> String? {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmed.unicodeScalars.count <= Limits.nickname else { throw BookRuleError.nicknameTooLong }
        return trimmed.isEmpty ? nil : trimmed
    }

    static func share(_ bps: Int, kind: AccountKind) throws -> Int {
        guard kind.isOptionalAsset else { return Ownership.fullShareBps }
        guard (1...Ownership.fullShareBps).contains(bps) else { throw BookRuleError.shareInvalid }
        return bps
    }

    /// Typed amount to a stated balance. Blank is unknown (nil), never zero. A debt or an asset is typed positive.
    static func opening(_ text: String, kind: AccountKind, digits: Int, now: Date, zone: String) throws -> Opening? {
        guard !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return nil }
        let typed: Int64
        switch MoneyParser.parseTyped(text, digits: digits) {
        case .success(let value): typed = value
        case .failure(let error): throw BookRuleError.amount(error)
        }
        if (kind.isLiability || kind.isOptionalAsset), typed < 0 { throw BookRuleError.negativeAmount }
        guard Limits.withinAmount(typed) else { throw BookRuleError.amountTooLarge }
        return Opening(amountMinor: kind.isLiability ? -typed : typed, asOf: wholeSeconds(now), timeZone: zone)
    }

    /// The file keeps instants to the second, so the book in memory does too and a reload changes nothing.
    static func wholeSeconds(_ date: Date) -> Date {
        Date(timeIntervalSince1970: date.timeIntervalSince1970.rounded(.down))
    }
}
