import SwiftUI

/// Email-link recovery UI proposal only. The current connected app uses web recovery.
struct CuadraoPasswordRecovery: View {
    let spanish: Bool
    @Binding var email: String
    @Environment(\.dismiss) private var dismiss
    @State private var state: Stage = .entry
    @State private var edited = false
    @State private var showHelp = false
    @FocusState private var focused: Bool
    private enum Stage: Equatable { case entry, sending, sent, offline }
    private var invalid: Bool { edited && !email.isEmpty && !PreviewEmail.isValid(email) && !focused }

    var body: some View {
        GeometryReader { geometry in
            ScrollView {
                VStack(alignment: .leading, spacing: 28) {
                    if state == .sent {
                        sentContent
                    } else {
                        RegistrationHeading(title: spanish ? "Recupera el acceso." : "Recover access.",
                            detail: spanish ? "Te enviaremos un enlace para cambiar tu contraseña."
                                : "We’ll send you a link to change your password.")
                        VStack(alignment: .leading, spacing: 10) {
                            Text(spanish ? "Correo electrónico" : "Email address").font(.subheadline.weight(.medium))
                            TextField(spanish ? "nombre@ejemplo.com" : "name@example.com", text: $email)
                                .textContentType(.emailAddress).keyboardType(.emailAddress)
                                .textInputAutocapitalization(.never).autocorrectionDisabled()
                                .focused($focused).submitLabel(.send)
                                .onSubmit { send() }
                                .modifier(RegistrationField(focused: focused, invalid: invalid))
                                .disabled(state == .sending)
                                .accessibilityLabel(spanish ? "Correo electrónico" : "Email address")
                                .accessibilityIdentifier("cuadrao.recovery.email")
                            if invalid {
                                Label(spanish ? "Revisa el formato del correo." : "Check the email format.", systemImage: "exclamationmark.circle")
                                    .font(.footnote).foregroundStyle(.red)
                            }
                        }
                        if state == .offline {
                            RegistrationNotice(title: spanish ? "No pudimos conectar." : "We couldn’t connect.",
                                detail: spanish ? "Revisa tu conexión y vuelve a intentarlo." : "Check your connection and try again.")
                        }
                    }
                    Spacer(minLength: 24)
                }
                .padding(.horizontal, 28).padding(.top, 24)
                .frame(minHeight: geometry.size.height, alignment: .topLeading)
            }
            .scrollDismissesKeyboard(.interactively)
        }
        .safeAreaInset(edge: .bottom, spacing: 0) {
            RegistrationButton(title: buttonTitle, busy: state == .sending,
                               enabled: state == .sent || PreviewEmail.isValid(email)) {
                if state == .sent { dismiss() } else { send() }
            }
            .accessibilityIdentifier("cuadrao.recovery.submit")
            .padding(.horizontal, 28).padding(.top, 16).padding(.bottom, 20).background(WelcomePalette.background)
        }
        .background(WelcomePalette.background.ignoresSafeArea()).foregroundStyle(WelcomePalette.ink)
        .navigationTitle("").navigationBarTitleDisplayMode(.inline)
        .toolbar {
            CuadraoCancelToolbar(title: spanish ? "Cerrar" : "Close") { dismiss() }
        }
        .onChange(of: focused) { old, _ in if old { edited = true } }
        .onAppear {
            if ProcessInfo.processInfo.arguments.contains("--recovery-state=offline") { state = .offline }
        }
        .task(id: state) {
            guard state == .sending else { return }
            do { try await Task.sleep(for: .milliseconds(800)) } catch { return }
            guard !Task.isCancelled else { return }
            state = .sent
        }
    }

    private var sentContent: some View {
        VStack(alignment: .leading, spacing: 0) {
            Image(systemName: "envelope")
                .font(.system(size: 32, weight: .light)).foregroundStyle(WelcomePalette.pine)
                .frame(width: 72, height: 72)
                .background(WelcomePalette.sage, in: RoundedRectangle(cornerRadius: 22))
                .accessibilityHidden(true).padding(.bottom, 28)
            RegistrationHeading(title: spanish ? "Revisa tu correo." : "Check your email.",
                detail: spanish ? "Si hay una cuenta con este correo, recibirás un enlace para cambiar tu contraseña."
                    : "If there’s an account with this email, you’ll receive a link to change your password.")
            Text(PreviewEmail.normalized(email)).font(.body.weight(.semibold))
                .textSelection(.enabled).padding(.top, 14)
            Button(spanish ? "Cambiar correo" : "Change email") { state = .entry; showHelp = false }
                .font(.subheadline.weight(.medium)).frame(minHeight: 44)
                .foregroundStyle(WelcomePalette.pine).padding(.top, 6)
            Button(spanish ? "¿No encuentras el correo?" : "Can’t find the email?") { showHelp.toggle() }
                .font(.subheadline).frame(minHeight: 44).padding(.top, 24)
            if showHelp {
                Text(CuadraoFirstRelease.showsSocialSignIn
                    ? (spanish ? "Revisa la carpeta de correo no deseado y comprueba la dirección. Si usas Apple para entrar, vuelve y elige Continuar con Apple."
                        : "Check your spam folder and the email address. If you sign in with Apple, go back and choose Continue with Apple.")
                    : (spanish ? "Revisa la carpeta de correo no deseado y comprueba la dirección."
                        : "Check your spam folder and the email address."))
                    .font(.footnote).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
                    .padding(.top, 8)
            }
        }
    }

    private var buttonTitle: String {
        switch state {
        case .entry: spanish ? "Enviar enlace" : "Send link"
        case .sending: spanish ? "Enviando…" : "Sending…"
        case .sent: spanish ? "Volver a iniciar sesión" : "Back to sign in"
        case .offline: spanish ? "Reintentar" : "Try again"
        }
    }
    private func send() {
        guard PreviewEmail.isValid(email), state != .sending else { return }
        email = PreviewEmail.normalized(email)
        focused = false
        state = .sending
    }
}

#Preview("Recovery · Spanish") {
    NavigationStack { CuadraoPasswordRecovery(spanish: true, email: .constant("alex@example.com")) }
}
#Preview("Recovery · English") {
    NavigationStack { CuadraoPasswordRecovery(spanish: false, email: .constant("")) }
}
