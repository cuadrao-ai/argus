import Foundation

public enum MovementKind: String, Codable, CaseIterable, Sendable {
    case expense, income, transfer
}

/// One recorded movement. The amount is a positive count of the source account's minor units; the kind decides which
/// way it moves money. A transfer moves it between two accounts of the same currency.
public struct Movement: Codable, Equatable, Identifiable, Sendable {
    public let id: UUID
    public var kind: MovementKind
    public var accountID: UUID
    /// The receiving account of a transfer.
    public var counterpartID: UUID?
    public var amountMinor: Int64
    /// The instant it happened, never in the future when recorded.
    public var occurredAt: Date
    /// The device's IANA zone when it was recorded; the month it belongs to is read in this zone.
    public var timeZone: String
    public var note: String?
    public var category: ExpenseCategory?
    /// Deleted movements stay in the book until the book is deleted, so a delete can be undone.
    public var deleted: Bool
    public let createdAt: Date

    public init(id: UUID, kind: MovementKind, accountID: UUID, counterpartID: UUID? = nil, amountMinor: Int64, occurredAt: Date,
                timeZone: String, note: String? = nil, category: ExpenseCategory? = nil, deleted: Bool = false, createdAt: Date) {
        self.id = id
        self.kind = kind
        self.accountID = accountID
        self.counterpartID = counterpartID
        self.amountMinor = amountMinor
        self.occurredAt = occurredAt
        self.timeZone = timeZone
        self.note = note
        self.category = category
        self.deleted = deleted
        self.createdAt = createdAt
    }

    /// The signed change this movement makes to an account's owner-signed balance, or nil if it does not touch it.
    public func effect(on account: UUID) -> Int64? {
        if account == accountID {
            switch kind {
            case .expense, .transfer: return -amountMinor
            case .income: return amountMinor
            }
        }
        if kind == .transfer, account == counterpartID { return amountMinor }
        return nil
    }
}

/// What the movement form collects. Amount is as typed.
public struct MovementDraft: Equatable, Sendable {
    public var kind: MovementKind
    public var accountID: UUID
    public var counterpartID: UUID?
    public var amountText: String
    public var occurredAt: Date
    public var note: String
    public var category: ExpenseCategory

    public init(kind: MovementKind, accountID: UUID, counterpartID: UUID? = nil, amountText: String, occurredAt: Date,
                note: String = "", category: ExpenseCategory = .other) {
        self.kind = kind
        self.accountID = accountID
        self.counterpartID = counterpartID
        self.amountText = amountText
        self.occurredAt = occurredAt
        self.note = note
        self.category = category
    }
}

extension DeviceBook {
    public static let movementLimit = 10_000

    public func movement(_ id: UUID) -> Movement? { movements.first { $0.id == id } }

    /// Movements that count, newest first. Pass an account to see only the ones that touch it.
    public func liveMovements(of account: UUID? = nil) -> [Movement] {
        movements.filter { !$0.deleted && (account == nil || $0.effect(on: account!) != nil) }
            .sorted { ($0.occurredAt, $0.createdAt) > ($1.occurredAt, $1.createdAt) }
    }

    public func recordingMovement(_ draft: MovementDraft, id: UUID = UUID(), now: Date = Date(),
                                  zone: String = TimeZone.current.identifier) throws -> DeviceBook {
        guard movements.count < Self.movementLimit else { throw BookRuleError.movementLimit }
        let movement = try validated(draft, id: id, now: now, zone: zone, createdAt: Self.wholeSeconds(now))
        var next = self
        next.movements.append(movement)
        next.revision += 1
        return next
    }

    public func editingMovement(_ id: UUID, with draft: MovementDraft, now: Date = Date(),
                                zone: String = TimeZone.current.identifier) throws -> DeviceBook {
        guard let index = movements.firstIndex(where: { $0.id == id && !$0.deleted }) else { throw BookRuleError.movementNotFound }
        let original = movements[index]
        // Editing keeps the zone the movement was recorded in unless its date moved, so its month does not shift by itself.
        let movement = try validated(draft, id: id, now: now, zone: zone, createdAt: original.createdAt)
        var next = self
        next.movements[index] = movement
        next.revision += 1
        return next
    }

    public func settingMovementDeleted(_ id: UUID, _ deleted: Bool) throws -> DeviceBook {
        guard let index = movements.firstIndex(where: { $0.id == id }) else { throw BookRuleError.movementNotFound }
        guard movements[index].deleted != deleted else { return self }
        var next = self
        next.movements[index].deleted = deleted
        next.revision += 1
        return next
    }

    private func validated(_ draft: MovementDraft, id: UUID, now: Date, zone: String, createdAt: Date) throws -> Movement {
        guard let account = account(draft.accountID) else { throw BookRuleError.accountNotFound }
        guard !account.archived else { throw BookRuleError.accountArchived }
        let typed: Int64
        switch MoneyParser.parseTyped(draft.amountText, digits: account.digits) {
        case .success(let value): typed = value
        case .failure(let error): throw BookRuleError.amount(error)
        }
        guard typed > 0 else { throw BookRuleError.amountNotPositive }
        guard Limits.withinAmount(typed) else { throw BookRuleError.amountTooLarge }
        let occurred = Self.wholeSeconds(draft.occurredAt)
        guard occurred <= now else { throw BookRuleError.futureDate }
        if let start = account.opening?.asOf, occurred < start { throw BookRuleError.beforeTracking }
        var counterpart: UUID?
        if draft.kind == .transfer {
            guard let other = draft.counterpartID.flatMap({ self.account($0) }) else { throw BookRuleError.accountNotFound }
            guard other.id != account.id else { throw BookRuleError.transferSameAccount }
            guard !other.archived else { throw BookRuleError.accountArchived }
            guard other.currency == account.currency else { throw BookRuleError.transferCurrencyMismatch }
            if let start = other.opening?.asOf, occurred < start { throw BookRuleError.beforeTracking }
            counterpart = other.id
        }
        let note = draft.note.trimmingCharacters(in: .whitespacesAndNewlines)
        guard note.unicodeScalars.count <= Limits.note else { throw BookRuleError.noteTooLong }
        return Movement(id: id, kind: draft.kind, accountID: account.id, counterpartID: counterpart, amountMinor: typed,
                        occurredAt: occurred, timeZone: zone, note: note.isEmpty ? nil : note,
                        category: draft.kind == .expense ? draft.category : nil, createdAt: createdAt)
    }
}
