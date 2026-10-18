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
                    Text(CuadraoCopy.text("copy.cuadraoVoiceProposalCanvas.1ede420bb0", spanish: CuadraoCopy.isSpanish())).font(CuadraoTypography.screen)
                    Text(CuadraoCopy.text("copy.cuadraoVoiceProposalCanvas.6736ae9daf", spanish: spanish))
                        .foregroundStyle(.secondary)
                    VStack(alignment: .leading, spacing: 20) {
                        Label(CuadraoCopy.text("copy.cuadraoVoiceProposalCanvas.0e3c8cf671", spanish: spanish), systemImage: "waveform")
                            .font(.caption).foregroundStyle(.secondary)
                        Text(CuadraoCopy.text("copy.cuadraoVoiceProposalCanvas.c80d28f5de", spanish: spanish))
                            .font(CuadraoTypography.section)
                        Text("DOP 3,000").font(.title.weight(.medium)).monospacedDigit()
                        Text(CuadraoCopy.text("copy.cuadraoVoiceProposalCanvas.74e9341edb", spanish: spanish)).foregroundStyle(.secondary)
                        Divider()
                        LabeledContent(CuadraoCopy.text("copy.cuadraoVoiceProposalCanvas.084c901429", spanish: spanish), value: "DOP 18,000")
                        Text(CuadraoCopy.text("copy.cuadraoVoiceProposalCanvas.35424d4f8f", spanish: spanish))
                            .font(.footnote).foregroundStyle(.secondary)
                        if state == .reviewed {
                            Label(CuadraoCopy.text("copy.cuadraoVoiceProposalCanvas.bb8e1e388b", spanish: spanish), systemImage: "checkmark.circle")
                                .foregroundStyle(WelcomePalette.pine)
                        } else {
                            Button(CuadraoCopy.text("copy.cuadraoVoiceProposalCanvas.eb09d1930a", spanish: spanish)) { reviewing = true }
                                .font(CuadraoTypography.action).frame(maxWidth: .infinity, minHeight: 48)
                                .foregroundStyle(WelcomePalette.onAccent)
                                .background(WelcomePalette.pine, in: Capsule())
                        }
                        Button(CuadraoCopy.text("copy.cuadraoVoiceProposalCanvas.a44eb70012", spanish: spanish)) { state = nil }
                            .frame(maxWidth: .infinity, minHeight: 44).foregroundStyle(.secondary)
                    }.padding(24).background(WelcomePalette.surface, in: RoundedRectangle(cornerRadius: 28))
                }.padding(24).padding(.bottom, 100)
            }.background(WelcomePalette.background).cuadraoSoftScrollEdges()
                .toolbar(.hidden, for: .navigationBar).toolbar(.hidden, for: .tabBar)
                .sheet(isPresented: $reviewing) {
                    NavigationStack {
                        Form {
                            Section {
                                LabeledContent(CuadraoCopy.text("copy.cuadraoVoiceProposalCanvas.a666a311f9", spanish: spanish), value: CuadraoCopy.text("copy.cuadraoVoiceProposalCanvas.9057658f68", spanish: spanish))
                                LabeledContent(CuadraoCopy.text("copy.cuadraoVoiceProposalCanvas.db4c3e00e8", spanish: spanish), value: "DOP 3,000")
                                LabeledContent(CuadraoCopy.text("copy.cuadraoVoiceProposalCanvas.94676d6f80", spanish: spanish), value: CuadraoCopy.text("copy.cuadraoVoiceProposalCanvas.d8bf0f51e4", spanish: spanish))
                            } footer: {
                                Text(CuadraoCopy.text("copy.cuadraoVoiceProposalCanvas.f657683439", spanish: spanish))
                            }
                            Button(CuadraoCopy.text("copy.cuadraoVoiceProposalCanvas.0746cbb70e", spanish: spanish)) { state = .reviewed; reviewing = false }
                        }.navigationTitle(CuadraoCopy.text("copy.cuadraoVoiceProposalCanvas.eb09d1930a", spanish: spanish)).navigationBarTitleDisplayMode(.inline)
                            .toolbar { CuadraoCancelToolbar(title: CuadraoCopy.text("copy.connectedCuadraoProfile.62a128b722", spanish: spanish)) { reviewing = false } }
                    }.presentationDetents([.medium, .large]).presentationDragIndicator(.visible)
                }
        }
    }
}
