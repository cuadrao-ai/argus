import SwiftUI
import ArgusSession

/// One editor for every supported money activity. The server owns eligibility,
/// reviewed effects, coverage questions and every balance calculation.
@MainActor
final class FinancialActivityEditor: ObservableObject, Identifiable {
    enum Phase { case editing, loading, review, saving, uncertain, conflict, retired, saved }

    let id = UUID()
    let origin: FinancialAccount
    let correcting: FinancialActivityDetail?
    let planOccurrence: FinancialPlanOccurrence?
    let debt: FinancialDebt?
    let debtOccurrenceId: String?
    let returning: FinancialActivityDetail?
    let goal: FinancialGoal?
    let goalOccurrenceId: String?
    /// A category shortcut opens the editor scrolled to the category control.
    let focusCategory: Bool
    @Published private(set) var kind: FinancialActivityKind
    @Published var accountId: UUID? { didSet { changed(accountId != oldValue) } }
    @Published var sourceAccountId: UUID? { didSet { changed(sourceAccountId != oldValue) } }
    @Published var destinationAccountId: UUID? { didSet { changed(destinationAccountId != oldValue); payCardIfChosen() } }
    @Published var amount = "" { didSet { changed(amount != oldValue) } }
    @Published var principal = "" { didSet { changed(principal != oldValue) } }
    @Published var interest = "" { didSet { changed(interest != oldValue) } }
    @Published var fees = "" { didSet { changed(fees != oldValue) } }
    @Published private(set) var debtPreview: FinancialDebtPreview?
    @Published var note = "" { didSet { changed(note != oldValue) } }
    @Published var date = Date() { didSet { changed(date != oldValue) } }
    @Published var categoryId: String? { didSet { changed(categoryId != oldValue) } }
    @Published var sourceId: String? { didSet { changed(sourceId != oldValue) } }
    @Published var purchaseActivityId: UUID? { didSet { changed(purchaseActivityId != oldValue) } }
    @Published var reason = "" { didSet { changed(reason != oldValue) } }
    @Published private(set) var options: FinancialActivityOptions?
    @Published private(set) var purchases: [FinancialActivityDetail] = []
    @Published private(set) var preview: FinancialActivityPreview?
    @Published private(set) var goalPreview: FinancialGoalPreview?
    @Published private(set) var phase = Phase.editing
    @Published private(set) var errorKey: String?

    private var answers: [FinancialAccountCoverage] = []
    private var reviewedCommand: FinancialActivityCommand?
    private var pendingWrite: PendingFinancialConfirmation?
    private var key = UUID()
    private let controller: SessionController
    private let journal: FinancialWriteJournal
    private let identity: SessionSnapshot
    private let timeZone: String
    private let started: (PendingFinancialConfirmation) -> Void
    private let resolved: () -> Void
    private let retired: (SessionSnapshot) -> Void
    private let completed: (FinancialActivityReceipt) async -> Void

    init(origin: FinancialAccount, correcting: FinancialActivityDetail? = nil, planOccurrence: FinancialPlanOccurrence? = nil, goal: FinancialGoal? = nil, goalOccurrenceId: String? = nil, debt: FinancialDebt? = nil, debtOccurrenceId: String? = nil, returning: FinancialActivityDetail? = nil, focusCategory: Bool = false,
         controller: SessionController, journal: FinancialWriteJournal, identity: SessionSnapshot,
         started: @escaping (PendingFinancialConfirmation) -> Void = { _ in },
         resolved: @escaping () -> Void = {},
         retired: @escaping (SessionSnapshot) -> Void = { _ in },
         completed: @escaping (FinancialActivityReceipt) async -> Void) {
        self.debt = debt; self.debtOccurrenceId = debtOccurrenceId; self.returning = returning
        self.goal = goal; self.goalOccurrenceId = goalOccurrenceId; self.focusCategory = focusCategory
        self.origin = origin; self.correcting = correcting; self.planOccurrence = planOccurrence
        self.controller = controller; self.journal = journal; self.identity = identity
        self.started = started; self.resolved = resolved; self.retired = retired; self.completed = completed
        kind = correcting?.kind ?? (origin.type == "credit_card" ? .cardPayment : origin.type == "other_debt" ? .debtPayment : origin.type == "investment" ? .transfer : .expense)
        timeZone = correcting?.timeZone ?? TimeZone.current.identifier
        if let correcting {
            amount = correcting.amount.map { AccountPresentation.amount($0, locale: .current) } ?? ""
            principal = correcting.principalMinor.map { AccountPresentation.amount(AccountPresentation.decimal($0, digits: correcting.currencyFractionDigits), locale: .current) } ?? ""
            interest = correcting.interestMinor.map { AccountPresentation.amount(AccountPresentation.decimal($0, digits: correcting.currencyFractionDigits), locale: .current) } ?? ""
            fees = correcting.feesMinor.map { AccountPresentation.amount(AccountPresentation.decimal($0, digits: correcting.currencyFractionDigits), locale: .current) } ?? ""
            note = correcting.note ?? ""; categoryId = correcting.categoryId
            sourceId = correcting.sourceId; purchaseActivityId = correcting.purchaseActivityId
            date = AccountPresentation.parseDate(correcting.occurredAt) ?? Date()
            accountId = correcting.legs.first(where: { $0.role == "single" })?.accountId
            sourceAccountId = correcting.legs.first(where: { $0.role == "source" })?.accountId
            destinationAccountId = correcting.legs.first(where: { $0.role == "destination" })?.accountId
            answers = correcting.legs.flatMap { leg in
                leg.coverage.map { .init(accountId: leg.accountId, observationId: $0.observationId, included: $0.included) }
            }
        } else {
            if let planOccurrence { kind = planOccurrence.kind == .income ? .income : .expense }
            setAccounts(for: kind)
            if let returning {
                kind = .paymentReversal; accountId = nil
                sourceAccountId = returning.legs.first(where: { $0.role == "source" })?.accountId
                destinationAccountId = returning.legs.first(where: { $0.role == "destination" })?.accountId
                categoryId = returning.categoryId
            }
            if let debt {
                kind = origin.id == debt.debtAccountId && origin.type == "credit_card" ? .cardPayment : .debtPayment
                accountId = nil; sourceAccountId = debt.sourceAccountId; destinationAccountId = debt.debtAccountId; note = debt.name
            }
            if let goal {
                kind = .transfer; sourceAccountId = goal.contributionPlan?.sourceAccountId ?? origin.id
                destinationAccountId = goal.destinationAccountId
                amount = goal.contributionPlan.map { AccountPresentation.amount($0.amount, locale: .current) } ?? ""
                note = goal.name
            }
            if let planOccurrence {
                amount = AccountPresentation.amount(planOccurrence.amount, locale: .current)
                note = planOccurrence.title
            }
        }
    }

    var needsLoanSplit: Bool { kind == .debtPayment || kind == .paymentReversal && (returning?.principalMinor != nil || correcting?.principalMinor != nil) }
    var isCorrection: Bool { correcting != nil }
    var busy: Bool { phase == .loading || phase == .saving }
    /// Entry fields only while editing. Coverage review must not remount amount/date
    /// controls — DatePicker jitter called invalidate() and wiped answers.
    var canEdit: Bool { phase == .editing }
    var canConfirm: Bool { phase == .uncertain || (phase == .review && preview?.ready == true && reviewedCommand != nil) }
    var readyToReview: Bool {
        (correcting?.originalAmountAvailable ?? true) && (returning?.originalAmountAvailable ?? true) &&
        !amount.isEmpty && (!needsLoanSplit || (!principal.isEmpty && !interest.isEmpty && !fees.isEmpty)) && note.unicodeScalars.count <= 200 &&
        (!isCorrection || !reason.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty) &&
        (kind.isPaired ? sourceAccountId != nil && destinationAccountId != nil && sourceAccountId != destinationAccountId : accountId != nil)
    }

    var availableKinds: [FinancialActivityKind] {
        guard let options else { return [] }
        return FinancialActivityKind.allCases.filter { kind in
            if returning != nil { return kind == .paymentReversal }
            if let debt { return kind == (options.accounts.first(where: { $0.id == debt.debtAccountId })?.type == "credit_card" ? .cardPayment : .debtPayment) }
            if kind == .paymentReversal { return false }
            if let planOccurrence { return kind == (planOccurrence.kind == .income ? .income : .expense) }
            return options.eligibility[kind.rawValue]?.contains(origin.type) == true ||
            (kind.isPaired && options.destinationEligibility[kind.rawValue]?.contains(origin.type) == true)
        }
    }

    var singleChoices: [FinancialAccount] { choices(types: options?.eligibility[kind.rawValue]) }
    var sourceChoices: [FinancialAccount] {
        choices(types: options?.eligibility[kind.rawValue]).filter { $0.id != destinationAccountId && (returning == nil || $0.id == sourceAccountId) }
    }
    /// Transfer also lists credit cards: people pay a card from Transfer, and choosing one makes it a card payment.
    var destinationChoices: [FinancialAccount] {
        let cards = kind == .transfer && availableKinds.contains(.cardPayment) ? options?.destinationEligibility[FinancialActivityKind.cardPayment.rawValue] ?? [] : []
        return choices(types: (options?.destinationEligibility[kind.rawValue] ?? []) + cards).filter { $0.id != sourceAccountId && (goal == nil || $0.id == goal?.destinationAccountId) && (debt == nil || $0.id == debt?.debtAccountId) && (returning == nil || $0.id == destinationAccountId) }
    }
    var linkedPurchase: FinancialActivityDetail? { purchases.first { $0.activityId == purchaseActivityId } }
    /// The account the sheet names: the one chosen, the "From" side for paired kinds, else where it opened.
    var headerAccount: FinancialAccount {
        let chosen = kind == .paymentReversal ? destinationAccountId : kind.isPaired ? sourceAccountId : accountId
        return options?.accounts.first { $0.id == chosen } ?? origin
    }

    func load() async {
        do {
            let loaded = try await controller.financialActivityOptions(expectedIdentity: identity)
            guard !(await retireIfNeeded()) else { return }
            options = loaded
            if let debt, !isCorrection { kind = loaded.accounts.first(where: { $0.id == debt.debtAccountId })?.type == "credit_card" ? .cardPayment : .debtPayment }
            if !availableKinds.contains(kind), !isCorrection, let first = availableKinds.first { setKind(first) }
            if kind == .refund { await loadPurchases() }
        } catch {
            if await retireIfNeeded() { return }
            errorKey = Self.message(error)
        }
    }

    func setKind(_ next: FinancialActivityKind) {
        guard !isCorrection, goal == nil, debt == nil, returning == nil, planOccurrence == nil, canEdit, availableKinds.contains(next) || options == nil else { return }
        kind = next; categoryId = nil; sourceId = nil; purchaseActivityId = nil
        answers = []; invalidate(); setAccounts(for: next)
        if next == .refund { Task { await loadPurchases() } }
    }

    /// A credit card chosen as a Transfer's "To" turns it into a card payment, keeping amount, date, note and "From".
    private func payCardIfChosen() {
        guard kind == .transfer, let card = destinationAccountId, let options,
              let type = options.accounts.first(where: { $0.id == card })?.type,
              options.destinationEligibility[kind.rawValue]?.contains(type) != true,
              options.destinationEligibility[FinancialActivityKind.cardPayment.rawValue]?.contains(type) == true else { return }
        let source = sourceAccountId
        setKind(.cardPayment)
        guard kind == .cardPayment else { return }
        sourceAccountId = source; destinationAccountId = card
    }

    private func setAccounts(for kind: FinancialActivityKind) {
        if kind.isPaired {
            accountId = nil
            if (kind == .cardPayment && origin.type == "credit_card") || (kind == .debtPayment && origin.type == "other_debt") {
                sourceAccountId = nil; destinationAccountId = origin.id
            } else {
                sourceAccountId = origin.id; destinationAccountId = nil
            }
        } else {
            sourceAccountId = nil; destinationAccountId = nil; accountId = origin.id
        }
    }

    private func choices(types: [String]?) -> [FinancialAccount] {
        guard let options, let types else { return [] }
        return options.accounts.filter { (planOccurrence == nil || $0.id == planOccurrence?.accountId) && !$0.archived && $0.currency == origin.currency && types.contains($0.type) && (goal == nil || ["cash", "checking", "savings"].contains($0.type)) }
    }

    private func loadPurchases() async {
        do {
            let loaded = try await controller.financialPurchases(currency: origin.currency, expectedIdentity: identity).items
            guard !(await retireIfNeeded()) else { return }
            purchases = loaded
        }
        catch { if !(await retireIfNeeded()) { errorKey = Self.message(error) } }
    }

    private func changed(_ different: Bool) {
        if different { invalidate() }
    }
    private func invalidate() {
        guard canEdit, !busy else { return }
        answers = []; preview = nil; reviewedCommand = nil
    }

    func edit() {
        guard phase == .review else { return }
        phase = .editing; preview = nil; reviewedCommand = nil
    }

    func answer(accountId: UUID, observationId: UUID, included: Bool) {
        guard !busy, phase != .uncertain else { return }
        answers.removeAll { $0.accountId == accountId && $0.observationId == observationId }
        answers.append(.init(accountId: accountId, observationId: observationId, included: included))
        // Stay in review while coverage is answered. Flipping to editing remounts
        // entry controls; DatePicker/field didSet then invalidate() and wipe answers.
        preview = nil
        reviewedCommand = nil
    }

    func answerAndReview(accountId: UUID, observationId: UUID, included: Bool, locale: Locale) async {
        guard phase != .uncertain else { return }
        answers.removeAll { $0.accountId == accountId && $0.observationId == observationId }
        answers.append(.init(accountId: accountId, observationId: observationId, included: included))
        // Wait out an in-flight review so a second observation answer is not dropped
        // by guard !busy, then send every answer collected so far.
        while busy {
            try? await Task.sleep(nanoseconds: 50_000_000)
        }
        guard phase != .uncertain else { return }
        preview = nil
        reviewedCommand = nil
        await review(locale: locale)
    }

    /// A movement timed after a balance was recorded cannot be part of that balance, so its question is answered
    /// "No, apply it" for the person. Only a movement at or before a recorded balance is still asked.
    static func answersAfterChecks(_ preview: FinancialActivityPreview, movement: Date,
                                   answered: [FinancialAccountCoverage]) -> [FinancialAccountCoverage] {
        preview.affectedAccounts.flatMap { affected in
            affected.observations.compactMap { observation -> FinancialAccountCoverage? in
                guard observation.included == nil,
                      !answered.contains(where: { $0.accountId == affected.accountId && $0.observationId == observation.observationId }),
                      let recorded = AccountPresentation.parseDate(observation.asOf), movement > recorded else { return nil }
                return .init(accountId: affected.accountId, observationId: observation.observationId, included: false)
            }
        }
    }

    func review(locale: Locale) async {
        guard !busy, phase != .uncertain else { return }
        phase = .loading; errorKey = nil
        do {
            guard readyToReview, let exact = try AccountEntry.amount(amount, locale: locale) else { throw AccountEntry.Failure.amount }
            let formatter = ISO8601DateFormatter()
            formatter.timeZone = TimeZone(identifier: timeZone)
            var ids = [accountId, sourceAccountId, destinationAccountId].compactMap { $0 }
            ids += correcting?.legs.map(\.accountId) ?? []
            ids += linkedPurchase?.legs.map(\.accountId) ?? []
            let versions = ids.reduce(into: [String: Int]()) { values, id in
                if let version = options?.accounts.first(where: { $0.id == id })?.version {
                    values[id.uuidString] = version
                }
            }
            let command = FinancialActivityCommand(kind: kind, accountId: kind.isPaired ? nil : accountId,
                sourceAccountId: kind.isPaired ? sourceAccountId : nil,
                destinationAccountId: kind.isPaired ? destinationAccountId : nil,
                amount: exact, occurredAt: formatter.string(from: date), timeZone: timeZone,
                note: note.isEmpty ? nil : note,
                categoryId: kind == .debtPayment || kind == .paymentReversal || kind == .expense || (kind == .refund && purchaseActivityId == nil) ? categoryId : nil,
                sourceId: kind == .income ? sourceId : nil,
                purchaseActivityId: kind == .refund ? purchaseActivityId : nil,
                expectedRevision: correcting?.revision, reason: isCorrection ? reason : nil,
                expectedVersions: versions, coverage: answers,
                principal: needsLoanSplit ? try AccountEntry.amount(principal, locale: locale) : nil,
                interest: needsLoanSplit ? try AccountEntry.amount(interest, locale: locale) : nil,
                fees: needsLoanSplit ? try AccountEntry.amount(fees, locale: locale) : nil,
                reversalOfActivityId: returning?.activityId ?? correcting?.reversalOfActivityId)
            let next: FinancialActivityPreview
            if let debt {
                let result = try await controller.financialDebtPreview(debt.id, command: .init(expectedVersion: debt.version, activity: command, occurrenceId: debtOccurrenceId), expectedIdentity: identity)
                guard !(await retireIfNeeded()) else { return }
                debtPreview = result; next = result.money
            } else if let goal {
                let result = try await controller.financialGoalPreview(goal.id, command: .init(expectedVersion: goal.version, activity: command, occurrenceId: goalOccurrenceId), expectedIdentity: identity)
                guard !(await retireIfNeeded()) else { return }
                goalPreview = result; next = result.money
            } else if let occurrence = planOccurrence {
                next = try await controller.financialPlanPreview(occurrenceId: occurrence.id,
                    command: .init(expectedVersion: occurrence.expectationVersion, activity: command), expectedIdentity: identity).money
            } else {
                next = try await controller.financialActivityPreview(command, activityId: correcting?.activityId, expectedIdentity: identity)
            }
            guard !(await retireIfNeeded()) else { return }
            let automatic = Self.answersAfterChecks(next, movement: date, answered: answers)
            if !automatic.isEmpty {
                answers += automatic
                phase = .editing
                return await review(locale: locale)
            }
            preview = next
            if next.ready, var reviewed = next.reviewedRequest, let token = next.previewToken {
                reviewed.previewToken = token
                reviewedCommand = reviewed
            } else { reviewedCommand = nil }
            phase = .review
        } catch {
            if await retireIfNeeded() { return }
            errorKey = Self.message(error)
            phase = Self.isConflict(error) ? .conflict : .editing
        }
    }

    func confirm() async {
        guard canConfirm else { return }
        if await retireIfNeeded() { return }
        phase = .saving; errorKey = nil
        do {
            let write: PendingFinancialConfirmation
            if let pendingWrite { write = pendingWrite }
            else {
                guard let reviewedCommand, let owner = identity.profile.flatMap({ UUID(uuidString: $0.id) }) else {
                    throw SessionFailure.invalidResponse
                }
                let encoder = JSONEncoder(); encoder.outputFormatting = .sortedKeys
                if let debt {
                    let operation = FinancialPlanOperation.recordDebt(id: debt.id, version: debt.version)
                    write = .init(ownerId: owner, originAccountId: origin.id, route: "financial-plan", path: operation.path, method: operation.method, body: try encoder.encode(FinancialDebtRecordCommand(expectedVersion: debt.version, activity: reviewedCommand, occurrenceId: debtOccurrenceId)), key: key, planOperation: operation)
                } else if let goal {
                    let operation = FinancialPlanOperation.recordGoal(id: goal.id, version: goal.version)
                    write = .init(ownerId: owner, originAccountId: origin.id, route: "financial-plan", path: operation.path, method: operation.method, body: try encoder.encode(FinancialGoalRecordCommand(expectedVersion: goal.version, activity: reviewedCommand, occurrenceId: goalOccurrenceId)), key: key, planOperation: operation)
                } else if let occurrence = planOccurrence {
                    let operation = FinancialPlanOperation.fulfill(occurrenceId: occurrence.id, version: occurrence.expectationVersion)
                    write = .init(ownerId: owner, originAccountId: origin.id, route: "financial-plan", path: operation.path,
                        method: operation.method, body: try encoder.encode(FinancialPlanFulfillmentCommand(
                            expectedVersion: occurrence.expectationVersion, activity: reviewedCommand)), key: key, planOperation: operation)
                } else {
                    write = .init(ownerId: owner, originAccountId: origin.id, route: "financial-activities",
                        path: correcting.map { "/" + $0.activityId.uuidString } ?? "", method: correcting == nil ? "POST" : "PATCH",
                        body: try encoder.encode(reviewedCommand), key: key)
                }
                try journal.begin(write, for: identity)
                pendingWrite = write
                started(write)
            }
            let receipt = try await write.planOperation == nil
                ? controller.sendFinancialConfirmation(write, expectedIdentity: identity)
                : controller.sendPlanFulfillment(write, expectedIdentity: identity)
            guard !(await retireIfNeeded()) else { return }
            try journal.clear(write, for: identity)
            pendingWrite = nil
            resolved()
            phase = .saved
            await completed(receipt)
        } catch {
            if await retireIfNeeded() { return }
            errorKey = Self.message(error)
            if Self.isDefinitive(error) {
                if let pendingWrite {
                    do { try journal.clear(pendingWrite, for: identity); self.pendingWrite = nil }
                    catch { phase = .uncertain; errorKey = Self.message(error); return }
                }
                resolved()
                key = UUID(); reviewedCommand = nil; preview = nil
                phase = Self.isConflict(error) ? .conflict : .editing
            } else { phase = .uncertain }
        }
    }

    private func retireIfNeeded() async -> Bool {
        let current = await controller.snapshot()
        guard current.phase != .authenticated || current.revision != identity.revision || current.profile?.id != identity.profile?.id else { return false }
        phase = .retired; retired(current); return true
    }

    private static func isConflict(_ error: Error) -> Bool {
        if case SessionFailure.rejected(let status, _) = error { return status == 409 }
        return error as? FinancialWriteJournalError == .pendingConfirmation
    }
    private static func isDefinitive(_ error: Error) -> Bool {
        if case SessionFailure.rejected(let status, _) = error { return (400..<500).contains(status) && status != 408 }
        return error as? FinancialWriteJournalError == .pendingConfirmation
    }
    static func message(_ error: Error) -> String {
        if error is AccountEntry.Failure { return "accounts.error.amount_invalid" }
        if let journal = error as? FinancialWriteJournalError {
            return journal == .pendingConfirmation ? "loop.pending.existing" : "auth.error.storage"
        }
        guard case SessionFailure.rejected(let status, let code) = error, status < 500 else { return "loop.error.connection" }
        guard let code else { return "loop.error.validation" }
        switch code {
        case "debt_plan_exists": return "debt.error.exists"
        case "debt_setup_invalid", "debt_payment_mismatch": return "debt.error.setup"
        case "payment_split_required", "payment_split_invalid": return "debt.error.split"
        case "payment_return_limit": return "debt.error.returnLimit"
        case "payment_reference_invalid", "payment_reference_immutable", "payment_return_mismatch", "payment_return_category", "linked_payment_return", "return_before_payment": return "debt.error.return"
        case "goal_backing_shortfall": return "goal.error.shortfall"
        case "goal_backing_unknown", "goal_backing_ineligible": return "goal.error.backing"
        case "goal_setup_required", "goal_setup_invalid", "goal_contribution_mismatch": return "goal.error.setup"
        case "goal_release_required", "goal_included_exceeds_allocation": return "goal.error.allocation"
        case "goal_allocation_negative", "goal_allocation_duplicate": return "goal.error.amount"
        case "budget_scope_conflict": return "budget.error.duplicate"
        case "budget_category_required", "budget_scope_duplicate", "budget_limit_required": return "budget.error.scope"
        case "plan_cutover_unsafe": return "plan.error.cutover"
        case "occurrence_already_linked", "activity_already_linked": return "plan.error.stale"
        case "fulfillment_mismatch": return "plan.error.account"
        case "accounts_invalid": return "loop.error.accounts_invalid"
        case "purchase_invalid": return "loop.error.purchase_not_found"
        case "refund_limit": return "loop.error.refund_exceeds_purchase"
        case "linked_refund_category", "linked_refund_currency": return "loop.error.purchase_has_refunds"
        case "refund_category_conflict": return "loop.error.refund_category_conflict"
        case "coverage_invalid", "coverage_duplicate", "balance_coverage_required", "preview_required": return "loop.error.coverage_conflict"
        case "amount_positive_required": return "loop.error.amount_invalid"
        case "kind_immutable": return "loop.error.kind_immutable"
        case "field_not_applicable": return "loop.error.field_not_applicable"
        case "category_unknown": return "loop.error.category_unknown"
        case "source_unknown": return "loop.error.source_unknown"
        case "stale_version", "stale_activity", "amount_precision", "amount_invalid", "amount_out_of_range",
             "date_in_future", "reason_required", "reason_invalid", "account_ineligible", "currency_mismatch",
             "refund_before_purchase": return "loop.error." + code
        default: break
        }
        return "loop.error.validation"
    }
}
