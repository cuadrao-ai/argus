import SwiftUI

struct CuadraoSignupAcceptance: View {
    let spanish: Bool
    var legal: CuadraoLegalURLs = .current

    var body: some View {
        if let terms = legal.terms, let privacy = legal.privacy {
            Text(LocalizedStringKey(CuadraoCopy.text("copy.cuadraoSignupAcceptance.29044df238", spanish: spanish, String(describing: terms.absoluteString), String(describing: privacy.absoluteString))))
                .font(.footnote)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .tint(WelcomePalette.pine)
                .accessibilityIdentifier("cuadrao.signup.acceptance")
                .frame(maxWidth: .infinity)
                .padding(.top, 24)
        }
    }
}
