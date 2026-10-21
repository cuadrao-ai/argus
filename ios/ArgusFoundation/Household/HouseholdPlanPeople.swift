import SwiftUI
import ArgusSession

struct HouseholdPlanPeopleFields: View {
    let people: [HouseholdPlanPerson]
    let ownerId: UUID
    @Binding var selected: Set<UUID>
    @Binding var editors: Set<UUID>
    @Binding var amounts: [UUID: String]
    let focus: FocusState<Bool>.Binding
    var permissionsEditable = true
    var body: some View {
        Section("household.people") {
            Text("sharedPlan.peopleNotice").font(.footnote)
            ForEach(people) { person in
                if person.id != ownerId {
                    Toggle(person.displayName, isOn: Binding(get: { selected.contains(person.id) }, set: { value in
                        if value { selected.insert(person.id) } else { selected.remove(person.id); editors.remove(person.id) }
                    })).disabled(!permissionsEditable).accessibilityIdentifier("sharedPlan.member." + person.id.uuidString)
                    if selected.contains(person.id) {
                        Toggle("sharedPlan.allowEditing", isOn: Binding(get: { editors.contains(person.id) }, set: { value in
                            if value { editors.insert(person.id) } else { editors.remove(person.id) }
                        })).disabled(!permissionsEditable).accessibilityIdentifier("sharedPlan.permission." + person.id.uuidString)
                    }
                } else { Text(person.displayName + " · " + NSLocalizedString("sharedPlan.owner", comment: "")) }
                if person.id == ownerId || selected.contains(person.id) {
                    TextField("sharedPlan.responsibility", text: Binding(get: { amounts[person.id] ?? "" }, set: { amounts[person.id] = $0 }))
                        .keyboardType(.decimalPad).focused(focus).accessibilityIdentifier("sharedPlan.responsibility." + person.id.uuidString)
                }
            }
            Text("sharedPlan.responsibilityNotice").font(.footnote)
        }
    }
}

struct HouseholdPlanPeopleEditor: View {
    @ObservedObject var model: HouseholdPlanModel
    let plan: HouseholdPlan
    @Environment(\.locale) private var locale
    @Environment(\.dismiss) private var dismiss
    @FocusState private var focused: Bool
    @State private var options: HouseholdPlanOptions?
    @State private var selected: Set<UUID> = []
    @State private var editors: Set<UUID> = []
    @State private var amounts: [UUID: String] = [:]
    @State private var occurrenceId: UUID?
    @State private var date = Date()
    @State private var publishBudgetScope = false
    @State private var error: String?
    @State private var loading = false
    private var period: HouseholdResponsibilityPeriod {
        if case .budget(_, _, let month, _, _, _) = plan.definition { return .month(month) }
        if let occurrenceId { return .occurrence(occurrenceId) }
        return .agreedDate(PlanDate.string(date))
    }
    var body: some View {
        NavigationStack {
            Form {
                if let options {
                    Section("sharedPlan.responsibilityPeriod") {
                        if case .budget(_, _, let month, _, _, _) = plan.definition { Text(month) }
                        else {
                            Picker("sharedPlan.occurrence", selection: $occurrenceId) {
                                Text("sharedPlan.agreedDate").tag(UUID?.none)
                                ForEach(plan.occurrences) { item in Text(item.date).tag(Optional(item.id)) }
                            }.accessibilityIdentifier("sharedPlan.responsibility.occurrence")
                            if occurrenceId == nil { DatePicker("sharedPlan.agreedDate", selection: $date, displayedComponents: .date) }
                        }
                    }
                    HouseholdPlanPeopleFields(people: options.people, ownerId: plan.owner.id, selected: $selected, editors: $editors, amounts: $amounts, focus: $focused, permissionsEditable: plan.canManagePeople)
                    if plan.ref.kind == .budget, plan.canManagePeople {
                        Section { Toggle("sharedPlan.publishBudget", isOn: $publishBudgetScope); Text("sharedPlan.publishBudgetNotice").font(.footnote) }
                    }
                    if let error { Text(LocalizedStringKey(error)).accessibilityIdentifier("sharedPlan.form.error") }
                    Button("sharedPlan.confirmPeople") { focused = false; Task { await save() } }.disabled(loading || model.pending || model.busy).accessibilityIdentifier("sharedPlan.confirm")
                } else {
                    if loading { ProgressView("accounts.loading") }
                    if let error { Text(LocalizedStringKey(error)); Button("accounts.retry") { Task { await load() } } }
                }
            }
            .navigationTitle("household.people")
            .scrollDismissesKeyboard(.interactively)
            .toolbar {
                CuadraoCancelToolbar(title: "accounts.cancel") { dismiss() }
            }
            .task { await load() }
            .onChange(of: occurrenceId) { _, _ in loadAmounts() }
            .onChange(of: date) { _, _ in if occurrenceId == nil { loadAmounts() } }
        }
    }
    private func load() async {
        loading = true; defer { loading = false }
        do {
            options = try await model.options()
            selected = Set(plan.participants.map(\.id)); editors = Set(plan.participants.filter { $0.permission == .edit }.map(\.id))
            occurrenceId = plan.occurrences.first?.id
            if let firstDate = plan.responsibilities.first(where: { $0.agreedDate != nil })?.agreedDate { date = PlanDate.parse(firstDate) ?? date }
            if plan.occurrences.isEmpty { occurrenceId = nil }
            if case .budget(_, _, _, _, _, let published) = plan.definition { publishBudgetScope = published }
            loadAmounts(); error = nil
        } catch { self.error = HouseholdPlanModel.message(error) }
    }
    private func matches(_ item: HouseholdPlanResponsibility) -> Bool {
        switch period {
        case .month(let month): item.period == month
        case .occurrence(let id): item.occurrenceId == id
        case .agreedDate(let value): item.agreedDate == value
        case .schedule(let id): item.scheduleId == id
        }
    }
    private func loadAmounts() {
        amounts = Dictionary(uniqueKeysWithValues: plan.responsibilities.filter(matches).map { ($0.person.id, $0.amountMinor.map { HouseholdPlanPresentation.decimal($0, digits: plan.definition.common.currencyFractionDigits) } ?? "") })
    }
    private func save() async {
        guard let identity = model.identity, model.isCurrent(plan, identity), let options else { error = "sharedPlan.changed"; return }
        do {
            let allowed = selected.union([plan.owner.id])
            var responsibilities = plan.responsibilities.filter { !matches($0) && allowed.contains($0.person.id) }.compactMap { item -> HouseholdPlanResponsibilityWrite? in
                let other: HouseholdResponsibilityPeriod
                if let month = item.period { other = .month(month) }
                else if let id = item.occurrenceId { other = .occurrence(id) }
                else if let id = item.scheduleId { other = .schedule(id) }
                else if let date = item.agreedDate { other = .agreedDate(date) }
                else { return nil }
                return .init(membershipId: item.person.id, amount: item.amountMinor.map { HouseholdPlanPresentation.decimal($0, digits: plan.definition.common.currencyFractionDigits) }, period: other)
            }
            for person in options.people where allowed.contains(person.id) {
                responsibilities.append(.init(membershipId: person.id, amount: try AccountEntry.amount(amounts[person.id] ?? "", locale: locale), period: period))
            }
            if plan.canManagePeople {
                let participants = options.people.filter { selected.contains($0.id) && $0.id != plan.owner.id }.map { HouseholdPlanParticipantWrite(membershipId: $0.id, permission: editors.contains($0.id) ? .edit : .view) }
                await model.submit(HouseholdPlanPeopleCommand(kind: plan.ref.kind, scope: model.scope(plan), participants: participants, responsibilities: responsibilities, publishBudgetScope: publishBudgetScope), action: .people(plan.ref))
            } else {
                await model.submit(HouseholdPlanEditCommand(scope: model.scope(plan), responsibilities: responsibilities), action: .edit(plan.ref))
            }
        } catch { self.error = "household.reviewError" }
    }
}

enum PlanDate {
    static func string(_ date: Date) -> String {
        let f = DateFormatter(); f.locale = Locale(identifier: "en_US_POSIX"); f.timeZone = TimeZone.current; f.dateFormat = "yyyy-MM-dd"; return f.string(from: date)
    }
    static func parse(_ string: String) -> Date? {
        let f = DateFormatter(); f.locale = Locale(identifier: "en_US_POSIX"); f.timeZone = TimeZone.current; f.dateFormat = "yyyy-MM-dd"; return f.date(from: string)
    }
}
