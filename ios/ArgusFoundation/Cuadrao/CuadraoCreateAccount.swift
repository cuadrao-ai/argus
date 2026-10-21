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
                        title: signingIn ? (CuadraoCopy.text("copy.connectedCuadraoAuth.4e250a863e", spanish: spanish))
                            : (CuadraoCopy.text("copy.connectedCuadraoAuth.b12eabc5ce", spanish: spanish)),
                        detail: signingIn ? (CuadraoCopy.text("copy.connectedCuadraoAuth.adf63b5a8b", spanish: spanish))
                            : (CuadraoCopy.text("copy.connectedCuadraoAuth.a20acd8081", spanish: spanish)))
                    Spacer(minLength: 64)
                    VStack(spacing: 14) {
                        if CuadraoFirstRelease.showsSocialSignIn {
                            PreviewAppleButton(dark: colorScheme == .dark) {
                                previewAction = CuadraoCopy.text("copy.cuadraoCreateAccount.3748d5e95d", spanish: spanish)
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
                            Label(CuadraoCopy.text("copy.connectedCuadraoAuth.77a84bd8c0", spanish: spanish), systemImage: "envelope")
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
                    if !signingIn {
                        CuadraoSignupAcceptance(spanish: spanish)
                    }
                    Button {
                        signingIn.toggle()
                    } label: {
                        (Text(signingIn ? (CuadraoCopy.text("copy.connectedCuadraoAuth.ee35d984be", spanish: spanish))
                              : (CuadraoCopy.text("copy.connectedCuadraoAuth.d136a4f355", spanish: spanish)))
                            .foregroundColor(.secondary)
                         + Text(signingIn ? (CuadraoCopy.text("copy.connectedCuadraoAuth.27a253a4e0", spanish: spanish))
                               : (CuadraoCopy.text("copy.connectedCuadraoAuth.d4c6a5c05c", spanish: spanish)))
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
            Button(CuadraoCopy.text("copy.cuadraoAccountCanvas.43385c465a", spanish: spanish), role: .cancel) { previewAction = nil }
        } message: {
            Text(CuadraoCopy.text("copy.cuadraoCreateAccount.bba1cc8edf", spanish: spanish))
        }
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
