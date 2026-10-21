import SwiftUI

struct CuadraoPlanEditor<Details: View, Footer: View>: View {
    let host: CuadraoPlanEditorHost
    let initial: CanvasPlan
    let spanish: Bool
    let details: (Binding<CanvasPlan>) -> Details
    let footer: () -> Footer
    @State private var draft: CanvasPlan
    @State private var amountErrors: [String: String] = [:]
    @State private var showDetails = false
    @State private var discard = false
    @FocusState private var nameFocused: Bool
    @FocusState private var rateFocused: Bool
    @State private var rateText = ""
    /// Only a visible rate field can hold the save back; switching away from Deuda clears it.
    private var rateProblem: PercentInput.Problem? {
        PlanRateCheck.blocking(kind: draft.kind.rawValue, showsRate: host.showsRate, text: rateText)
    }
    @Environment(\.dismiss) private var dismiss
    private var editing: Bool { host.editing }
    private var ids: CuadraoPlanEditorIdentifiers { host.identifiers }
    private var currencyLocked: Bool { editing || host.currencyLocked }
    private var showsStartingPoint: Bool { host.showsRecorded || (draft.kind == .debt && host.showsRate) }
    private var valid: Bool {
        amountErrors.allSatisfy { id, error in error.isEmpty || (draft.kind == .budget && id == ids.monthly) || (!host.showsTarget && id == ids.target) }
        && !draft.name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        && (!host.showsTarget || (draft.target.isFinite && (0.01...CanvasMoney.maximumValue).contains(draft.target)))
        && draft.recorded.isFinite && (0...CanvasMoney.maximumValue).contains(draft.recorded)
        && (draft.kind == .budget || (draft.monthly.isFinite && ((host.monthlyRequired ? 0.01 : 0)...CanvasMoney.maximumValue).contains(draft.monthly)))
        && draft.annualRate.isFinite && (0...100).contains(draft.annualRate) && rateProblem == nil
        && (draft.kind != .debt || !host.showsTarget || draft.recorded <= draft.target)
        && host.spaces.contains { $0.id == draft.spaceID }
        && host.canSave(draft)
    }
    init(host: CuadraoPlanEditorHost, initial: CanvasPlan, spanish: Bool,
         @ViewBuilder details: @escaping (Binding<CanvasPlan>) -> Details, @ViewBuilder footer: @escaping () -> Footer) {
        self.host = host; self.initial = initial; self.spanish = spanish; self.details = details; self.footer = footer
        _draft = State(initialValue: initial)
    }
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    if !editing && !host.kindLocked { kindPicker }
                    HStack(spacing: 18) {
                        PlanLandscape(look: draft.look).frame(width: 64, height: 70)
                        VStack(alignment: .leading, spacing: 8) {
                            Text(CuadraoCopy.text("copy.cuadraoPlanEditor.b6e583497b", spanish: spanish)).font(CuadraoTypography.section)
                            TextField(CuadraoCopy.text("copy.cuadraoPlanEditor.686ef0b19c", spanish: spanish), text: $draft.name)
                                .font(.body).focused($nameFocused).submitLabel(.done).onSubmit { nameFocused = false }
                                .accessibilityIdentifier(ids.name)
                        }
                    }
                    VStack(spacing: 0) {
                        if host.showsTarget {
                            amountRow(draft.kind.amountTitle(spanish), value: $draft.target, id: ids.target, primary: true)
                            if draft.kind != .budget {
                                Divider().padding(.horizontal, 18)
                                amountRow(monthlyTitle, value: $draft.monthly, id: ids.monthly)
                            }
                        } else {
                            amountRow(monthlyTitle, value: $draft.monthly, id: ids.monthly, primary: true)
                        }
                    }.background(WelcomePalette.surface, in: RoundedRectangle(cornerRadius: 20))
                    details($draft)
                    HStack {
                        CuadraoChoiceMenu(title: CuadraoCopy.text("copy.cuadraoPlanEditor.35e8322d8a", spanish: spanish), selection: $draft.spaceID,
                            values: host.spaces.map(\.id),
                            valueTitle: { id in host.spaces.first { $0.id == id }?.title ?? (CuadraoCopy.text("copy.cuadraoPlanEditor.577a4529ed", spanish: spanish)) })
                            .accessibilityIdentifier("plan-edit-space")
                        Spacer()
                    }
                    if !editing {
                        Text(CuadraoCopy.text("copy.cuadraoGroupEditor.5c8f67cfc6", spanish: spanish)).font(.caption).foregroundStyle(.secondary)
                    }
                    if draft.spaceID == "household" {
                        Text(CuadraoCopy.text("copy.cuadraoPlanEditor.bf6659c2bb", spanish: spanish))
                            .font(.caption).foregroundStyle(.secondary)
                    }
                    if host.showsLook {
                        DisclosureGroup(CuadraoCopy.text("copy.cuadraoPlanEditor.b549852830", spanish: spanish)) {
                            PlanLookPicker(look: $draft.look, spanish: spanish).padding(.top, 12)
                        }.font(.subheadline)
                    }
                    if showsStartingPoint {
                        DisclosureGroup(isExpanded: $showDetails) {
                            VStack(spacing: 12) {
                                if host.showsRecorded {
                                    amountRow(draft.kind.recordedTitle(spanish), value: $draft.recorded, id: "plan-recorded")
                                }
                                if draft.kind == .debt && host.showsRate {
                                    PercentField(title: CuadraoCopy.text("copy.cuadraoPlanDetail.71b1540ce2", spanish: spanish), text: $rateText, bounds: .interest,
                                                 spanish: spanish, identifier: ids.rate)
                                        .focused($rateFocused).padding(18)
                                        .onChange(of: rateText) { _, text in
                                            if case .success(let value) = PercentInput.parse(text, .interest) {
                                                draft.annualRate = NSDecimalNumber(decimal: value ?? 0).doubleValue
                                            }
                                        }
                                    .onAppear { if draft.annualRate != 0 && rateText.isEmpty { rateText = draft.annualRate.formatted(.number.grouping(.never)) } }
                                    Text(CuadraoCopy.text("copy.cuadraoPlanEditor.bd7e42d542", spanish: spanish))
                                        .font(.caption).foregroundStyle(.secondary)
                                }
                            }.padding(.top, 12)
                        } label: { Text(CuadraoCopy.text("copy.cuadraoPlanEditor.8b8cad6032", spanish: spanish)).font(.subheadline.weight(.medium)) }
                    }
                    if draft.kind == .debt && host.showsRate && !showDetails {
                        Text(CuadraoCopy.text("copy.cuadraoPlanEditor.fc6273400c", spanish: spanish, String(describing: draft.annualRate.formatted())))
                            .font(.caption).foregroundStyle(.secondary)
                    }
                    if draft.kind != .budget && host.showsTarget && host.showsRecorded {
                        let months = draft.months(at: draft.monthly)
                        VStack(alignment: .leading, spacing: 5) {
                            Text(months.map { $0 == 0 ? (CuadraoCopy.text("copy.cuadraoPlanEditor.3fd01b458f", spanish: spanish)) : PlanFormat.month(after: $0, spanish: spanish) }
                                 ?? (CuadraoCopy.text("copy.cuadraoPlanEditor.4f1aa8639a", spanish: spanish)))
                                .font(CuadraoTypography.section).foregroundStyle(WelcomePalette.pine)
                            Text(CuadraoCopy.text("copy.cuadraoPlanEditor.87e73474e8", spanish: spanish))
                                .font(.caption).foregroundStyle(.secondary)
                        }
                    }
                    if !valid {
                        Text(PlanRateCheck.hint(rateProblem, spanish: spanish)
                             ?? host.missing(draft) ?? (CuadraoCopy.text("copy.cuadraoPlanEditor.4e0d78bbf7", spanish: spanish)))
                            .font(.caption).foregroundStyle(.secondary).accessibilityIdentifier("plan.missing")
                    }
                    footer()
                }.padding(24)
            }.safeAreaInset(edge: .bottom) {
                VStack(spacing: 12) {
                    PlanPrimaryButton(title: editing ? (CuadraoCopy.text("copy.cuadraoGroupEditor.f16dc530c4", spanish: spanish)) : (CuadraoCopy.text("copy.cuadraoPlanCanvas.2131013203", spanish: spanish))) {
                        draft.name = draft.name.trimmingCharacters(in: .whitespacesAndNewlines)
                        if draft.kind == .budget { draft.monthly = draft.target }
                        host.save(draft)
                        if host.dismissesOnSave { dismiss() }
                    }.disabled(!valid || host.saving).opacity(valid && !host.saving ? 1 : 0.45).accessibilityIdentifier(ids.save)
                }.padding(.horizontal, 24).padding(.vertical, 12).background(.regularMaterial)
            }.cuadraoFormKeyboard().background(WelcomePalette.background)
                .navigationTitle(editing ? (CuadraoCopy.text("copy.cuadraoPlanDetail.507c662ea3", spanish: spanish)) : (CuadraoCopy.text("copy.cuadraoPlanEditor.3fe8b9ec92", spanish: spanish)))
                .navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    CuadraoCancelToolbar(title: CuadraoCopy.text("copy.connectedCuadraoProfile.62a128b722", spanish: spanish), disabled: host.saving) {
                        if draft != initial { discard = true } else { dismiss() }
                    }
                }
                .confirmationDialog(CuadraoCopy.text("copy.cuadraoGroupEditor.4a48e5135c", spanish: spanish), isPresented: $discard, titleVisibility: .visible) {
                    Button(CuadraoCopy.text("copy.guestClaimModel.adac3a9868", spanish: spanish), role: .destructive) { dismiss() }
                }
        }.sensoryFeedback(.selection, trigger: draft.look)
            .presentationDragIndicator(.visible).interactiveDismissDisabled(draft != initial || host.saving)
    }
    private var monthlyTitle: String { host.monthlyTitle ?? (CuadraoCopy.text("copy.cuadraoPlanEditor.90ae4ff82c", spanish: spanish)) }
    private var kindPicker: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(CuadraoCopy.text("copy.cuadraoPlanComposition.3dc6d1d16a", spanish: spanish)).font(CuadraoTypography.section)
            ViewThatFits(in: .horizontal) {
                HStack(spacing: 8) { kindButtons }
                VStack(alignment: .leading, spacing: 8) { kindButtons }
            }
        }
    }
    private var kindButtons: some View {
        ForEach(host.allowedKinds) { kind in
            Button { draft.kind = kind } label: {
                Text(kind == .goal ? (CuadraoCopy.text("copy.cuadraoVoiceProposalCanvas.a666a311f9", spanish: spanish)) : kind == .budget ? (CuadraoCopy.text("copy.cuadraoPlanEditor.7736181f54", spanish: spanish)) : (CuadraoCopy.text("copy.cuadraoPlanEditor.d7c2a3812a", spanish: spanish))).font(.subheadline)
                    .padding(.horizontal, 14).frame(minHeight: 44)
                    .foregroundStyle(draft.kind == kind ? WelcomePalette.onAccent : WelcomePalette.ink)
                    .background(draft.kind == kind ? WelcomePalette.pine : WelcomePalette.surface, in: Capsule())
            }.accessibilityIdentifier(ids.kind(kind)).accessibilityAddTraits(draft.kind == kind ? .isSelected : [])
        }
    }
    private func amountRow(_ title: String, value: Binding<Double>, id: String, primary: Bool = false) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(title).font(.caption).foregroundStyle(.secondary)
            PlanAmountInput(value: value, currency: $draft.currency, error: $amountErrors.message(for: id), title: title,
                            identifier: id, spanish: spanish, currencySelectable: primary && !currencyLocked,
                            showCurrencyLock: primary && currencyLocked, prominent: primary, currencyIdentifier: ids.currency)
        }.padding(18)
    }
}

extension CuadraoPlanEditor where Details == EmptyView, Footer == PlanPreviewFootnote {
    init(store: CuadraoPlanPreview, accounts: CuadraoAccountsPreview, initial: CanvasPlan, spanish: Bool, onSave: ((UUID) -> Void)? = nil) {
        self.init(host: .init(store: store, accounts: accounts, initial: initial, spanish: spanish, onSave: onSave), initial: initial, spanish: spanish,
                  details: { _ in EmptyView() }, footer: { PlanPreviewFootnote(spanish: spanish) })
    }
}
