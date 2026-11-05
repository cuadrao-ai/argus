import Foundation

/// The whole on-device book. One value, one JSON document: the store writes and reads exactly this.
public struct DeviceBook: Codable, Equatable, Sendable {
    /// The format this build reads and writes. A newer file opens read-only; an older one is migrated forward.
    public static let currentSchemaVersion = 1

    public var schemaVersion: Int
    /// Bumped by every change. The store drops a save older than the newest it has written.
    public var revision: Int
    public var settings: BookSettings
    /// In display order; archived accounts keep their place.
    public var accounts: [BookAccount]
    /// Every movement ever recorded, deleted ones included so a delete can be undone.
    public var movements: [Movement]
    public var plans: [BookPlan]

    public init(schemaVersion: Int = DeviceBook.currentSchemaVersion, revision: Int = 0, settings: BookSettings = BookSettings(),
                accounts: [BookAccount] = [], movements: [Movement] = [], plans: [BookPlan] = []) {
        self.schemaVersion = schemaVersion
        self.revision = revision
        self.settings = settings
        self.accounts = accounts
        self.movements = movements
        self.plans = plans
    }

    public static func empty() -> DeviceBook { DeviceBook() }

    private enum CodingKeys: String, CodingKey { case schemaVersion, revision, settings, accounts, movements, plans }

    /// Fields added later decode to their defaults, so a book written before they existed still opens.
    public init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        schemaVersion = try values.decode(Int.self, forKey: .schemaVersion)
        revision = try values.decodeIfPresent(Int.self, forKey: .revision) ?? 0
        settings = try values.decodeIfPresent(BookSettings.self, forKey: .settings) ?? BookSettings()
        accounts = try values.decodeIfPresent([BookAccount].self, forKey: .accounts) ?? []
        movements = try values.decodeIfPresent([Movement].self, forKey: .movements) ?? []
        plans = try values.decodeIfPresent([BookPlan].self, forKey: .plans) ?? []
    }
}

public struct BookSettings: Codable, Equatable, Sendable {
    /// The currency new accounts start in and Home totals lead with. Always a code in `CurrencyTable`.
    public var primaryCurrency: String?

    public init(primaryCurrency: String? = nil) {
        self.primaryCurrency = primaryCurrency
    }
}

public enum BookRuleError: Error, Equatable, Sendable {
    case currencyUnsupported
    case nicknameTooLong
    case amount(MoneyError)
    /// Debts and optional assets are typed as a positive amount.
    case negativeAmount
    case amountTooLarge
    case shareInvalid
    case accountLimit
    case accountNotFound
    /// The currency or the type is kept once the account has a recorded balance or movements.
    case currencyLocked
    case kindLocked
    /// The order given was not exactly the active accounts.
    case orderInvalid
    case amountNotPositive
    /// A movement cannot be dated after the moment it is recorded.
    case futureDate
    /// A movement cannot be dated before its account's balance was stated; that balance already includes it.
    case beforeTracking
    case accountArchived
    case transferCurrencyMismatch
    case transferSameAccount
    case movementNotFound
    case movementLimit
    case noteTooLong
    case planNameEmpty
    case planLimit
    case planNotFound
    /// A plan keeps its kind, and only a goal takes contributions.
    case planKindLocked
    case planArchived
    /// A budget's scope named an account that is not one of its currency's accounts.
    case scopeInvalid
}

extension DeviceBook {
    /// The preferred currency, or nil to clear it. A code the server would refuse is refused here too.
    public func settingPrimaryCurrency(_ code: String?) throws -> DeviceBook {
        var next = self
        if let code {
            guard let currency = CurrencyTable.currency(code) else { throw BookRuleError.currencyUnsupported }
            next.settings.primaryCurrency = currency.code
        } else {
            next.settings.primaryCurrency = nil
        }
        next.revision += 1
        return next
    }
}
