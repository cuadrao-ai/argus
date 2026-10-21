import SwiftUI

enum CanvasVoiceProposal { case proposed, reviewed }

/// Illustrates agent-to-surface handoff only; never writes a goal or allocation.
struct CuadraoVoiceProposalCanvas: View {
    @Binding var state: CanvasVoiceProposal?
    let spanish: Bool
    @State private var reviewing = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 28) {
                    Text("Plan").font(CuadraoTypography.screen)
                    Text(spanish ? "Lo conversamos. Aquí lo ves." : "Talk it through. See it here.")
                        .foregroundStyle(.secondary)
                    VStack(alignment: .leading, spacing: 20) {
                        Label(spanish ? "Propuesta de ejemplo" : "Example proposal", systemImage: "waveform")
                            .font(.caption).foregroundStyle(.secondary)
                        Text(spanish ? "Tu fondo de emergencia" : "Your emergency fund")
                            .font(CuadraoTypography.section)
                        Text("DOP 3,000").font(.title.weight(.medium)).monospacedDigit()
                        Text(spanish ? "al mes · durante 6 meses" : "per month · for 6 months").foregroundStyle(.secondary)
                        Divider()
                        LabeledContent(spanish ? "Aportes previstos" : "Planned contributions", value: "DOP 18,000")
                        Text(spanish ? "Es una propuesta, no dinero ahorrado. Tus cuentas no cambian." : "A proposal, not saved money. Your accounts stay unchanged.")
                            .font(.footnote).foregroundStyle(.secondary)
                        if state == .reviewed {
                            Label(spanish ? "Revisada en la vista previa" : "Reviewed in preview", systemImage: "checkmark.circle")
                                .foregroundStyle(WelcomePalette.pine)
                        } else {
                            Button(spanish ? "Revisar propuesta" : "Review proposal") { reviewing = true }
                                .font(CuadraoTypography.action).frame(maxWidth: .infinity, minHeight: 48)
                                .foregroundStyle(WelcomePalette.onAccent)
                                .background(WelcomePalette.pine, in: Capsule())
                        }
                        Button(spanish ? "Descartar" : "Dismiss") { state = nil }
                            .frame(maxWidth: .infinity, minHeight: 44).foregroundStyle(.secondary)
                    }.padding(24).background(WelcomePalette.surface, in: RoundedRectangle(cornerRadius: 28))
                }.padding(24).padding(.bottom, 100)
            }.background(WelcomePalette.background).cuadraoSoftScrollEdges()
                .toolbar(.hidden, for: .navigationBar).toolbar(.hidden, for: .tabBar)
                .sheet(isPresented: $reviewing) {
                    NavigationStack {
                        Form {
                            Section {
                                LabeledContent(spanish ? "Meta" : "Goal", value: spanish ? "Fondo de emergencia" : "Emergency fund")
                                LabeledContent(spanish ? "Aporte mensual" : "Monthly contribution", value: "DOP 3,000")
                                LabeledContent(spanish ? "Plazo" : "Duration", value: spanish ? "6 meses" : "6 months")
                            } footer: {
                                Text(spanish ? "Esta demostración no crea metas ni mueve dinero." : "This demonstration doesn't create goals or move money.")
                            }
                            Button(spanish ? "Marcar como revisada" : "Mark reviewed") { state = .reviewed; reviewing = false }
                        }.navigationTitle(spanish ? "Revisar propuesta" : "Review proposal").navigationBarTitleDisplayMode(.inline)
                            .toolbar { CuadraoCancelToolbar(title: spanish ? "Cancelar" : "Cancel") { reviewing = false } }
                    }.presentationDetents([.medium, .large]).presentationDragIndicator(.visible)
                }
        }
    }
}
