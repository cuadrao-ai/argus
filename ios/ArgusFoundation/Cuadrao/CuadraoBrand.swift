import SwiftUI

/// The one place the Cuadrao lockup is drawn: Marketing's mark-and-wordmark SVG, unchanged, light or dark from the
/// asset catalog. Welcome, the invitation card and the chat empty state all use it and differ only in size.
/// The lockup is 4.79 times as wide as it is tall, so the default width keeps the 32 pt height the old
/// glyph-and-text lockup had and the layouts around it do not move.
struct CuadraoBrand: View {
    static let compactWidth: CGFloat = 153

    var maxWidth: CGFloat = Self.compactWidth

    var body: some View {
        Image("CuadraoLockup")
            .resizable()
            .scaledToFit()
            .frame(maxWidth: maxWidth)
            .accessibilityIdentifier("cuadrao.brand")
    }
}
