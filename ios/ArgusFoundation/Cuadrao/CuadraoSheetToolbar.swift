import SwiftUI

/// The one way a sheet closes or confirms from its navigation bar.
/// - Cancel (or Close, Back): plain text on the leading side, from `CuadraoCancelToolbar`.
/// - Confirm: a check mark on the trailing side, only when the sheet has no primary button of its own to confirm.
/// - Done: plain text on the trailing side, for sheets that only show something and have nothing to confirm.
/// None of them has a glass oval, so a sheet never shows two competing confirms.
struct CuadraoConfirmToolbar: ToolbarContent {
    let title: String
    var disabled = false
    var identifier: String?
    let action: () -> Void

    var body: some ToolbarContent {
        if #available(iOS 26.0, *) {
            ToolbarItem(placement: .confirmationAction) { label }.sharedBackgroundVisibility(.hidden)
        } else {
            ToolbarItem(placement: .confirmationAction) { label }
        }
    }

    private var label: some View {
        Button(action: action) {
            Image(systemName: "checkmark").fontWeight(.semibold).frame(minWidth: 44, minHeight: 44).contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .foregroundStyle(disabled ? Color.secondary : WelcomePalette.pine)
        .disabled(disabled)
        .accessibilityLabel(Text(LocalizedStringKey(title)))
        .accessibilityShowsLargeContentViewer()
        .modifier(CuadraoToolbarIdentifier(identifier: identifier))
    }
}

struct CuadraoDoneToolbar: ToolbarContent {
    let title: String
    var identifier: String?
    let action: () -> Void

    var body: some ToolbarContent {
        if #available(iOS 26.0, *) {
            ToolbarItem(placement: .confirmationAction) { label }.sharedBackgroundVisibility(.hidden)
        } else {
            ToolbarItem(placement: .confirmationAction) { label }
        }
    }

    private var label: some View {
        Button(action: action) {
            Text(LocalizedStringKey(title)).fixedSize().frame(minHeight: 44).contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .foregroundStyle(WelcomePalette.pine)
        .modifier(CuadraoToolbarIdentifier(identifier: identifier))
    }
}

struct CuadraoToolbarIdentifier: ViewModifier {
    let identifier: String?

    @ViewBuilder func body(content: Content) -> some View {
        if let identifier { content.accessibilityIdentifier(identifier) } else { content }
    }
}
