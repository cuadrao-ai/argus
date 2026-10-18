import SwiftUI

struct CuadraoPlanDetail: View {
    let store: CuadraoPlanPreview
    let accounts: CuadraoAccountsPreview
    let planID: UUID
    let spanish: Bool
    var bottomSpace: CGFloat = 90
    @State private var chatFocus: CanvasChatFocus?
    @State private var editing: PlanEditorRoute?
    @State private var archive = false
    @State private var people = false
    @State private var progressEntry = false
    @Environment(\.dismiss) private var dismiss
    private var plan: CanvasPlan? { store.plan(planID) }

    var body: some View {
        Group {
            if let plan {
                CuadraoPlanDetailPage(bottomSpace: bottomSpace) {
                    heading(plan)
                    if plan.remaining == 0 && plan.kind != .budget {
                        PlanLandscape(look: plan.look).frame(height: 135)
                    } else if plan.kind == .budget && plan.recorded == 0 {
                        VStack(alignment: .leading, spacing: 12) {
                            PlanLandscape(look: plan.look).frame(height: 100)
                            Text(CuadraoCopy.text("copy.cuadraoPlanDetail.82ea69d62d", spanish: spanish))
                                .font(.subheadline).foregroundStyle(.secondary)
                        }
                    }
                    if plan.remaining > 0 || plan.kind == .budget {
                        CuadraoPlanWhatIf(scenario: plan.scenario, spanish: spanish, resetsOn: plan) { amount in
                            var updated = plan
                            if plan.kind == .budget { updated.target = amount } else { updated.monthly = amount }
                            store.save(updated)
                        }
                    }
                    Button { progressEntry = true } label: {
                        Label(CuadraoCopy.text("copy.cuadraoPlanDetail.11c4223212", spanish: spanish), systemImage: "plus.circle").frame(minHeight: 44)
                    }.accessibilityIdentifier("plan-record-progress")
                    facts(plan)
                    if plan.spaceID == "household" { household(plan) }
                    PlanPreviewFootnote(spanish: spanish)
                }
                .toolbar {
                    ToolbarItem(placement: .topBarTrailing) {
                        CuadraoPlanDetailOptions(spanish: spanish) {
                            Button(CuadraoCopy.text("copy.cuadraoAccountCanvas.b44a9adeb4", spanish: spanish), systemImage: "bubble") { chatFocus = .plan(id: plan.id, title: plan.name) }
                                .accessibilityIdentifier("plan-open-chat")
                            Button { editing = .init(plan: plan) } label: { Label(CuadraoCopy.text("copy.cuadraoPlanDetail.507c662ea3", spanish: spanish), systemImage: "pencil") }
                            Button { archive = true } label: { Label(CuadraoCopy.text("copy.connectedCuadraoHome.0960027352", spanish: spanish), systemImage: "archivebox") }
                        }
                    }
                }
                .sheet(isPresented: $progressEntry) {
                    PlanExactAmount(amount: Binding(get: { plan.recorded }, set: { value in
                        var updated = plan; updated.recorded = value; store.save(updated)
                    }), maximum: plan.kind == .debt ? plan.target : CanvasMoney.maximumValue, title: plan.kind.recordedTitle(spanish), currency: plan.currency, spanish: spanish)
                }
                .confirmationDialog(CuadraoCopy.text("copy.cuadraoPlanDetail.3a2244a625", spanish: spanish), isPresented: $archive, titleVisibility: .visible) {
                    Button(CuadraoCopy.text("copy.cuadraoPlanDetail.d81495f770", spanish: spanish)) { store.archive(plan.id, true); dismiss() }
                } message: { Text(CuadraoCopy.text("copy.cuadraoPlanDetail.3429a88e41", spanish: spanish)) }
            } else {
                ContentUnavailableView(CuadraoCopy.text("copy.cuadraoPlanDetail.037615818c", spanish: spanish), systemImage: "square.stack")
            }
        }
        .navigationTitle("").navigationBarTitleDisplayMode(.inline).toolbar(.visible, for: .navigationBar)
        .sheet(item: $editing) { route in
            CuadraoPlanEditor(store: store, accounts: accounts, initial: route.plan, spanish: spanish)
        }
        .sheet(isPresented: $people) { CuadraoHouseholdSheet(data: accounts, spanish: spanish) }
        .contextualCuadrao(focus: $chatFocus, spanish: spanish)
    }

    private func heading(_ plan: CanvasPlan) -> some View {
        CuadraoPlanDetailHeading(display: .init(
            name: plan.name, space: PlanFormat.space(plan.spaceID, accounts: accounts, spanish: spanish), look: plan.look,
            amount: PlanFormat.amount(plan.kind == .debt ? plan.remaining : plan.recorded, currency: plan.currency),
            annotation: plan.kind == .debt ? (CuadraoCopy.text("copy.cuadraoPlanDetail.c55558f313", spanish: spanish)) : plan.kind.recordedTitle(spanish))) {
            if plan.remaining == 0 && plan.kind != .budget {
                Label(CuadraoCopy.text("copy.cuadraoPlanDetail.59d3e81cdd", spanish: spanish), systemImage: "checkmark.seal").font(.subheadline).foregroundStyle(plan.look.color)
            }
        }
    }

    private func facts(_ plan: CanvasPlan) -> some View {
        CuadraoPlanDetailFacts(spanish: spanish) {
            LabeledContent(plan.kind.amountTitle(spanish), value: PlanFormat.amount(plan.target, currency: plan.currency))
            LabeledContent(plan.kind.recordedTitle(spanish), value: PlanFormat.amount(plan.recorded, currency: plan.currency))
            if plan.kind == .debt {
                LabeledContent(CuadraoCopy.text("copy.cuadraoPlanDetail.71b1540ce2", spanish: spanish), value: "\(plan.annualRate.formatted())%")
            }
            Text(plan.scenario.disclosure(spanish: spanish))
                .font(.caption).foregroundStyle(.secondary)
        }
    }
    private func household(_ plan: CanvasPlan) -> some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Text(CuadraoCopy.text("copy.cuadraoPlanDetail.03982777ff", spanish: spanish)).font(CuadraoTypography.section)
                Spacer()
                Button { people = true } label: { Image(systemName: "person.2").frame(width: 44, height: 44) }
                    .accessibilityLabel(CuadraoCopy.text("copy.cuadraoHomeCanvas.132a60da1b", spanish: spanish))
            }
            Text(plan.kind == .budget ? (CuadraoCopy.text("copy.cuadraoPlanDetail.c435d90826", spanish: spanish, String(describing: PlanFormat.amount(plan.target, currency: plan.currency)))) : (CuadraoCopy.text("copy.cuadraoPlanDetail.2ecacc4cb4", spanish: spanish, String(describing: PlanFormat.amount(plan.monthly, currency: plan.currency)))))
                .font(.subheadline)
            Text(plan.kind == .budget ? (CuadraoCopy.text("copy.cuadraoPlanDetail.de34ef500e", spanish: spanish)) : (CuadraoCopy.text("copy.cuadraoPlanDetail.d264f56072", spanish: spanish)))
                .font(.caption).foregroundStyle(.secondary)
        }.padding(22).background(WelcomePalette.surface, in: RoundedRectangle(cornerRadius: 24))
    }
}
