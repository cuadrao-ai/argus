import SwiftUI

/// Holds the launch screen until the first session restore ends, then hands over to the app.
struct LaunchGateHost<Content: View>: View {
    @EnvironmentObject private var auth: ProfileAuthModel
    @ViewBuilder let content: () -> Content

    var body: some View {
        if LaunchGate(restored: auth.hasRestored, authenticated: auth.state == .authenticated).showsApp {
            content()
        } else {
            CuadraoLaunchScreen()
        }
    }
}

/// Continues the static launch screen (Info.plist UILaunchScreen): BrandPaper with the lockup at its natural
/// size, centred on the full screen. A quiet loader appears below it only when the wait passes one second.
struct CuadraoLaunchScreen: View {
    static let loaderDelay: Duration = .seconds(1)
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var slow = false

    var body: some View {
        ZStack {
            WelcomePalette.brandPaper
            Image("CuadraoLockup")
                .accessibilityLabel("cuadrao")
                .overlay(alignment: .bottom) {
                    if slow {
                        ProgressView()
                            .offset(y: 56)
                            .transition(.opacity)
                            .accessibilityIdentifier("app.launching.loader")
                    }
                }
        }
        .ignoresSafeArea()
        .accessibilityIdentifier("app.launching")
        .task {
            try? await Task.sleep(for: Self.loaderDelay)
            withAnimation(reduceMotion ? nil : .easeIn(duration: 0.3)) { slow = true }
        }
    }
}
