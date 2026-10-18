import SwiftUI

public struct ReleaseMemoryControlsView: View {
    public let state: ReleaseMemoryState
    public let onSetEnabled: (Bool) -> Void
    public let onReset: () -> Void
    @Environment(\.locale) private var locale
    @State private var confirmingReset = false

    public init(state: ReleaseMemoryState, onSetEnabled: @escaping (Bool) -> Void, onReset: @escaping () -> Void) {
        self.state = state; self.onSetEnabled = onSetEnabled; self.onReset = onReset
    }

    private var spanish: Bool { CuadraoCopy.isSpanish() }

    public var body: some View {
        List {
            Section {
                Toggle(CuadraoCopy.text("copy.releaseMemoryControlsView.fe432c633c", spanish: spanish), isOn: Binding(get: { state.isEnabled }, set: onSetEnabled))
                    .disabled(state.isBusy).accessibilityIdentifier("identity.memory.enabled")
                Text(CuadraoCopy.text("copy.releaseMemoryControlsView.21399ac39f", spanish: spanish))
                    .font(CuadraoTypography.supporting).foregroundStyle(.secondary)
                if !state.isEnabled && !state.isBusy {
                    Label(CuadraoCopy.text("copy.releaseMemoryControlsView.2d81d3a8b8", spanish: spanish), systemImage: "pause.circle")
                }
            } footer: {
                Text(CuadraoCopy.text("copy.releaseMemoryControlsView.105544768c", spanish: spanish))
            }
            Section {
                if state.isBusy { ProgressView(CuadraoCopy.text("copy.releaseMemoryControlsView.61df2b5921", spanish: spanish)) }
                if case .failed = state {
                    Label(CuadraoCopy.text("copy.releaseMemoryControlsView.30ce7c0d56", spanish: spanish),
                          systemImage: "exclamationmark.circle")
                }
                if case .resetComplete = state {
                    Label(CuadraoCopy.text("copy.releaseMemoryControlsView.e48acc65ad", spanish: spanish), systemImage: "checkmark.circle")
                        .accessibilityIdentifier("identity.memory.resetComplete")
                }
                Button(CuadraoCopy.text("copy.releaseMemoryControlsView.c9b284078e", spanish: spanish), role: .destructive) { confirmingReset = true }
                    .disabled(state.isBusy).accessibilityIdentifier("identity.memory.reset")
            }
        }
        .font(CuadraoTypography.body).tint(WelcomePalette.pine)
        .navigationTitle(CuadraoCopy.text("copy.releaseMemoryControlsView.7fa6d06e03", spanish: spanish))
        .navigationBarTitleDisplayMode(.inline)
        .confirmationDialog(CuadraoCopy.text("copy.releaseMemoryControlsView.e2a23146c1", spanish: spanish),
                            isPresented: $confirmingReset, titleVisibility: .visible) {
            Button(CuadraoCopy.text("copy.releaseMemoryControlsView.82eb4412d9", spanish: spanish), role: .destructive, action: onReset)
            Button(CuadraoCopy.text("copy.releaseMemoryControlsView.62a128b722", spanish: spanish), role: .cancel) {}
        } message: {
            Text(CuadraoCopy.text("copy.releaseMemoryControlsView.f12ba99660", spanish: spanish))
        }
        .accessibilityIdentifier("identity.memory.screen")
    }
}
