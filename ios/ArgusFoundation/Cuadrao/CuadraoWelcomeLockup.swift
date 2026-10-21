import SwiftUI

/// The welcome screen's one brand composition: the shared lockup at hero size.
struct CuadraoWelcomeLockup: View {
    /// Wide enough to read as the main mark, and it narrows on small screens rather than clipping.
    static let width: CGFloat = 268

    var body: some View {
        CuadraoBrand(maxWidth: Self.width)
            .accessibilityLabel(CuadraoCopy.text("copy.cuadraoWelcomeLockup.d6c2cf736d", spanish: CuadraoCopy.isSpanish()))
            .accessibilityIdentifier("cuadrao.welcome.lockup")
    }
}

extension WelcomePalette {
    /// The website's page colours: #fafbf8 paper on light, #172b26 ink on dark. The welcome screen uses them
    /// because the dark lockup is drawn for #172b26 and changes tone on any other dark. The BrandPaper asset
    /// owns the values so the static launch screen and the app paint the same colour.
    static let brandPaper = Color("BrandPaper")
}
