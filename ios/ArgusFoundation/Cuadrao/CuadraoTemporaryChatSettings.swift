import SwiftUI

struct CuadraoTemporaryChatSettings: View {
    let store: CuadraoChatPreview
    let spanish: Bool
    let returnToRegular: () -> Void
    private var es: Bool { spanish }

    var body: some View {
        @Bindable var store = store
        VStack(alignment: .leading, spacing: 28) {
            VStack(alignment: .leading, spacing: 18) {
                explanation("clock", CuadraoCopy.text("copy.cuadraoTemporaryChatSettings.575a171d05", spanish: es),
                    CuadraoCopy.text("copy.cuadraoTemporaryChatSettings.cabdb95a90", spanish: es))
                if CuadraoFirstRelease.shows(.memory) {
                    explanation("brain", CuadraoCopy.text("copy.cuadraoTemporaryChatSettings.9aa1d74ee4", spanish: es),
                        CuadraoCopy.text("copy.cuadraoTemporaryChatSettings.b64c68aa55", spanish: es))
                }
            }
            Divider()
            VStack(alignment: .leading, spacing: 12) {
                Toggle(CuadraoCopy.text("copy.cuadraoTemporaryChatSettings.01a72d8998", spanish: es), isOn: $store.useContext)
                    .font(CuadraoTypography.action).disabled(store.contextLocked)
                    .accessibilityIdentifier("temporary-context")
                Text(CuadraoFirstRelease.shows(.memory)
                    ? (CuadraoCopy.text("copy.cuadraoTemporaryChatSettings.eb75a8c499", spanish: es))
                    : (CuadraoCopy.text("copy.cuadraoTemporaryChatSettings.3e56e3da09", spanish: es)))
                    .font(.subheadline).foregroundStyle(.secondary)
                if store.contextLocked {
                    Label(CuadraoCopy.text("copy.cuadraoTemporaryChatSettings.893a989d40", spanish: es), systemImage: "lock")
                        .font(.footnote).foregroundStyle(.secondary)
                } else {
                    Text(store.useContext
                        ? (CuadraoCopy.text("copy.cuadraoTemporaryChatSettings.8766e6d2f9", spanish: es))
                        : (CuadraoCopy.text("copy.cuadraoTemporaryChatSettings.a372752b00", spanish: es)))
                        .font(.footnote).foregroundStyle(.secondary)
                }
            }
            DisclosureGroup(CuadraoCopy.text("copy.cuadraoTemporaryChatSettings.0c32e3f446", spanish: es)) {
                VStack(alignment: .leading, spacing: 14) {
                    Text(CuadraoCopy.text("copy.cuadraoTemporaryChatSettings.d4582b83aa", spanish: es))
                    Text(CuadraoCopy.text("copy.cuadraoTemporaryChatSettings.0c2ff956ee", spanish: es))
                    Text(CuadraoCopy.text("copy.cuadraoTemporaryChatSettings.e1c60adacf", spanish: es))
                }.font(.footnote).foregroundStyle(.secondary).padding(.top, 12)
            }.font(.subheadline)
            Button(action: returnToRegular) {
                Text(CuadraoCopy.text("copy.cuadraoTemporaryChatSettings.d5a1a7ba31", spanish: es))
                    .font(CuadraoTypography.action).frame(maxWidth: .infinity, minHeight: 48)
            }.accessibilityIdentifier("temporary-return")
        }
    }

    private func explanation(_ symbol: String, _ title: String, _ detail: String) -> some View {
        HStack(alignment: .top, spacing: 16) {
            Image(systemName: symbol).font(.system(size: 20)).frame(width: 24, height: 26)
            VStack(alignment: .leading, spacing: 5) {
                Text(title).font(CuadraoTypography.action)
                Text(detail).font(.subheadline).foregroundStyle(.secondary)
            }
        }
    }
}
