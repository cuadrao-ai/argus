import SwiftUI

/// Holds the launch screen until the session is known, then hands over to the app. Past the deadline, or when a
/// stored session could not be confirmed, it says so and offers Reintentar.
struct LaunchGateHost<Content: View>: View {
    @EnvironmentObject private var auth: ProfileAuthModel
    @ViewBuilder let content: () -> Content
    @State private var waitingSince = Date()
    @State private var now = Date()

    private var gate: LaunchGate {
        LaunchGate(restored: auth.hasRestored, authenticated: auth.state == .authenticated,
                   storedSessionUnconfirmed: auth.storedSessionUnconfirmed, waitingSince: waitingSince, now: now)
    }

    var body: some View {
        switch gate {
        case .signedIn, .signedOut:
            content()
        case .unknown:
            CuadraoLaunchScreen()
                .task(id: waitingSince) {
                    try? await Task.sleep(for: .seconds(LaunchGate.deadline))
                    now = Date()
                }
        case .unreachable:
            CuadraoLaunchScreen(unreachable: true, retrying: auth.busy) {
                waitingSince = Date()
                now = waitingSince
                Task { await auth.restore() }
            }
        }
    }
}

/// Continues the static launch screen (Info.plist UILaunchScreen): BrandPaper with the lockup at its natural
/// size, centred on the full screen. A quiet loader appears below it only when the wait passes one second.
struct CuadraoLaunchScreen: View {
    static let loaderDelay: Duration = .seconds(1)
    var unreachable = false
    var retrying = false
    var retry: () -> Void = {}
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var slow = false

    var body: some View {
        ZStack {
            WelcomePalette.brandPaper
            Image("CuadraoLockup")
                .accessibilityLabel("cuadrao")
            // Same centre as the lockup, so the logo never moves when the loader or the message appears.
            Color.clear
                .frame(width: 280, height: 56)
                .overlay(alignment: .top) { below.offset(y: 96) }
        }
        .ignoresSafeArea()
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(unreachable ? "app.unreachable" : "app.launching")
        .task {
            try? await Task.sleep(for: Self.loaderDelay)
            withAnimation(reduceMotion ? nil : .easeIn(duration: 0.3)) { slow = true }
        }
    }

    @ViewBuilder private var below: some View {
        if unreachable {
            VStack(spacing: 16) {
                Text("launch.unreachable")
                    .font(.body)
                    .foregroundStyle(WelcomePalette.ink)
                    .multilineTextAlignment(.center)
                    .frame(width: 280)
                    .accessibilityIdentifier("app.unreachable.message")
                if retrying {
                    ProgressView().accessibilityIdentifier("app.unreachable.retrying")
                } else {
                    Button("launch.retry", action: retry)
                        .font(.system(.body, weight: .semibold))
                        .tint(WelcomePalette.pine)
                        .accessibilityIdentifier("app.unreachable.retry")
                }
            }
        } else if slow {
            ProgressView()
                .transition(.opacity)
                .accessibilityIdentifier("app.launching.loader")
        }
    }
}
