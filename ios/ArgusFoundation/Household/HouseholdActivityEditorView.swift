import SwiftUI
import ArgusSession

struct HouseholdActivityEditorView: View {
    @ObservedObject var model: HouseholdActivityEditor
    @Environment(\.locale) private var locale
    @Environment(\.dismiss) private var dismiss
    @FocusState private var focused: Bool
    var body: some View {
        NavigationStack {
            Form {
                if model.options == nil { ProgressView("accounts.loading") }
                else {
                    Section {
                        if model.correcting == nil {
                            Picker("household.activity", selection: $model.kind) { ForEach(model.kinds, id: \.self) { Text(LocalizedStringKey("loop.kind." + $0.rawValue)).tag($0) } }.accessibilityIdentifier("household.activity.kind")
                        }
                        if model.kind.isPaired {
                            accountPicker("household.sourceAccount", selection: $model.sourceId, types: model.options?.eligibility[model.kind.rawValue])
                            accountPicker("household.destinationAccount", selection: $model.destinationId, types: model.options?.destinationEligibility[model.kind.rawValue])
                        } else { accountPicker("household.account", selection: $model.accountId, types: model.options?.eligibility[model.kind.rawValue]) }
                        TextField("household.amount", text: $model.amount).keyboardType(.decimalPad).focused($focused).accessibilityIdentifier("household.activity.amount")
                        if model.kind == .debtPayment || model.kind == .paymentReversal && model.correcting?.activity.principalMinor != nil {
                            TextField("household.principal", text: $model.principal).keyboardType(.decimalPad).focused($focused)
                            TextField("household.interest", text: $model.interest).keyboardType(.decimalPad).focused($focused)
                            TextField("household.fees", text: $model.fees).keyboardType(.decimalPad).focused($focused)
                        }
                        DatePicker("household.date", selection: $model.date, displayedComponents: [.date])
                        if model.kind == .expense || model.kind == .refund {
                            Picker("household.category", selection: $model.category) {
                                Text("household.choose").tag(String?.none)
                                ForEach(model.options?.categories ?? [], id: \.self) { Text(LocalizedStringKey("loop.category." + $0)).tag(Optional($0)) }
                            }
                        }
                        if model.kind == .income {
                            Picker("household.source", selection: $model.incomeSource) {
                                Text("household.choose").tag(String?.none)
                                ForEach(model.options?.sources ?? [], id: \.self) { Text(LocalizedStringKey("loop.source." + $0)).tag(Optional($0)) }
                            }
                        }
                        if model.kind == .refund {
                            Picker("household.purchase", selection: $model.purchase) {
                                Text("household.unlinked").tag(UUID?.none)
                                ForEach(model.snapshot.activities.filter { $0.activity.kind == .expense && $0.canEdit }) { item in Text(item.activity.note ?? item.activity.amount ?? "").tag(Optional(item.id)) }
                            }
                        }
                        TextField("household.note", text: $model.note).focused($focused).accessibilityIdentifier("household.activity.note")
                        if model.correcting != nil { TextField("household.reason", text: $model.reason).focused($focused).accessibilityIdentifier("household.activity.reason") }
                    }.disabled(model.busy)
                    if let preview = model.preview {
                        Section("household.review") {
                            ForEach(preview.affectedAccounts) { effect in
                                Text(effect.currency + " " + (effect.before.amount ?? "?") + " → " + (effect.after?.amount ?? "?"))
                                ForEach(effect.observations, id: \.observationId) { observation in
                                    Text(observation.asOf)
                                    Button("household.included") { model.answer(effect.accountId, observation.observationId, true) }
                                    Button("household.notIncluded") { model.answer(effect.accountId, observation.observationId, false) }
                                }
                            }
                        }
                    }
                    if let error = model.errorKey { Text(LocalizedStringKey(error)).accessibilityIdentifier("household.activity.error") }
                    if model.preview?.ready == true {
                        Button("household.confirmActivity") { focused = false; Task { await model.confirm() } }.accessibilityIdentifier("household.activity.confirm")
                    } else {
                        Button("household.review") { focused = false; Task { await model.review(locale) } }.accessibilityIdentifier("household.activity.review").disabled(model.amount.isEmpty || model.busy)
                    }
                }
            }
            .navigationTitle(model.correcting == nil ? "household.recordActivity" : "household.correct")
            .scrollDismissesKeyboard(.interactively)
            .toolbar {
                CuadraoCancelToolbar(title: "accounts.cancel") { dismiss() }
            }.task { await model.load() }
        }
    }
    private func accountPicker(_ label: LocalizedStringKey, selection: Binding<UUID?>, types: [String]?) -> some View {
        Picker(label, selection: selection) {
            Text("household.choose").tag(UUID?.none)
            ForEach(model.choices.filter { types?.contains($0.type) == true }) { account in Text((account.nickname ?? account.type) + " · " + account.currency).tag(Optional(account.id)) }
        }
    }
}
