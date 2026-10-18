import SwiftUI

struct CuadraoSignupAcceptance: View {
    let spanish: Bool
    var legal: CuadraoLegalURLs = .current

    var body: some View {
        if let terms = legal.terms, let privacy = legal.privacy {
            Text(LocalizedStringKey(spanish
                ? "Al continuar, aceptas los [Términos](\(terms.absoluteString)) y la [Política de privacidad](\(privacy.absoluteString))."
                : "By continuing, you agree to the [Terms](\(terms.absoluteString)) and [Privacy Policy](\(privacy.absoluteString))."))
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
