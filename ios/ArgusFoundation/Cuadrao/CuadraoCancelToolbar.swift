import SwiftUI

/// Cancel as plain text: no glass oval around it, so there is no rim or shadow under it either.
struct CuadraoCancelToolbar: ToolbarContent {
    let title: String
    var disabled = false
    var identifier: String?
    let action: () -> Void

    var body: some ToolbarContent {
        if #available(iOS 26.0, *) {
            ToolbarItem(placement: .cancellationAction) { label }.sharedBackgroundVisibility(.hidden)
        } else {
            ToolbarItem(placement: .cancellationAction) { label }
        }
    }

    private var label: some View {
        Button(action: action) {
            Text(LocalizedStringKey(title)).fixedSize().frame(minHeight: 44).contentShape(Rectangle())
        }
            .buttonStyle(.plain)
            .foregroundStyle(disabled ? Color.secondary : WelcomePalette.pine)
            .disabled(disabled)
            .modifier(CuadraoToolbarIdentifier(identifier: identifier))
    }
}
