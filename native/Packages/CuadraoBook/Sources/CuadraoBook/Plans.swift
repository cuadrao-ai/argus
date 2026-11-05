import Foundation

public enum PlanKind: String, Codable, CaseIterable, Sendable {
    /// Saving toward an amount, with progress from contributions the person records by hand.
    case goal
    /// A monthly spending limit over some or all of the accounts and categories of one currency.
    case budget
}

public enum PlanLook: String, Codable, CaseIterable, Sendable {
    case coast, sunshine, bloom, clay
}

/// Money the person set aside toward a goal by hand. Nothing moves between accounts: the book counts what they state.
public struct Contribution: Codable, Equatable, Identifiable, Sendable {
    public let id: UUID
    public var amountMinor: Int64
    public var occurredAt: Date
    public var timeZone: String
    public var note: String?
    public var deleted: Bool

    public init(id: UUID, amountMinor: Int64, occurredAt: Date, timeZone: String, note: String? = nil, deleted: Bool = false) {
        self.id = id
        self.amountMinor = amountMinor
        self.occurredAt = occurredAt
        self.timeZone = timeZone
        self.note = note
        self.deleted = deleted
    }
}

public struct BookPlan: Codable, Equatable, Identifiable, Sendable {
    public let id: UUID
    public var kind: PlanKind
    public var name: String
    public let currency: String
    public let digits: Int
    /// A goal's target, or a budget's monthly limit, in minor units.
    public var targetMinor: Int64
    /// What a goal plans to set aside each month. Budgets have none.
    public var monthlyMinor: Int64?
    public var look: PlanLook
    /// A budget counts expenses from these accounts only; empty means every account in its currency.
    public var accountScope: [UUID]
    /// A budget counts these categories only; empty means every category.
    public var categoryScope: [ExpenseCategory]
    /// The device zone when the plan was made. A budget's months are read in it, so they never shift with a trip.
    public var timeZone: String
    public var archived: Bool
    public var contributions: [Contribution]
    public let createdAt: Date

    public init(id: UUID, kind: PlanKind, name: String, currency: String, digits: Int, targetMinor: Int64, monthlyMinor: Int64? = nil,
                look: PlanLook = .coast, accountScope: [UUID] = [], categoryScope: [ExpenseCategory] = [], timeZone: String,
                archived: Bool = false, contributions: [Contribution] = [], createdAt: Date) {
        self.id = id
        self.kind = kind
        self.name = name
        self.currency = currency
        self.digits = digits
        self.targetMinor = targetMinor
        self.monthlyMinor = monthlyMinor
        self.look = look
        self.accountScope = accountScope
        self.categoryScope = categoryScope
        self.timeZone = timeZone
        self.archived = archived
        self.contributions = contributions
        self.createdAt = createdAt
    }
}

/// What the plan form collects. Amounts are as typed.
public struct BookPlanDraft: Equatable, Sendable {
    public var kind: PlanKind
    public var name: String
    public var currency: String
    public var targetText: String
    public var monthlyText: String
    public var look: PlanLook
    public var accountScope: [UUID]
    public var categoryScope: [ExpenseCategory]

    public init(kind: PlanKind, name: String, currency: String, targetText: String, monthlyText: String = "", look: PlanLook = .coast,
                accountScope: [UUID] = [], categoryScope: [ExpenseCategory] = []) {
        self.kind = kind
        self.name = name
        self.currency = currency
        self.targetText = targetText
        self.monthlyText = monthlyText
        self.look = look
        self.accountScope = accountScope
        self.categoryScope = categoryScope
    }
}

public struct GoalProgress: Equatable, Sendable {
    public let savedMinor: Int64
    public let targetMinor: Int64
    public var remainingMinor: Int64 { max(0, targetMinor - savedMinor) }
    public var reached: Bool { savedMinor >= targetMinor }
    /// 0...1 for drawing a bar; the amounts above are the truth.
    public var fraction: Decimal {
        guard targetMinor > 0 else { return 0 }
        return min(1, max(0, Decimal(savedMinor) / Decimal(targetMinor)))
    }
}

public struct BudgetStatus: Equatable, Sendable {
    public let limitMinor: Int64
    public let spentMinor: Int64
    /// Negative when the limit is passed.
    public var remainingMinor: Int64 { limitMinor - spentMinor }
    public var isOver: Bool { spentMinor > limitMinor }
    public let month: DateInterval
    /// Days of the month that have started, today included, and the month's length, in the plan's zone.
    public let elapsedDays: Int
    public let totalDays: Int
    public var fraction: Decimal {
        guard limitMinor > 0 else { return 0 }
        return min(1, max(0, Decimal(spentMinor) / Decimal(limitMinor)))
    }
}

extension DeviceBook {
    public static let planLimit = 100
    public static let contributionLimit = 5_000

    public func plan(_ id: UUID) -> BookPlan? { plans.first { $0.id == id } }
    public var activePlans: [BookPlan] { plans.filter { !$0.archived } }
    public var archivedPlans: [BookPlan] { plans.filter(\.archived) }

    public func addingPlan(_ draft: BookPlanDraft, id: UUID = UUID(), now: Date = Date(),
                           zone: String = TimeZone.current.identifier) throws -> DeviceBook {
        guard plans.count < Self.planLimit else { throw BookRuleError.planLimit }
        guard let currency = CurrencyTable.currency(draft.currency) else { throw BookRuleError.currencyUnsupported }
        var plan = BookPlan(id: id, kind: draft.kind, name: "", currency: currency.code, digits: currency.digits, targetMinor: 0,
                            look: draft.look, timeZone: zone, createdAt: Self.wholeSeconds(now))
        try fill(&plan, from: draft)
        var next = self
        next.plans.append(plan)
        next.revision += 1
        return next
    }

    /// Edits everything but the currency, which is fixed when the plan is made. A plan's kind cannot change either.
    public func editingPlan(_ id: UUID, with draft: BookPlanDraft) throws -> DeviceBook {
        guard let index = plans.firstIndex(where: { $0.id == id }) else { throw BookRuleError.planNotFound }
        var plan = plans[index]
        guard draft.kind == plan.kind else { throw BookRuleError.planKindLocked }
        guard CurrencyTable.currency(draft.currency)?.code == plan.currency else { throw BookRuleError.currencyLocked }
        try fill(&plan, from: draft)
        var next = self
        next.plans[index] = plan
        next.revision += 1
        return next
    }

    public func settingPlanArchived(_ id: UUID, _ archived: Bool) throws -> DeviceBook {
        guard let index = plans.firstIndex(where: { $0.id == id }) else { throw BookRuleError.planNotFound }
        guard plans[index].archived != archived else { return self }
        var next = self
        next.plans[index].archived = archived
        next.revision += 1
        return next
    }

    /// Puts the active plans in the given order; archived ones keep their place.
    public func reorderingActivePlans(_ ids: [UUID]) throws -> DeviceBook {
        let active = activePlans
        guard ids.count == active.count, Set(ids) == Set(active.map(\.id)) else { throw BookRuleError.orderInvalid }
        var queue = ids.compactMap { id in active.first { $0.id == id } }[...]
        var next = self
        next.plans = plans.map { plan in
            guard !plan.archived, let replacement = queue.popFirst() else { return plan }
            return replacement
        }
        next.revision += 1
        return next
    }

    /// Records money set aside toward a goal. Not in the future; positive; exact in the plan's digits.
    public func addingContribution(to planID: UUID, amountText: String, occurredAt: Date, note: String = "", id: UUID = UUID(),
                                   now: Date = Date(), zone: String = TimeZone.current.identifier) throws -> DeviceBook {
        guard let index = plans.firstIndex(where: { $0.id == planID }) else { throw BookRuleError.planNotFound }
        let plan = plans[index]
        guard plan.kind == .goal else { throw BookRuleError.planKindLocked }
        guard !plan.archived else { throw BookRuleError.planArchived }
        guard plan.contributions.count < Self.contributionLimit else { throw BookRuleError.movementLimit }
        let minor: Int64
        switch MoneyParser.parseTyped(amountText, digits: plan.digits) {
        case .success(let value): minor = value
        case .failure(let error): throw BookRuleError.amount(error)
        }
        guard minor > 0 else { throw BookRuleError.amountNotPositive }
        guard Limits.withinAmount(minor) else { throw BookRuleError.amountTooLarge }
        let occurred = Self.wholeSeconds(occurredAt)
        guard occurred <= now else { throw BookRuleError.futureDate }
        let trimmed = note.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmed.unicodeScalars.count <= Limits.note else { throw BookRuleError.noteTooLong }
        var next = self
        next.plans[index].contributions.append(Contribution(id: id, amountMinor: minor, occurredAt: occurred, timeZone: zone,
                                                            note: trimmed.isEmpty ? nil : trimmed))
        next.revision += 1
        return next
    }

    public func settingContributionDeleted(_ id: UUID, in planID: UUID, _ deleted: Bool) throws -> DeviceBook {
        guard let planIndex = plans.firstIndex(where: { $0.id == planID }),
              let index = plans[planIndex].contributions.firstIndex(where: { $0.id == id }) else { throw BookRuleError.planNotFound }
        guard plans[planIndex].contributions[index].deleted != deleted else { return self }
        var next = self
        next.plans[planIndex].contributions[index].deleted = deleted
        next.revision += 1
        return next
    }

    // MARK: Derived

    /// Saved so far: the contributions that still count. Nil only if the sum would overflow.
    public func goalProgress(_ id: UUID) -> GoalProgress? {
        guard let plan = plan(id), plan.kind == .goal else { return nil }
        var total: Int64 = 0
        for contribution in plan.contributions where !contribution.deleted {
            let (sum, overflow) = total.addingReportingOverflow(contribution.amountMinor)
            guard !overflow else { return nil }
            total = sum
        }
        return GoalProgress(savedMinor: total, targetMinor: plan.targetMinor)
    }

    /// This month's spending against a budget: the recorded expenses in its scope, month read in the plan's own zone.
    public func budgetStatus(_ id: UUID, now: Date) -> BudgetStatus? {
        guard let plan = plan(id), plan.kind == .budget else { return nil }
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: plan.timeZone) ?? .current
        guard let month = calendar.dateInterval(of: .month, for: now),
              let days = calendar.range(of: .day, in: .month, for: now) else { return nil }
        let accountIDs: Set<UUID> = plan.accountScope.isEmpty
            ? Set(accounts.filter { $0.currency == plan.currency }.map(\.id)) : Set(plan.accountScope)
        let categories = Set(plan.categoryScope)
        var spent: Int64 = 0
        for movement in movements where !movement.deleted && movement.kind == .expense && accountIDs.contains(movement.accountID)
            && month.contains(movement.occurredAt) && movement.occurredAt <= now
            && (categories.isEmpty || categories.contains(movement.category ?? .other)) {
            let (sum, overflow) = spent.addingReportingOverflow(movement.amountMinor)
            guard !overflow else { return nil }
            spent = sum
        }
        return BudgetStatus(limitMinor: plan.targetMinor, spentMinor: spent, month: month,
                            elapsedDays: calendar.component(.day, from: now), totalDays: days.count)
    }

    // MARK: Validation

    private func fill(_ plan: inout BookPlan, from draft: BookPlanDraft) throws {
        let name = draft.name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !name.isEmpty else { throw BookRuleError.planNameEmpty }
        guard name.unicodeScalars.count <= Limits.planName else { throw BookRuleError.nicknameTooLong }
        let target = try Self.positiveAmount(draft.targetText, digits: plan.digits)
        var monthly: Int64?
        if plan.kind == .goal {
            monthly = try Self.positiveAmount(draft.monthlyText, digits: plan.digits)
        }
        var scope: [UUID] = []
        if plan.kind == .budget {
            for id in draft.accountScope where !scope.contains(id) {
                guard let account = account(id), account.currency == plan.currency else { throw BookRuleError.scopeInvalid }
                scope.append(id)
            }
        }
        plan.name = name
        plan.targetMinor = target
        plan.monthlyMinor = monthly
        plan.look = draft.look
        plan.accountScope = scope
        plan.categoryScope = plan.kind == .budget ? ExpenseCategory.allCases.filter { draft.categoryScope.contains($0) } : []
    }

    private static func positiveAmount(_ text: String, digits: Int) throws -> Int64 {
        switch MoneyParser.parseTyped(text, digits: digits) {
        case .success(let value):
            guard value > 0 else { throw BookRuleError.amountNotPositive }
            guard Limits.withinAmount(value) else { throw BookRuleError.amountTooLarge }
            return value
        case .failure(let error): throw BookRuleError.amount(error)
        }
    }
}
