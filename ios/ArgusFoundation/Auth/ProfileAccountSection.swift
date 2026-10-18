import SwiftUI

struct ProfileAccountSection: View {
    @ObservedObject var model: ProfileAuthModel

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            Text("auth.account").font(ArgusStyle.display(24, relativeTo: .title2))
                .accessibilityAddTraits(.isHeader)
            if model.busy {
                ProgressView("auth.working").accessibilityIdentifier("auth.working")
            }
            switch model.state {
            case .accountDeletionUncertain: Text("auth.deletion.uncertain")
            case .accountDeletionPending: Text("auth.deletion.pending")
            case .disabled: EmptyView()
            case .configurationInvalid: Text("auth.error.configuration")
            case .signedOut:
                AuthFormView(model: model)
            case .authenticated:
                VStack(alignment: .leading, spacing: 8) {
                    Text(model.profile?.displayName ?? String(localized: "auth.signedIn"))
                        .font(ArgusStyle.display(22, relativeTo: .title2))
                    if let email = model.profile?.email { Text(verbatim: email).textSelection(.enabled) }
                    Text("auth.identity.verified").font(ArgusStyle.body(12, relativeTo: .caption))
                        .foregroundStyle(ArgusStyle.secondary)
                }
                .accessibilityElement(children: .combine)
                .accessibilityIdentifier("auth.identity")
                Button("auth.signOut") { Task { await model.signOut() } }
                    .buttonStyle(PillButtonStyle(primary: false))
                    .accessibilityIdentifier("auth.signOut")
                    .disabled(model.busy)
            case .pendingSignOut:
                Text("auth.signOut.pending").accessibilityIdentifier("auth.signOut.pending")
                Button("auth.signOut.retry") { Task { await model.retryPendingSignOut() } }
                    .buttonStyle(PillButtonStyle())
                    .accessibilityIdentifier("auth.retry")
                    .disabled(model.busy)
            case .credentialValidationRequired, .reauthenticationRequired:
                Text(model.state == .reauthenticationRequired ? "auth.apple.signInAgain.detail" : "auth.apple.validation.detail")
                Button(model.state == .reauthenticationRequired ? "auth.apple.signInAgain.action" : "auth.retry") {
                    Task { if model.state == .reauthenticationRequired { await model.signOut() } else { await model.restore() } }
                }
                .buttonStyle(PillButtonStyle()).disabled(model.busy)
                .accessibilityIdentifier("auth.validation.retry")
                if model.state == .credentialValidationRequired {
                    Button("auth.signOut") { Task { await model.signOut() } }
                        .buttonStyle(PillButtonStyle(primary: false)).disabled(model.busy)
                }
            case .unsupportedAnonymous:
                Text("auth.error.anonymous")
            }
            if let key = model.captureNoticeKey {
                Text(LocalizedStringKey(key)).accessibilityIdentifier("auth.apple.capture.notice")
                Button("auth.apple.capture.dismiss") { model.dismissCaptureNotice() }
            }
            if let key = model.errorKey {
                Text(LocalizedStringKey(key)).foregroundStyle(ArgusStyle.secondary)
                    .accessibilityIdentifier("auth.error")
                    .accessibilityAddTraits(.updatesFrequently)
                if model.state == .authenticated || model.state == .signedOut {
                    Button("auth.retry") { Task { await model.restore() } }
                        .buttonStyle(PillButtonStyle(primary: false))
                        .accessibilityIdentifier("auth.retry")
                        .disabled(model.busy)
                }
            }
            Text("auth.financial.samples")
                .font(ArgusStyle.body(12, relativeTo: .caption))
                .foregroundStyle(ArgusStyle.secondary)
        }
    }
}

private struct AuthFormView: View {
    @ObservedObject var model: ProfileAuthModel
    @State private var signup = false
    @State private var email = ""
    @State private var password = ""
    @State private var displayName = ""
    @State private var challenge: Challenge?
    @State private var recoveryNotice = false
    @Environment(\.openURL) private var openURL
    @Environment(\.locale) private var locale
    @FocusState private var fieldFocused: Bool

    private struct Challenge: Identifiable { let id = UUID(); let url: URL }

    var body: some View {
        if signup { AgeConfirmationGate { form } }
        else { form }
    }

    private var form: some View {
        VStack(alignment: .leading, spacing: 16) {
            if model.confirmationRequired {
                Text("auth.confirmation.title").font(ArgusStyle.display(24, relativeTo: .title2))
                    .accessibilityIdentifier("auth.confirmation")
                Text("auth.confirmation.detail")
                Text("auth.resend.unsupported").font(ArgusStyle.body(14, relativeTo: .subheadline))
                    .foregroundStyle(ArgusStyle.secondary)
                Button("auth.return.signIn") { signup = false; model.returnToSignIn() }
                    .buttonStyle(PillButtonStyle())
                    .accessibilityIdentifier("auth.return.signIn")
            } else {
                if signup {
                    TextField("auth.name", text: $displayName, prompt: Text("auth.name").foregroundStyle(ArgusStyle.secondary)).textContentType(.name)
                        .authField().accessibilityLabel(Text("auth.name")).accessibilityIdentifier("auth.name")
                }
                TextField("auth.email", text: $email, prompt: Text("auth.email").foregroundStyle(ArgusStyle.secondary))
                    .keyboardType(.emailAddress).textContentType(.emailAddress)
                    .textInputAutocapitalization(.never).autocorrectionDisabled()
                    .focused($fieldFocused).authField().accessibilityLabel(Text("auth.email")).accessibilityIdentifier("auth.email")
                SecureField("auth.password", text: $password, prompt: Text("auth.password").foregroundStyle(ArgusStyle.secondary))
                    .textContentType(signup ? .newPassword : .password)
                    .focused($fieldFocused).authField().accessibilityLabel(Text("auth.password")).accessibilityIdentifier("auth.password")
                if signup { Text("auth.password.requirement").font(ArgusStyle.body(12, relativeTo: .caption)) }
                Button(signup ? "auth.createAccount" : "auth.signIn") {
                    fieldFocused = false
                    guard let configuration = model.configuration else { return }
                    challenge = Challenge(url: configuration.captchaURL)
                }
                .buttonStyle(PillButtonStyle())
                .accessibilityIdentifier("auth.submit")
                .disabled(model.busy || email.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || password.isEmpty || (signup && password.count < 8))
                Button(signup ? "auth.return.signIn" : "auth.createAccount") {
                    signup.toggle(); password = ""; model.returnToSignIn()
                }
                .buttonStyle(PillButtonStyle(primary: false))
                .accessibilityIdentifier("auth.createAccount")
                .disabled(model.busy)
                Button(action: recover) {
                    Text("auth.forgotPassword").frame(minHeight: 48).contentShape(Rectangle())
                }
                    .accessibilityIdentifier("auth.forgotPassword")
                    .disabled(model.busy)
                Text("auth.recovery.hint")
                    .font(ArgusStyle.body(12, relativeTo: .caption))
                    .foregroundStyle(ArgusStyle.secondary)
                if recoveryNotice {
                    Text("auth.recovery.detail").font(ArgusStyle.body(14, relativeTo: .subheadline))
                        .accessibilityIdentifier("auth.recovery.notice")
                }
                let legal = CuadraoLegalURLs.current
                if legal.hasPages {
                    HStack(spacing: 18) {
                        if let terms = legal.terms {
                            Link(destination: terms) {
                                Text("auth.terms").frame(minWidth: 44, minHeight: 48).contentShape(Rectangle())
                            }
                        }
                        if let privacy = legal.privacy {
                            Link(destination: privacy) {
                                Text("auth.privacy").frame(minWidth: 44, minHeight: 48).contentShape(Rectangle())
                            }
                        }
                    }
                    .font(ArgusStyle.body(12, relativeTo: .caption)).frame(minHeight: 48)
                }
            }
        }
        .sheet(item: $challenge) { request in
            CaptchaChallengeView(sourceURL: request.url) { result in
                challenge = nil
                switch result {
                case .failure(.cancelled): break
                case .failure(.unavailable): model.presentationError("auth.captcha.error")
                case .success(let token):
                    let submittedPassword = password
                    let submittedEmail = email.trimmingCharacters(in: .whitespacesAndNewlines)
                    let submittedName = displayName.trimmingCharacters(in: .whitespacesAndNewlines)
                    let submittedSignup = signup
                    let submittedLanguage = locale.language.languageCode?.identifier == "es" ? "es-419" : "en"
                    password = ""
                    Task {
                        await model.authenticate(email: submittedEmail,
                                                 password: submittedPassword, captchaToken: token, signup: submittedSignup,
                                                 language: submittedLanguage, displayName: submittedName)
                    }
                }
            }
        }
    }

    private func recover() {
        guard let url = model.configuration?.recoveryURL else { return }
        fieldFocused = false
        password = ""
        recoveryNotice = true
        openURL(url) { accepted in
            if !accepted { model.presentationError("auth.recovery.failed") }
        }
    }
}

private extension View {
    func authField() -> some View {
        self.font(ArgusStyle.body()).padding(16)
            .frame(minHeight: 52)
            .background(ArgusStyle.surface, in: RoundedRectangle(cornerRadius: 18))
    }
}
