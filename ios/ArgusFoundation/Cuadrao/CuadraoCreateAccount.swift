import AuthenticationServices
import SwiftUI

struct CuadraoCreateAccount: View {
    let spanish: Bool
    @Environment(\.colorScheme) private var colorScheme
    @State private var signingIn: Bool
    @State private var previewAction: String?

    init(spanish: Bool, signingIn: Bool = false) {
        self.spanish = spanish
        _signingIn = State(initialValue: signingIn)
    }

    var body: some View {
        GeometryReader { geometry in
            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    RegistrationHeading(
                        title: signingIn ? (spanish ? "Qué bueno verte." : "Welcome back.")
                            : (spanish ? "Crea tu cuenta." : "Create your account."),
                        detail: signingIn ? (spanish ? "Entra a Cuadrao." : "Sign in to Cuadrao.")
                            : (spanish ? "Tus cuentas y tus planes, en un solo lugar."
                                : "Your accounts and plans, in one place."))
                    Spacer(minLength: 64)
                    VStack(spacing: 14) {
                        if CuadraoFirstRelease.showsSocialSignIn {
                            PreviewAppleButton(dark: colorScheme == .dark) {
                                previewAction = spanish ? "Continuar con Apple" : "Continue with Apple"
                            }
                            .id(colorScheme)
                            .frame(height: 56)
                            .accessibilityIdentifier(signingIn ? "cuadrao.signin.apple" : "cuadrao.signup.apple")
                        }
                        NavigationLink {
                            if signingIn {
                                CuadraoEmailSignIn(spanish: spanish)
                            } else {
                                CuadraoEmailRegistration(spanish: spanish)
                            }
                        } label: {
                            Label(spanish ? "Continuar con correo" : "Continue with email", systemImage: "envelope")
                                .font(.body.weight(.semibold))
                                .frame(maxWidth: .infinity, minHeight: 56)
                                .overlay {
                                    RoundedRectangle(cornerRadius: 16)
                                        .stroke(WelcomePalette.border, lineWidth: 1)
                                }
                                .contentShape(RoundedRectangle(cornerRadius: 16))
                        }
                        .buttonStyle(.plain)
                        .accessibilityIdentifier(signingIn ? "cuadrao.signin.emailChoice" : "cuadrao.signup.email")
                    }
                    if !signingIn && CuadraoLegalURLs.current.hasTermsAndPrivacy {
                        VStack(spacing: 0) {
                            Text(spanish ? "Al crear tu cuenta, aceptas los términos."
                                 : "By creating an account, you accept the terms.")
                                .font(.footnote)
                                .foregroundStyle(.secondary)
                                .multilineTextAlignment(.center)
                            HStack(spacing: 20) {
                                legalButton(spanish ? "Términos" : "Terms")
                                legalButton(spanish ? "Privacidad" : "Privacy")
                            }
                        }
                        .frame(maxWidth: .infinity)
                        .padding(.top, 24)
                    }
                    Button {
                        signingIn.toggle()
                    } label: {
                        (Text(signingIn ? (spanish ? "¿Primera vez aquí? " : "New here? ")
                              : (spanish ? "¿Ya tienes cuenta? " : "Already have an account? "))
                            .foregroundColor(.secondary)
                         + Text(signingIn ? (spanish ? "Crea una cuenta" : "Create an account")
                               : (spanish ? "Inicia sesión" : "Sign in"))
                            .foregroundColor(WelcomePalette.pine).bold())
                            .font(.subheadline)
                            .frame(maxWidth: .infinity, minHeight: 48).contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .padding(.top, 16)
                }
                .padding(.horizontal, 28)
                .padding(.top, 24)
                .padding(.bottom, 20)
                .frame(minHeight: geometry.size.height, alignment: .topLeading)
            }
            .scrollIndicators(.hidden)
        }
        .background(WelcomePalette.background.ignoresSafeArea())
        .foregroundStyle(WelcomePalette.ink)
        .navigationTitle("")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar(.visible, for: .navigationBar)
        .alert(previewAction ?? "", isPresented: Binding(
            get: { previewAction != nil }, set: { if !$0 { previewAction = nil } }
        )) {
            Button(spanish ? "Entendido" : "Got it", role: .cancel) { previewAction = nil }
        } message: {
            Text(spanish ? "Esta opción aún no está conectada en la vista previa. No se envía información."
                 : "This option is not connected in the preview. No information is sent.")
        }
    }

    private func legalButton(_ title: String) -> some View {
        Button { previewAction = title } label: {
            Text(title).underline().font(.footnote)
                .frame(minWidth: 44, minHeight: 44)
                .contentShape(Rectangle())
        }.buttonStyle(.plain)
    }
}

/// Uses Apple's standard control; deliberately makes no authorization request.
private struct PreviewAppleButton: UIViewRepresentable {
    let dark: Bool
    let action: () -> Void

    func makeUIView(context: Context) -> ASAuthorizationAppleIDButton {
        let button = ASAuthorizationAppleIDButton(type: .continue, style: dark ? .white : .black)
        button.cornerRadius = 16
        button.addAction(UIAction { _ in action() }, for: .touchUpInside)
        return button
    }

    func updateUIView(_ uiView: ASAuthorizationAppleIDButton, context: Context) {}
}

#Preview("Cuadrao · Create account") {
    NavigationStack { CuadraoCreateAccount(spanish: true) }
        .tint(WelcomePalette.pine)
        .preferredColorScheme(.light)
}
