import Network
import SwiftUI

/// One watch on the network for the signed-in app. Saves are not queued: while offline they do not go through.
/// A loss of signal shows only after it lasts `debounce`, so a Wi-Fi to cellular handoff or a blip at launch never flashes the strip.
@MainActor
final class CuadraoConnectivity: ObservableObject {
    @Published private(set) var online = true
    private let monitor: NWPathMonitor?
    private let debounce: Duration
    private var pendingLoss: Task<Void, Never>?
    private var settled = false

    /// `monitoring: false` is for the gallery, which drives `report` by hand and never touches the real network.
    init(monitoring: Bool = true, debounce: Duration = .seconds(1)) {
        self.debounce = debounce
        guard monitoring else { monitor = nil; return }
        let monitor = NWPathMonitor()
        self.monitor = monitor
        monitor.pathUpdateHandler = { [weak self] path in
            let satisfied = path.status == .satisfied
            Task { @MainActor in self?.report(satisfied) }
        }
        monitor.start(queue: DispatchQueue(label: "cuadrao.connectivity"))
    }

    deinit { monitor?.cancel() }

    func report(_ satisfied: Bool) {
        if satisfied {
            pendingLoss?.cancel(); pendingLoss = nil
            apply(true)
        } else if online, pendingLoss == nil {
            pendingLoss = Task {
                try? await Task.sleep(for: debounce)
                guard !Task.isCancelled else { return }
                pendingLoss = nil
                apply(false)
            }
        }
        settled = true
    }

    private func apply(_ satisfied: Bool) {
        guard satisfied != online else { return }
        online = satisfied
        if satisfied { CuadraoHaptics.success() } else { CuadraoHaptics.warning() }
    }
}

/// A calm strip under the status bar, in the manner of Alta's "Network offline. Reconnecting…" with the consequence on the second line.
/// https://mobbin.com/screens/2b00c4b9-d2a6-4a6a-9d95-2aba49348be1
struct CuadraoOfflineBanner: View {
    let spanish: Bool

    private var title: String { spanish ? "Sin conexión. Reconectando…" : "No connection. Reconnecting…" }
    private var detail: String {
        spanish ? "Por ahora no se pueden guardar cambios. Ves lo último guardado." : "Changes can't be saved for now. You see what was last saved."
    }

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: "wifi.slash").font(.subheadline.weight(.semibold)).padding(.top, 2)
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(.subheadline.weight(.semibold))
                Text(detail).font(.footnote).foregroundStyle(.secondary)
            }
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 16).padding(.vertical, 12)
        .background(WelcomePalette.surface, in: RoundedRectangle(cornerRadius: 14))
        .padding(.horizontal, 20).padding(.bottom, 8)
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("cuadrao.offline.banner")
        .onAppear { UIAccessibility.post(notification: .announcement, argument: title + " " + detail) }
    }
}

extension View {
    /// Shows the offline strip above this view while the network is gone.
    func cuadraoOfflineBanner(_ connectivity: CuadraoConnectivity, spanish: Bool) -> some View {
        modifier(CuadraoOfflineHost(connectivity: connectivity, spanish: spanish))
    }
}

private struct CuadraoOfflineHost: ViewModifier {
    @ObservedObject var connectivity: CuadraoConnectivity
    let spanish: Bool
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    func body(content: Content) -> some View {
        content
            .safeAreaInset(edge: .top, spacing: 0) {
                if !connectivity.online {
                    CuadraoOfflineBanner(spanish: spanish).transition(reduceMotion ? .opacity : .move(edge: .top).combined(with: .opacity))
                }
            }
            .animation(reduceMotion ? nil : .snappy(duration: 0.3), value: connectivity.online)
    }
}
