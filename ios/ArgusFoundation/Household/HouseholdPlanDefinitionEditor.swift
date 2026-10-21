import SwiftUI
import ArgusSession

struct HouseholdPlanDefinitionEditor: View {
    @ObservedObject var model: HouseholdPlanModel
    var editing: HouseholdPlan?
    var sharing = false
    @Environment(\.locale) private var locale
    @Environment(\.dismiss) private var dismiss
    @FocusState private var focused: Bool
    @State private var options: HouseholdPlanOptions?
    @State private var kind = HouseholdPlanKind.budget
    @State private var existingId: UUID?
    @State private var existingVersion: Int?
    @State private var name = ""
    @State private var amount = ""
    @State private var currency = ""
    @State private var month = String(PlanDate.string(Date()).prefix(7))
    @State private var accountIds: Set<UUID> = []
    @State private var sourceId: UUID?
    @State private var destinationId: UUID?
    @State private var categories: Set<String> = []
    @State private var uncategorized = true
    @State private var cadence = FinancialPlanSchedule.Cadence.monthly
    @State private var startDate = Date()
    @State private var effectiveDate = Date()
    @State private var endDate = Date()
    @State private var hasEnd = false
    @State private var secondDay = "15"
    @State private var targetDate = Date()
    @State private var hasTargetDate = false
    @State private var contribution = ""
    @State private var hasContribution = false
    @State private var selected: Set<UUID> = []
    @State private var editors: Set<UUID> = []
    @State private var responsibilities: [UUID: String] = [:]
    @State private var publishBudgetScope = false
    @State private var error: String?
    @State private var loading = false
    private var accounts: [FinancialAccount] { options?.money.accounts.filter { options?.ownedAccountIds.contains($0.id) == true } ?? [] }
    private var existing: HouseholdPlanOptions.Existing? { options?.existingDefinitions.first { $0.id == existingId } }
    private var usesSchedule: Bool { kind == .bill || kind == .debt || kind == .goal && hasContribution }
    private var earliestEffectiveDate: Date? { editing.flatMap { PlanDate.parse($0.definition.common.earliestEffectiveDate) } }
    private var schedule: FinancialPlanSchedule {
        HouseholdPlanDefinitionEdit.schedule(original: editing?.definition.schedule, cadence: cadence, startDate: PlanDate.string(startDate), endDate: hasEnd ? PlanDate.string(endDate) : nil, secondDay: Int(secondDay) ?? 15)
    }
    var body: some View {
        NavigationStack {
            Form {
                if let options {
                    if sharing {
                        Section("sharedPlan.share") {
                            Picker("sharedPlan.definition", selection: $existingId) {
                                Text("household.choose").tag(UUID?.none)
                                ForEach(options.existingDefinitions) { item in Text(item.name + " · " + NSLocalizedString("sharedPlan.kind." + item.ref.kind.rawValue, comment: "")).tag(Optional(item.id)) }
                            }.accessibilityIdentifier("sharedPlan.existing")
                        }
                    } else {
                        definitionFields(options)
                    }
                    if editing == nil, let scope = model.scope {
                        Section("sharedPlan.responsibilityPeriod") {
                            if selectedKind == .budget {
                                if sharing { Text(month).accessibilityIdentifier("sharedPlan.month") }
                                else { Text(month); Text("sharedPlan.monthResponsibility").font(.footnote) }
                            }
                            else { DatePicker("sharedPlan.agreedDate", selection: $startDate, displayedComponents: .date) }
                        }
                        HouseholdPlanPeopleFields(people: options.people, ownerId: scope.membershipId, selected: $selected, editors: $editors, amounts: $responsibilities, focus: $focused)
                        if selectedKind == .budget {
                            Section { Toggle("sharedPlan.publishBudget", isOn: $publishBudgetScope).accessibilityIdentifier("sharedPlan.publishBudget"); Text("sharedPlan.publishBudgetNotice").font(.footnote) }
                        }
                    }
                    if let error { Text(LocalizedStringKey(error)).accessibilityIdentifier("sharedPlan.form.error") }
                    Button(sharing ? "sharedPlan.confirmShare" : editing == nil ? "sharedPlan.confirmCreate" : "sharedPlan.confirmEdit") { focused = false; Task { await save() } }
                        .disabled(loading || model.pending || model.busy || (sharing && (existing == nil || existingVersion == nil)) || (editing != nil && usesSchedule && earliestEffectiveDate == nil)).accessibilityIdentifier("sharedPlan.confirm")
                } else if loading { ProgressView("accounts.loading") }
                else if let error { Text(LocalizedStringKey(error)); Button("accounts.retry") { Task { await load() } } }
            }
            .navigationTitle(sharing ? "sharedPlan.share" : editing == nil ? "sharedPlan.create" : "sharedPlan.edit")
            .scrollDismissesKeyboard(.interactively)
            .toolbar {
                CuadraoCancelToolbar(title: "accounts.cancel") { dismiss() }
            }
            .task { await load() }
            .onChange(of: existingId) { _, _ in Task { await loadExistingScope() } }
        }
    }
    private var selectedKind: HouseholdPlanKind { sharing ? existing?.ref.kind ?? .budget : kind }
    @ViewBuilder private func definitionFields(_ options: HouseholdPlanOptions) -> some View {
        Section {
            if editing == nil {
                Picker("sharedPlan.kind", selection: $kind) { ForEach(HouseholdPlanKind.allCases, id: \.self) { Text(LocalizedStringKey("sharedPlan.kind." + $0.rawValue)).tag($0) } }.accessibilityIdentifier("sharedPlan.kind")
            }
            TextField("sharedPlan.name", text: $name).focused($focused).accessibilityIdentifier("sharedPlan.name")
            TextField(LocalizedStringKey(kind == .budget ? "sharedPlan.limit" : kind == .goal ? "sharedPlan.target" : "sharedPlan.agreed"), text: $amount).keyboardType(.decimalPad).focused($focused).accessibilityIdentifier("sharedPlan.amount")
            if editing == nil {
                if accounts.isEmpty {
                    TextField("accounts.currency", text: $currency).textInputAutocapitalization(.characters).autocorrectionDisabled().focused($focused).accessibilityIdentifier("sharedPlan.currency")
                    Text("sharedPlan.noAccounts").font(.footnote)
                } else {
                    Picker("accounts.currency", selection: $currency) {
                        Text("household.choose").tag("")
                        ForEach(Array(Set(accounts.map(\.currency))).sorted(), id: \.self) { Text($0).tag($0) }
                    }.accessibilityIdentifier("sharedPlan.currency")
                }
                Text("sharedPlan.privateAccounts").font(.footnote)
                if kind == .budget {
                    ForEach(accounts.filter { $0.currency == currency }) { account in
                        Toggle(account.nickname ?? NSLocalizedString("accounts.type." + account.type, comment: ""), isOn: Binding(get: { accountIds.contains(account.id) }, set: { if $0 { accountIds.insert(account.id) } else { accountIds.remove(account.id) } })).accessibilityIdentifier("sharedPlan.account." + account.id.uuidString)
                    }
                } else {
                    if kind != .goal || hasContribution { accountPicker("sharedPlan.source", selection: $sourceId, types: ["cash", "checking", "savings"], id: "sharedPlan.source") }
                    if kind == .goal { accountPicker("sharedPlan.destination", selection: $destinationId, types: ["cash", "checking", "savings"], id: "sharedPlan.destination") }
                    if kind == .debt { accountPicker("sharedPlan.debtAccount", selection: $destinationId, types: ["credit_card", "other_debt"], id: "sharedPlan.destination") }
                }
            } else { Text(editing?.definition.common.currency ?? "") }
        }
        if kind == .budget {
            Section("sharedPlan.budgetScope") {
                TextField("sharedPlan.month", text: $month).focused($focused).accessibilityIdentifier("sharedPlan.month")
                ForEach(options.money.categories, id: \.self) { category in
                    Toggle(LocalizedStringKey("loop.category." + category), isOn: Binding(get: { categories.contains(category) }, set: { if $0 { categories.insert(category) } else { categories.remove(category) } })).accessibilityIdentifier("sharedPlan.category." + category)
                }
                Toggle("budget.uncategorized", isOn: $uncategorized).accessibilityIdentifier("sharedPlan.uncategorized")
            }
        }
        if kind == .goal {
            Section {
                Toggle("sharedPlan.hasTargetDate", isOn: $hasTargetDate)
                if hasTargetDate { DatePicker("sharedPlan.targetDate", selection: $targetDate, displayedComponents: .date) }
                if editing == nil {
                    Toggle("sharedPlan.hasContribution", isOn: $hasContribution).accessibilityIdentifier("sharedPlan.hasContribution")
                }
                if hasContribution { TextField("sharedPlan.plannedContribution", text: $contribution).keyboardType(.decimalPad).focused($focused).accessibilityIdentifier("sharedPlan.plannedContribution") }
            }
        }
        if usesSchedule {
            Section("sharedPlan.schedule") {
                Picker("sharedPlan.schedule", selection: $cadence) { ForEach(FinancialPlanSchedule.Cadence.allCases, id: \.self) { Text(LocalizedStringKey("plan.repeat." + $0.rawValue)).tag($0) } }.accessibilityIdentifier("sharedPlan.cadence")
                if editing != nil, let minimum = earliestEffectiveDate {
                    DatePicker("plan.effectiveDate", selection: $effectiveDate, in: minimum..., displayedComponents: .date).accessibilityIdentifier("sharedPlan.effectiveDate")
                    DatePicker("sharedPlan.startDate", selection: $startDate, displayedComponents: .date).accessibilityIdentifier("sharedPlan.startDate")
                    Text("plan.cutover.hint").font(.footnote).foregroundStyle(ArgusStyle.secondary)
                } else if editing != nil { Text("sharedPlan.changed") }
                else { DatePicker("sharedPlan.startDate", selection: $startDate, displayedComponents: .date).accessibilityIdentifier("sharedPlan.startDate") }
                Toggle("sharedPlan.hasEndDate", isOn: $hasEnd)
                if hasEnd { DatePicker("sharedPlan.endDate", selection: $endDate, displayedComponents: .date) }
                if cadence == .twiceMonthly { TextField("sharedPlan.secondDay", text: $secondDay).keyboardType(.numberPad).focused($focused) }
            }
        }
    }
    private func accountPicker(_ label: LocalizedStringKey, selection: Binding<UUID?>, types: [String], id: String) -> some View {
        Picker(label, selection: selection) {
            Text("household.choose").tag(UUID?.none)
            ForEach(accounts.filter { $0.currency == currency && types.contains($0.type) }) { account in Text(account.nickname ?? NSLocalizedString("accounts.type." + account.type, comment: "")).tag(Optional(account.id)) }
        }.accessibilityIdentifier(id)
    }
    private func load() async {
        loading = true; defer { loading = false }
        do {
            options = try await model.options(); error = nil
            if let plan = editing {
                kind = plan.ref.kind; name = plan.definition.common.name; currency = plan.definition.common.currency
                amount = HouseholdPlanPresentation.decimal(plan.definition.amountMinor, digits: plan.definition.common.currencyFractionDigits)
                if let s = plan.definition.schedule { cadence = s.cadence; startDate = PlanDate.parse(s.startDate) ?? startDate; endDate = s.endDate.flatMap(PlanDate.parse) ?? endDate; hasEnd = s.endDate != nil; secondDay = s.monthDays.last.map(String.init) ?? "15" }
                if case .budget(_, _, let m, let c, let u, _) = plan.definition { month = m; categories = Set(c); uncategorized = u }
                if case .goal(_, _, let d, let s, let planned) = plan.definition {
                    hasTargetDate = d != nil; targetDate = d.flatMap(PlanDate.parse) ?? targetDate; hasContribution = s != nil
                    contribution = planned.map { HouseholdPlanPresentation.decimal($0, digits: plan.definition.common.currencyFractionDigits) } ?? ""
                }
                if usesSchedule, let minimum = earliestEffectiveDate { effectiveDate = minimum }
            }
        } catch { self.error = HouseholdPlanModel.message(error) }
    }
    private func save() async {
        do {
            let value = try AccountEntry.amount(amount, locale: locale) ?? ""
            if let plan = editing {
                guard let identity = model.identity, model.isCurrent(plan, identity), plan.canEdit else { error = "sharedPlan.changed"; return }
                guard !usesSchedule || earliestEffectiveDate != nil else { error = "sharedPlan.changed"; return }
                let plannedAmount: String?
                if kind == .goal && hasContribution {
                    guard let entered = try AccountEntry.amount(contribution, locale: locale) else { error = "household.reviewError"; return }
                    plannedAmount = entered
                } else { plannedAmount = nil }
                let patch = HouseholdPlanDefinitionEdit.patch(plan: plan, name: name, amount: value, plannedAmount: plannedAmount, targetDate: hasTargetDate ? PlanDate.string(targetDate) : nil, month: month, categories: categories.sorted(), uncategorized: uncategorized, schedule: usesSchedule ? schedule : nil, effectiveDate: PlanDate.string(effectiveDate))
                await model.submit(HouseholdPlanEditCommand(scope: model.scope(plan), definition: patch), action: .edit(plan.ref)); return
            }
            guard let scope = model.scope, let options else { error = "sharedPlan.changed"; return }
            let participants = options.people.filter { selected.contains($0.id) && $0.id != scope.membershipId }.map { HouseholdPlanParticipantWrite(membershipId: $0.id, permission: editors.contains($0.id) ? .edit : .view) }
            let period: HouseholdResponsibilityPeriod = selectedKind == .budget ? .month(month) : .agreedDate(PlanDate.string(startDate))
            let duties = try options.people.filter { selected.contains($0.id) || $0.id == scope.membershipId }.map { HouseholdPlanResponsibilityWrite(membershipId: $0.id, amount: try AccountEntry.amount(responsibilities[$0.id] ?? "", locale: locale), period: period) }
            let people = HouseholdPlanPeopleCommand(kind: selectedKind, scope: sharing ? .init(membershipId: scope.membershipId, authorizationVersion: scope.authorizationVersion, planVersion: existingVersion) : scope, participants: participants, responsibilities: duties, publishBudgetScope: publishBudgetScope)
            if sharing, let existing { await model.submit(people, action: .share(existing.ref)); return }
            switch kind {
            case .budget: await create(FinancialBudgetCommand(name: name, limit: value, currency: currency, month: month, accountIds: accountIds.sorted { $0.uuidString < $1.uuidString }, categoryIds: categories.sorted(), includeUncategorized: uncategorized), people)
            case .bill: await create(FinancialExpectationCommand(kind: .bill, title: name, currency: currency, amount: value, accountId: sourceId, schedule: schedule), people)
            case .goal:
                let planned: FinancialGoalPlan?
                if hasContribution {
                    guard let sourceId else { error = "household.reviewError"; return }
                    planned = FinancialGoalPlan(sourceAccountId: sourceId, amount: try AccountEntry.amount(contribution, locale: locale) ?? "", schedule: schedule)
                } else { planned = nil }
                await create(FinancialGoalCommand(name: name, currency: currency, target: value, targetDate: hasTargetDate ? PlanDate.string(targetDate) : nil, destinationAccountId: destinationId, contributionPlan: planned), people)
            case .debt: await create(FinancialDebtCommand(name: name, debtAccountId: destinationId, sourceAccountId: sourceId, amount: value, schedule: schedule, assumptions: nil, expectedVersion: nil, effectiveDate: nil), people)
            }
        } catch { self.error = "household.reviewError" }
    }
    private func create<Value: Encodable & Sendable>(_ value: Value, _ people: HouseholdPlanPeopleCommand) async {
        await model.submit(HouseholdPlanCreateCommand(people: people, definition: HouseholdPlanDefinitionInput(kind: kind, value: value)), action: .create(kind))
    }
    private func loadExistingScope() async {
        guard sharing, let existing, let identity = model.identity, let scope = model.scope, let controller = model.controller else { return }
        loading = true; existingVersion = nil
        defer { if existingId == existing.id { loading = false } }
        do {
            let date: String?
            let canonicalMonth: String?
            let version: Int
            switch existing.ref.kind {
            case .budget:
                let value = try await controller.financialBudget(existing.id, expectedIdentity: identity)
                canonicalMonth = value.budget.month; date = nil; version = value.budget.version
            case .bill:
                let value = try await controller.financialPlan(expectedIdentity: identity)
                guard let bill = value.expectations.first(where: { $0.id == existing.id && $0.kind == .bill }) else { throw SessionFailure.invalidResponse }
                canonicalMonth = nil; date = bill.schedule.startDate; version = bill.version
            case .goal:
                let value = try await controller.financialGoal(existing.id, expectedIdentity: identity)
                canonicalMonth = nil; date = value.goal.contributionPlan?.schedule.startDate ?? value.goal.targetDate; version = value.goal.version
            case .debt:
                let value = try await controller.financialDebt(existing.id, expectedIdentity: identity)
                canonicalMonth = nil; date = value.debt.schedule.startDate; version = value.debt.version
            }
            guard existingId == existing.id, model.identity?.revision == identity.revision, model.identity?.profile?.id == identity.profile?.id, model.scope?.membershipId == scope.membershipId, model.scope?.authorizationVersion == scope.authorizationVersion else { return }
            if let canonicalMonth { month = canonicalMonth }
            if let date, let parsed = PlanDate.parse(date) { startDate = parsed }
            existingVersion = version; error = nil
        } catch {
            if existingId == existing.id { self.error = HouseholdPlanModel.message(error) }
        }
    }
}

enum HouseholdPlanDefinitionEdit {
    static func schedule(original: FinancialPlanSchedule?, cadence: FinancialPlanSchedule.Cadence, startDate: String, endDate: String?, secondDay: Int) -> FinancialPlanSchedule {
        let day = Int(startDate.suffix(2)) ?? 1
        let sameAnchor = original?.cadence == cadence && original?.startDate == startDate
        let monthDays: [Int]
        if sameAnchor, cadence == .monthly { monthDays = original?.monthDays ?? [] }
        else if sameAnchor, cadence == .twiceMonthly, original?.monthDays.last == secondDay { monthDays = original?.monthDays ?? [] }
        else { monthDays = cadence == .twiceMonthly ? [day, secondDay] : cadence == .monthly ? [day] : [] }
        return .init(cadence: cadence, startDate: startDate, endDate: endDate, monthDays: monthDays)
    }
    static func patch(plan: HouseholdPlan, name: String, amount: String, plannedAmount: String?, targetDate: String?, month: String, categories: [String], uncategorized: Bool, schedule: FinancialPlanSchedule?, effectiveDate: String) -> HouseholdPlanDefinitionPatch {
        let digits = plan.definition.common.currencyFractionDigits
        var patch = HouseholdPlanDefinitionPatch(name: name == plan.definition.common.name ? nil : name, amount: amount == HouseholdPlanPresentation.decimal(plan.definition.amountMinor, digits: digits) ? nil : amount)
        switch plan.definition {
        case .budget(_, _, let originalMonth, let originalCategories, let originalUncategorized, _):
            patch.month = month == originalMonth ? nil : month
            patch.categoryIds = Set(categories) == Set(originalCategories) ? nil : categories
            patch.includeUncategorized = uncategorized == originalUncategorized ? nil : uncategorized
        case .goal(_, _, let originalDate, _, let originalPlanned):
            patch.includesTargetDate = targetDate != originalDate; patch.targetDate = targetDate
            if let plannedAmount, plannedAmount != originalPlanned.map({ HouseholdPlanPresentation.decimal($0, digits: digits) }) { patch.plannedContributionAmount = plannedAmount }
        case .bill, .debt: break
        }
        if schedule != plan.definition.schedule { patch.schedule = schedule }
        if patch.schedule != nil || patch.plannedContributionAmount != nil || plan.ref.kind == .debt && patch.amount != nil { patch.effectiveDate = effectiveDate }
        return patch
    }
}
