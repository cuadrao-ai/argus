import SwiftUI

/// The one template for a load or save that failed: what happened in one line, then one way to try again.
/// After Marcus by Goldman Sachs: an icon, one sentence and a single underlined "Try again".
/// https://mobbin.com/screens/c52eea8e-2fe0-4f57-a5f8-9f8a976faa37
struct CuadraoRetryState: View {
    let message: LocalizedStringKey
    let spanish: Bool
    var identifier = "retry.state"
    var retryIdentifier = "retry.action"
    let retry: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label { Text(message) } icon: { Image(systemName: "exclamationmark.circle") }
                .font(.subheadline).foregroundStyle(.secondary).accessibilityIdentifier(identifier)
            Button(action: retry) {
                Text(spanish ? "Intentar de nuevo" : "Try again").underline().frame(minHeight: 44, alignment: .leading)
            }
            .font(CuadraoTypography.action).accessibilityIdentifier(retryIdentifier)
        }
    }
}
