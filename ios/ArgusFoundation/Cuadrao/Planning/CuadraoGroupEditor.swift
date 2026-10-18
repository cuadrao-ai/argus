import SwiftUI

struct CuadraoGroupEditor: View {
    let store: CuadraoGroupPreview
    let spanish: Bool
    var initial: PlanGroup?
    var onSave: ((UUID) -> Void)?
    @State private var name = ""
    @State private var kind: PlanGroupKind = .trip
    @State private var look: CanvasPlanLook = .coast
    @State private var amount = 0.0
    @State private var amountError = ""
    @State private var currency = "DOP"
    @State private var people = 8
    @State private var discard = false
    @Environment(\.dismiss) private var dismiss
    private var valid: Bool { amountError.isEmpty && !name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && amount.isFinite && (0.01...CanvasMoney.maximumValue).contains(amount) }
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 22) {
                    PlanGroupArtwork(look: look, cover: initial?.cover).frame(height: 150).clipShape(RoundedRectangle(cornerRadius: 28))
                    TextField(CuadraoCopy.text("copy.cuadraoGroupEditor.7de58e5bff", spanish: spanish), text: $name)
                        .font(CuadraoTypography.feature).accessibilityIdentifier("group-name")
                    Picker(CuadraoCopy.text("copy.cuadraoGroupEditor.9a518d0196", spanish: spanish), selection: $kind) {
                        ForEach(PlanGroupKind.allCases, id: \.self) { Text($0.title(spanish)).tag($0) }
                    }.pickerStyle(.segmented).disabled(initial?.expenses.isEmpty == false)
                    VStack(alignment: .leading, spacing: 10) {
                        Text(kind == .trip ? (CuadraoCopy.text("copy.cuadraoGroupEditor.4d6c03b5fd", spanish: spanish)) : (CuadraoCopy.text("copy.cuadraoGroupEditor.83a840d1e5", spanish: spanish))).foregroundStyle(.secondary)
                        PlanAmountInput(value: $amount, currency: $currency, error: $amountError,
                                        title: CuadraoCopy.text("copy.cuadraoGroupEditor.aae0b3301f", spanish: spanish),
                                        identifier: "group-estimate", spanish: spanish,
                                        currencySelectable: initial == nil, showCurrencyLock: initial != nil)
                        Stepper(CuadraoCopy.text("copy.cuadraoGroupEditor.deba0e18f2", spanish: spanish, String(describing: people)), value: $people, in: 1...50)
                        Text(amount > 0 ? (CuadraoCopy.text("copy.cuadraoGroupEditor.7adfa6923a", spanish: spanish, String(describing: PlanFormat.amount(amount / Double(people), currency: currency)))) : (CuadraoCopy.text("copy.cuadraoGroupEditor.0a65e3e3b2", spanish: spanish)))
                            .font(.subheadline).foregroundStyle(look.color)
                    }.padding(20).background(look.color.opacity(0.07), in: RoundedRectangle(cornerRadius: 24))
                    if initial == nil {
                        Text(CuadraoCopy.text("copy.cuadraoGroupEditor.5c8f67cfc6", spanish: spanish)).font(.caption).foregroundStyle(.secondary)
                    }
                    Text(CuadraoCopy.text("copy.cuadraoGroupEditor.0f9ae25a4b", spanish: spanish))
                        .font(.caption).foregroundStyle(.secondary)
                    PlanLookPicker(look: $look, spanish: spanish)
                    PlanPrimaryButton(title: initial == nil ? (CuadraoCopy.text("copy.cuadraoGroupEditor.a54bd5bc95", spanish: spanish)) : (CuadraoCopy.text("copy.cuadraoGroupEditor.f16dc530c4", spanish: spanish))) {
                        var group = initial ?? PlanGroup(name: name, members: [.init(name: CuadraoCopy.text("copy.cuadraoHouseholdSheet.df8578d82b", spanish: spanish), symbol: "sun.max.fill")])
                        group.currency = currency
                        group.name = name.trimmingCharacters(in: .whitespacesAndNewlines); group.kind = kind; group.look = look
                        group.estimatedCents = Int((amount * 100).rounded()); group.expectedPeople = people
                        store.save(group); dismiss(); onSave?(group.id)
                    }.disabled(!valid).opacity(valid ? 1 : 0.4).accessibilityIdentifier("group-save")
                    PlanPreviewFootnote(spanish: spanish)
                }.padding(24)
            }.cuadraoFormKeyboard().background(WelcomePalette.background)
                .navigationTitle(CuadraoCopy.text("copy.cuadraoGroupEditor.1d8148f854", spanish: spanish)).navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    CuadraoCancelToolbar(title: CuadraoCopy.text("copy.connectedCuadraoProfile.62a128b722", spanish: spanish)) { discard = true }
                }
                .confirmationDialog(CuadraoCopy.text("copy.cuadraoGroupEditor.4a48e5135c", spanish: spanish), isPresented: $discard, titleVisibility: .visible) {
                    Button(CuadraoCopy.text("copy.guestClaimModel.adac3a9868", spanish: spanish), role: .destructive) { dismiss() }
                }
        }.onAppear { if let initial { name = initial.name; currency = initial.currency; kind = initial.kind; look = initial.look; amount = Double(initial.estimatedCents) / 100; people = initial.expectedPeople } }
            .interactiveDismissDisabled().presentationDragIndicator(.visible)
    }
}

struct PlanLookPicker: View {
    @Binding var look: CanvasPlanLook
    let spanish: Bool
    var body: some View {
        HStack(spacing: 14) {
            ForEach(CanvasPlanLook.allCases) { choice in
                Button { look = choice } label: {
                    Image(systemName: choice.symbol).font(.title3).foregroundStyle(choice.color)
                        .frame(maxWidth: .infinity, minHeight: 48)
                        .background(choice.color.opacity(look == choice ? 0.18 : 0.04), in: RoundedRectangle(cornerRadius: 16))
                        .overlay { if look == choice { RoundedRectangle(cornerRadius: 16).stroke(choice.color.opacity(0.5), lineWidth: 1) } }
                }.accessibilityLabel(choice.title(spanish)).accessibilityAddTraits(look == choice ? .isSelected : [])
            }
        }.sensoryFeedback(.selection, trigger: look)
    }
}
