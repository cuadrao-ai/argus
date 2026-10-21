import SwiftUI
import ArgusSession

struct HouseholdContributionEditorView: View {
    @StateObject private var editor: HouseholdContributionEditor
    @ObservedObject private var model: HouseholdPlanModel
    @Environment(\.locale) private var locale
    @Environment(\.dismiss) private var dismiss
    @FocusState private var focused: Bool
    init(model: HouseholdPlanModel, plan: HouseholdPlan, correcting: HouseholdPlanContribution?) {
        self.model = model; _editor = StateObject(wrappedValue: HouseholdContributionEditor(model: model, plan: plan, correcting: correcting))
    }
    var body: some View {
        NavigationStack {
            Form {
                if editor.options == nil {
                    if editor.busy { ProgressView("accounts.loading") }
                    else { Button("accounts.retry") { Task { await editor.load() } } }
                } else {
                    Section {
                        Text("sharedPlan.privateContribution").font(.footnote)
                        if editor.correcting == nil {
                            Picker("sharedPlan.purpose", selection: $editor.purpose) { ForEach(editor.purposes, id: \.self) { Text(LocalizedStringKey("sharedPlan.purpose." + $0.rawValue)).tag($0) } }.accessibilityIdentifier("sharedPlan.contribution.purpose")
                            Picker("loop.activity.kind", selection: $editor.kind) { ForEach(editor.kinds, id: \.self) { Text(LocalizedStringKey("loop.kind." + $0.rawValue)).tag($0) } }.accessibilityIdentifier("sharedPlan.contribution.kind")
                            Picker("sharedPlan.occurrence", selection: $editor.occurrenceId) {
                                Text("sharedPlan.noOccurrence").tag(UUID?.none)
                                ForEach(editor.plan.occurrences) { item in Text(item.date).tag(Optional(item.id)) }
                            }.accessibilityIdentifier("sharedPlan.contribution.occurrence")
                        } else { Text(LocalizedStringKey("loop.kind." + editor.kind.rawValue)) }
                        if editor.kind.isPaired {
                            accountPicker("household.sourceAccount", $editor.sourceId, editor.choices(), "sharedPlan.contribution.source")
                            accountPicker("household.destinationAccount", $editor.destinationId, editor.choices(destination: true), "sharedPlan.contribution.destination")
                        } else { accountPicker("household.account", $editor.accountId, editor.choices(), "sharedPlan.contribution.account") }
                        TextField("household.amount", text: $editor.amount).keyboardType(.decimalPad).focused($focused).accessibilityIdentifier("sharedPlan.contribution.amount")
                        if editor.kind == .debtPayment || editor.original?.principalMinor != nil || editor.sharedOriginal?.principalMinor != nil {
                            TextField("household.principal", text: $editor.principal).keyboardType(.decimalPad).focused($focused).accessibilityIdentifier("sharedPlan.contribution.principal")
                            TextField("household.interest", text: $editor.interest).keyboardType(.decimalPad).focused($focused).accessibilityIdentifier("sharedPlan.contribution.interest")
                            TextField("household.fees", text: $editor.fees).keyboardType(.decimalPad).focused($focused).accessibilityIdentifier("sharedPlan.contribution.fees")
                        }
                        DatePicker("household.date", selection: $editor.date, in: ...Date(), displayedComponents: .date)
                        if editor.kind == .expense || editor.kind == .refund {
                            Picker("household.category", selection: $editor.category) { Text("household.choose").tag(String?.none); ForEach(editor.options?.money.categories ?? [], id: \.self) { Text(LocalizedStringKey("loop.category." + $0)).tag(Optional($0)) } }
                        }
                        if editor.kind == .income {
                            Picker("household.source", selection: $editor.incomeSource) { Text("household.choose").tag(String?.none); ForEach(editor.options?.money.sources ?? [], id: \.self) { Text(LocalizedStringKey("loop.source." + $0)).tag(Optional($0)) } }
                        }
                        TextField("household.note", text: $editor.note).focused($focused).accessibilityIdentifier("sharedPlan.contribution.note")
                        if editor.correcting != nil { TextField("household.reason", text: $editor.reason).focused($focused).accessibilityIdentifier("sharedPlan.contribution.reason") }
                    }.disabled(editor.busy || model.pending)
                    if let preview = editor.preview {
                        Section("household.review") {
                            ForEach(preview.affectedAccounts) { effect in
                                Text(effect.currency + " " + (effect.before.amount ?? "?") + " → " + (effect.after?.amount ?? "?"))
                                ForEach(effect.observations, id: \.observationId) { observation in
                                    Text(observation.asOf).font(.footnote)
                                    HStack {
                                        Button("household.included") { editor.answer(effect.accountId, observation.observationId, true); Task { await editor.review(locale) } }.accessibilityIdentifier("sharedPlan.coverage.yes." + observation.observationId.uuidString)
                                        Button("household.notIncluded") { editor.answer(effect.accountId, observation.observationId, false); Task { await editor.review(locale) } }.accessibilityIdentifier("sharedPlan.coverage.no." + observation.observationId.uuidString)
                                    }.disabled(editor.busy || model.pending)
                                }
                            }
                        }
                    }
                    if model.pending { Text("household.uncertain").font(.footnote) }
                    else if editor.preview?.ready == true, editor.preview?.previewToken != nil {
                        Button("household.confirmActivity") { focused = false; Task { await editor.confirm() } }.accessibilityIdentifier("sharedPlan.contribution.confirm").disabled(editor.busy)
                    } else {
                        Button("household.review") { focused = false; Task { await editor.review(locale) } }.accessibilityIdentifier("sharedPlan.contribution.review").disabled(editor.busy || editor.amount.isEmpty)
                    }
                }
                if let error = editor.errorKey { Text(LocalizedStringKey(error)).accessibilityIdentifier("sharedPlan.contribution.error") }
            }
            .navigationTitle(editor.correcting == nil ? "sharedPlan.record" : "household.correct")
            .scrollDismissesKeyboard(.interactively)
            .toolbar {
                CuadraoCancelToolbar(title: "accounts.cancel", disabled: editor.busy) { dismiss() }
            }.task { await editor.load() }
        }
    }
    private func accountPicker(_ label: LocalizedStringKey, _ value: Binding<UUID?>, _ accounts: [HouseholdContributionEditor.AccountChoice], _ id: String) -> some View {
        Picker(label, selection: value) { Text("household.choose").tag(UUID?.none); ForEach(accounts) { Text($0.nickname ?? NSLocalizedString("accounts.type." + $0.type, comment: "")).tag(Optional($0.id)) } }.accessibilityIdentifier(id)
    }
}
