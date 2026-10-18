import SwiftUI

public struct ReleaseConnectedSourcesView: View {
    public let sources: [ReleaseConnectedSource]
    public let onDisconnect: (String) -> Void
    public let onRetry: (String) -> Void
    @State private var confirmation: ReleaseConnectedSource?
    @Environment(\.locale) private var locale

    public init(sources: [ReleaseConnectedSource], onDisconnect: @escaping (String) -> Void,
                onRetry: @escaping (String) -> Void) {
        self.sources = sources; self.onDisconnect = onDisconnect; self.onRetry = onRetry
    }

    private var spanish: Bool { CuadraoCopy.isSpanish() }

    public var body: some View {
        List {
            if sources.isEmpty {
                Section {
                    Label(CuadraoCopy.text("copy.releaseConnectedSourcesView.83c417a8a1", spanish: spanish), systemImage: "link")
                    Text(CuadraoCopy.text("copy.releaseConnectedSourcesView.236ae02c2d", spanish: spanish))
                        .foregroundStyle(.secondary)
                }
            }
            ForEach(sources) { source in
                Section {
                    Text(source.name).font(CuadraoTypography.action)
                    if !source.detail.isEmpty { Text(source.detail).font(CuadraoTypography.supporting).foregroundStyle(.secondary) }
                    sourceStatus(source)
                }.accessibilityIdentifier("identity.source.\(source.id)")
            }
        }
        .font(CuadraoTypography.body).tint(WelcomePalette.pine)
        .navigationTitle(CuadraoCopy.text("copy.releaseConnectedSourcesView.3985a96bb5", spanish: spanish))
        .navigationBarTitleDisplayMode(.inline)
        .confirmationDialog(CuadraoCopy.text("copy.releaseConnectedSourcesView.245aa7fd2c", spanish: spanish),
                            isPresented: Binding(get: { confirmation != nil }, set: { if !$0 { confirmation = nil } }),
                            titleVisibility: .visible, presenting: confirmation) { source in
            Button(CuadraoCopy.text("copy.releaseConnectedSourcesView.65ca190c04", spanish: spanish), role: .destructive) { onDisconnect(source.id) }
            Button(CuadraoCopy.text("copy.releaseConnectedSourcesView.62a128b722", spanish: spanish), role: .cancel) { confirmation = nil }
        } message: { source in
            Text(CuadraoCopy.text("copy.releaseConnectedSourcesView.81efeba55a", spanish: spanish, String(describing: source.name)))
        }
        .accessibilityIdentifier("identity.sources.screen")
    }

    @ViewBuilder private func sourceStatus(_ source: ReleaseConnectedSource) -> some View {
        switch source.state {
        case .connected:
            Button(CuadraoCopy.text("copy.releaseConnectedSourcesView.65ca190c04", spanish: spanish), role: .destructive) { confirmation = source }
                .accessibilityIdentifier("identity.source.disconnect.\(source.id)")
        case .disconnecting:
            ProgressView(CuadraoCopy.text("copy.releaseConnectedSourcesView.f002ce31b8", spanish: spanish))
        case .pending:
            Label(CuadraoCopy.text("copy.releaseConnectedSourcesView.34ffe88c0a", spanish: spanish), systemImage: "clock")
            Text(CuadraoCopy.text("copy.releaseConnectedSourcesView.e08f505ce9", spanish: spanish))
                .font(CuadraoTypography.supporting).foregroundStyle(.secondary)
            retry(source)
        case .failed:
            Label(CuadraoCopy.text("copy.releaseConnectedSourcesView.5a85afd3f6", spanish: spanish), systemImage: "exclamationmark.circle")
            retry(source)
        case .disconnected:
            Label(CuadraoCopy.text("copy.releaseConnectedSourcesView.906459808e", spanish: spanish), systemImage: "checkmark.circle")
        }
    }

    private func retry(_ source: ReleaseConnectedSource) -> some View {
        Button(CuadraoCopy.text("copy.releaseConnectedSourcesView.e4bd371375", spanish: spanish)) { onRetry(source.id) }
            .accessibilityIdentifier("identity.source.retry.\(source.id)")
    }
}
