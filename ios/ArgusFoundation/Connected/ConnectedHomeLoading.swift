import SwiftUI

/// Home before the signed-in models exist: blocks in Home's footprint, inset as the real Home is. A session error shows
/// its message with one retry. A slow load keeps the blocks and says it is still loading, with the same retry link after
/// 12 seconds. The view leaves when Home's data arrives.
struct ConnectedHomeLoading: View {
    @ObservedObject var auth: ProfileAuthModel
    @State private var slow = false
    @State private var attempt = 0

    var body: some View {
        VStack(alignment: .leading, spacing: 24) {
            if let error = auth.errorKey {
                CuadraoRetryState(message: LocalizedStringKey(error), identifier: "home.loading.error",
                                  retryIdentifier: "home.loading.retry", retry: retry)
            } else {
                CuadraoSkeleton(layout: .home, identifier: "home.loading")
                if slow {
                    CuadraoRetryState(message: "home.stillLoading", symbol: "clock", identifier: "home.loading.slow",
                                      retryIdentifier: "home.loading.retry", retry: retry)
                }
            }
        }
        .padding(.horizontal, 24).padding(.top, 28)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        .task(id: attempt) {
            try? await Task.sleep(for: .seconds(12))
            if !Task.isCancelled { slow = true }
        }
    }

    private func retry() {
        slow = false; attempt += 1
        Task { await auth.restore() }
    }
}
