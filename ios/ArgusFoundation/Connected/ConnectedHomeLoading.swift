import SwiftUI

/// Home before the signed-in models exist: blocks in Home's footprint. It never shimmers forever: after a session
/// error, or 12 seconds, it offers one retry that asks the session to restore again.
struct ConnectedHomeLoading: View {
    @ObservedObject var auth: ProfileAuthModel
    @State private var waited = false
    @State private var attempt = 0

    private var failed: Bool { auth.errorKey != nil || waited }

    var body: some View {
        VStack(alignment: .leading, spacing: 24) {
            if failed {
                CuadraoRetryState(message: LocalizedStringKey(auth.errorKey ?? "home.loadFailed"), identifier: "home.loading.error",
                                  retryIdentifier: "home.loading.retry") {
                    waited = false; attempt += 1
                    Task { await auth.restore() }
                }
            } else {
                CuadraoSkeleton(layout: .home, identifier: "home.loading")
            }
        }
        .padding(.horizontal, 20).padding(.top, 24)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        .task(id: attempt) {
            try? await Task.sleep(for: .seconds(12))
            if !Task.isCancelled { waited = true }
        }
    }
}
