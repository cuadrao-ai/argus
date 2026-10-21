import SwiftUI
import ArgusSession

struct FinancialGoalAllocationView: View {
    @ObservedObject var model: FinancialGoalModel
    @ObservedObject var loop: FinancialLoopModel
    let detail: FinancialGoalProgress
    @State private var accountID: UUID?
    @State private var values: [UUID: String] = [:]
    @State private var releasing: Set<UUID> = []
    @State private var inputError = false
    @Environment(\.locale) private var locale
    @Environment(\.dismiss) private var dismiss
    @FocusState private var focused: Bool
    private var goals: [FinancialGoalProgress] { (loop.plan.projection?.goals ?? []).filter { $0.goal.currency == detail.goal.currency } }
    private var pools: [FinancialGoalPool] { (loop.plan.projection?.goalPools ?? []).filter { $0.currency == detail.goal.currency && ($0.state != "ineligible" || $0.assignedMinor != "0") } }
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 22) {
                    Text("goal.allocation.disclosure").foregroundStyle(ArgusStyle.secondary)
                    Picker("loop.activity.account", selection: $accountID) {
                        Text("plan.account.unassigned").tag(nil as UUID?)
                        ForEach(pools) { Text(loop.accountName($0.accountId)).tag(Optional($0.accountId)) }
                    }.accessibilityIdentifier("goal.allocation.account")
                    if let pool = pools.first(where: { $0.accountId == accountID }) {
                        PlanValueRow(title: "goal.available", value: money(pool.availableMinor))
                        PlanValueRow(title: "goal.backing", value: money(pool.backingMinor))
                        PlanValueRow(title: "goal.shortfall", value: money(pool.shortfallMinor))
                        ForEach(goals) { progress in
                            VStack(alignment: .leading, spacing: 10) {
                                Text(verbatim: progress.goal.name).font(ArgusStyle.display(20))
                                if progress.goal.archived { Text("goal.archived").foregroundStyle(ArgusStyle.secondary) }
                                TextField("goal.assigned", text: Binding(get: { values[progress.id] ?? "" }, set: { values[progress.id] = $0 }))
                                    .keyboardType(.decimalPad).focused($focused).padding(14)
                                    .overlay(RoundedRectangle(cornerRadius: 14).stroke(ArgusStyle.line))
                                    .accessibilityIdentifier("goal.allocation.amount." + progress.id.uuidString)
                                ForEach(progress.contributions.filter { $0.counting && $0.destinationAccountId == accountID }) { claim in
                                    Toggle(isOn: Binding(get: { releasing.contains(claim.id) }, set: { on in
                                        if on { releasing.insert(claim.id) } else { releasing.remove(claim.id) }
                                    })) { Text("goal.stopCounting") + Text(verbatim: " · " + money(claim.currentPersonalMinor)) }
                                        .accessibilityIdentifier("goal.allocation.release." + claim.id.uuidString)
                                }
                            }
                        }
                    }
                    if inputError { Text("accounts.error.amount_invalid") }
                    if let error = model.errorKey { Text(LocalizedStringKey(error)).accessibilityIdentifier("goal.error") }
                    if loop.pendingConfirmation != nil { PlanPendingView(loop: loop) }
                    else {
                        Button("goal.saveAllocation") { focused = false; save() }.buttonStyle(PillButtonStyle())
                            .disabled(accountID == nil || model.saving).accessibilityIdentifier("goal.allocation.save")
                    }
                }.padding(24).font(ArgusStyle.body())
            }.background(ArgusStyle.background).scrollDismissesKeyboard(.interactively)
                .navigationTitle("goal.allocate").navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    CuadraoCancelToolbar(title: "accounts.cancel", disabled: model.saving, identifier: "goal.action.cancel") { dismiss() }
                }.interactiveDismissDisabled(model.saving)
                .onAppear { accountID = detail.goal.destinationAccountId ?? pools.first?.accountId; load() }
                .onChange(of: accountID) { _, _ in load() }
        }
    }
    private func load() {
        releasing = []
        values = Dictionary(uniqueKeysWithValues: goals.map { progress in
            let minor = progress.components.first(where: { $0.accountId == accountID })?.assignedMinor ?? "0"
            return (progress.id, AccountPresentation.amount(AccountPresentation.decimal(minor, digits: progress.goal.currencyFractionDigits), locale: locale))
        })
    }
    private func money(_ minor: String?) -> String {
        minor.map { PlanPresentation.money($0, currency: detail.goal.currency, digits: detail.goal.currencyFractionDigits, locale: locale) } ?? NSLocalizedString("accounts.unknown", comment: "")
    }
    private func save() {
        guard let aid = accountID, let pool = pools.first(where: { $0.accountId == aid }) else { return }
        do {
            let changes = try goals.map { progress in
                guard let amount = try AccountEntry.amount(values[progress.id] ?? "", locale: locale) else { throw AccountEntry.Failure.amount }
                return FinancialGoalAllocationCommand.Change(goalId: progress.id, expectedVersion: progress.goal.version, accountId: aid, amount: amount,
                    releaseClaimIds: progress.contributions.filter { releasing.contains($0.id) }.map(\.id))
            }
            inputError = false
            Task { await model.allocate(.init(changes: changes, expectedAccountVersions: [aid.uuidString: pool.accountVersion])) }
        } catch { inputError = true }
    }
}

struct FinancialGoalLinkView: View {
    @ObservedObject var model: FinancialGoalModel
    @ObservedObject var loop: FinancialLoopModel
    @State private var selected: UUID?
    @State private var treatment = "add"
    @State private var occurrenceID: String?
    @Environment(\.dismiss) private var dismiss
    @Environment(\.locale) private var locale
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 22) {
                    Text("goal.link.disclosure").foregroundStyle(ArgusStyle.secondary)
                    ForEach(model.candidates, id: \.activityId) { entry in
                        Button { selected = entry.activityId } label: {
                            HStack {
                                VStack(alignment: .leading, spacing: 6) {
                                    Text(entry.note ?? NSLocalizedString("loop.kind.transfer", comment: ""))
                                    Text(entry.currency + " " + AccountPresentation.amount(entry.amount, locale: locale))
                                    Text(entry.legs.map { loop.accountName($0.accountId) }.joined(separator: " → "))
                                    Text(AccountPresentation.date(entry.occurredAt, zone: entry.timeZone, locale: locale))
                                }
                                Spacer(); if selected == entry.activityId { Image(systemName: "checkmark") }
                            }.padding(.vertical, 14).contentShape(Rectangle())
                        }.buttonStyle(.plain).accessibilityIdentifier("goal.candidate." + entry.activityId.uuidString)
                    }
                    if model.candidates.isEmpty && !model.loading { Text("goal.noCandidates") }
                    Picker("goal.link.treatment", selection: $treatment) {
                        Text("goal.link.add").tag("add"); Text("goal.link.included").tag("included")
                    }.accessibilityIdentifier("goal.link.treatment")
                    Text("goal.included.disclosure").font(ArgusStyle.body(12, relativeTo: .caption)).foregroundStyle(ArgusStyle.secondary)
                    Picker("goal.occurrence", selection: $occurrenceID) {
                        Text("goal.noOccurrence").tag(nil as String?)
                        ForEach((loop.plan.projection?.occurrences ?? []).filter { $0.goalId == model.detail?.id && $0.status == .planned }) { row in
                            Text(PlanPresentation.dateLabel(row.dueDate, locale: locale)).tag(Optional(row.id))
                        }
                    }.accessibilityIdentifier("goal.link.occurrence")
                    if model.loading { ProgressView("goal.loading") }
                    if let error = model.errorKey { Text(LocalizedStringKey(error)).accessibilityIdentifier("goal.error") }
                    if loop.pendingConfirmation != nil { PlanPendingView(loop: loop) }
                    else {
                        Button("goal.link.confirm") {
                            if let entry = model.candidates.first(where: { $0.activityId == selected }) {
                                Task { await model.link(entry, treatment: treatment, occurrenceID: occurrenceID) }
                            }
                        }.buttonStyle(PillButtonStyle()).disabled(selected == nil || model.saving).accessibilityIdentifier("goal.link.confirm")
                    }
                }.padding(24).font(ArgusStyle.body())
            }.background(ArgusStyle.background).navigationTitle("goal.link").navigationBarTitleDisplayMode(.inline)
                .toolbar { CuadraoCancelToolbar(title: "accounts.cancel", disabled: model.saving, identifier: "goal.action.cancel") { dismiss() }}
                .interactiveDismissDisabled(model.saving).onAppear { occurrenceID = model.navigation?.occurrenceID }
        }
    }
}
