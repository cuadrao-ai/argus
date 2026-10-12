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
        && draft.annualRate.isFinite && (0...100).contains(draft.annualRate)
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
                            Text(spanish ? "Dale un nombre." : "Make it yours.").font(CuadraoTypography.section)
                            TextField(spanish ? "Por ejemplo, mi próximo viaje" : "For example, my next trip", text: $draft.name)
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
                        CuadraoChoiceMenu(title: spanish ? "Espacio" : "Space", selection: $draft.spaceID,
                            values: host.spaces.map(\.id),
                            valueTitle: { id in host.spaces.first { $0.id == id }?.title ?? (spanish ? "Espacio archivado" : "Archived space") })
                            .accessibilityIdentifier("plan-edit-space")
                        Spacer()
                    }
                    if !editing {
                        Text(spanish ? "La moneda queda fija al crear el plan." : "Currency is fixed once you create the plan.").font(.caption).foregroundStyle(.secondary)
                    }
                    if draft.spaceID == "household" {
                        Text(spanish ? "Este plan pertenece a Hogar. Sus miembros podrán verlo; tus cuentas personales siguen siendo privadas." : "This plan belongs to Household. Its members will see it; your personal accounts stay private.")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                    if host.showsLook {
                        DisclosureGroup(spanish ? "Darle mi estilo" : "Make it mine") {
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
                                    HStack {
                                        Text(spanish ? "Interés anual (%)" : "Annual interest (%)")
                                        TextField("0", text: $rateText).keyboardType(.decimalPad).focused($rateFocused).multilineTextAlignment(.trailing)
                                            .accessibilityIdentifier(ids.rate)
                                            .onChange(of: rateText) { _, text in draft.annualRate = Double(text.replacingOccurrences(of: ",", with: ".")) ?? 0 }
                                    }.padding(18)
                                    .onAppear { if draft.annualRate != 0 && rateText.isEmpty { rateText = draft.annualRate.formatted(.number.grouping(.never)) } }
                                    Text(spanish ? "La estimación supone una tasa fija, pagos mensuales, sin compras nuevas ni comisiones." : "The estimate assumes a fixed rate, monthly payments, no new purchases or fees.")
                                        .font(.caption).foregroundStyle(.secondary)
                                }
                            }.padding(.top, 12)
                        } label: { Text(spanish ? "Punto de partida" : "Starting point").font(.subheadline.weight(.medium)) }
                    }
                    if draft.kind == .debt && host.showsRate && !showDetails {
                        Text(spanish ? "Supuesto: interés anual de \(draft.annualRate.formatted())%. Puedes cambiarlo en Punto de partida." : "Assumption: \(draft.annualRate.formatted())% annual interest. Change it in Starting point.")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                    if draft.kind != .budget && host.showsTarget && host.showsRecorded {
                        let months = draft.months(at: draft.monthly)
                        VStack(alignment: .leading, spacing: 5) {
                            Text(months.map { $0 == 0 ? (spanish ? "Ya llegaste." : "You're there.") : PlanFormat.month(after: $0, spanish: spanish) }
                                 ?? (spanish ? "Prueba un aporte mayor" : "Try a higher amount"))
                                .font(CuadraoTypography.section).foregroundStyle(WelcomePalette.pine)
                            Text(spanish ? "Fecha estimada con este ritmo. Puedes ajustarlo después." : "Estimated date at this pace. You can adjust it later.")
                                .font(.caption).foregroundStyle(.secondary)
                        }
                    }
                    if !valid {
                        Text(spanish ? "Añade un nombre y revisa los montos." : "Add a name and check the amounts.")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                    footer()
                }.padding(24)
            }.safeAreaInset(edge: .bottom) {
                VStack(spacing: 12) {
                    PlanPrimaryButton(title: editing ? (spanish ? "Guardar cambios" : "Save changes") : (spanish ? "Crear plan" : "Create plan")) {
                        draft.name = draft.name.trimmingCharacters(in: .whitespacesAndNewlines)
                        if draft.kind == .budget { draft.monthly = draft.target }
                        host.save(draft)
                        if host.dismissesOnSave { dismiss() }
                    }.disabled(!valid || host.saving).opacity(valid && !host.saving ? 1 : 0.45).accessibilityIdentifier(ids.save)
                }.padding(.horizontal, 24).padding(.vertical, 12).background(.regularMaterial)
            }.cuadraoFormKeyboard().background(WelcomePalette.background)
                .navigationTitle(editing ? (spanish ? "Editar plan" : "Edit plan") : (spanish ? "Un nuevo plan" : "A new plan"))
                .navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    CuadraoCancelToolbar(title: spanish ? "Cancelar" : "Cancel", disabled: host.saving) {
                        if draft != initial { discard = true } else { dismiss() }
                    }
                }
                .confirmationDialog(spanish ? "¿Descartar cambios?" : "Discard changes?", isPresented: $discard, titleVisibility: .visible) {
                    Button(spanish ? "Descartar" : "Discard", role: .destructive) { dismiss() }
                }
        }.sensoryFeedback(.selection, trigger: draft.look)
            .presentationDragIndicator(.visible).interactiveDismissDisabled(draft != initial || host.saving)
    }
    private var monthlyTitle: String { host.monthlyTitle ?? (spanish ? "Cada mes" : "Each month") }
    private var kindPicker: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(spanish ? "¿Qué tienes en mente?" : "What do you have in mind?").font(CuadraoTypography.section)
            ViewThatFits(in: .horizontal) {
                HStack(spacing: 8) { kindButtons }
                VStack(alignment: .leading, spacing: 8) { kindButtons }
            }
        }
    }
    private var kindButtons: some View {
        ForEach(host.allowedKinds) { kind in
            Button { draft.kind = kind } label: {
                Text(kind == .goal ? (spanish ? "Meta" : "Goal") : kind == .budget ? (spanish ? "Mi mes" : "My month") : (spanish ? "Deuda" : "Debt")).font(.subheadline)
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
