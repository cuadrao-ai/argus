import SwiftUI

/// Connected welcome and email auth with Cuadrao chrome. Apple and Google appear only when
/// their native sign-in switches are on (ConnectedProviderButtons).
struct ConnectedCuadraoAuthFlow: View {
    @EnvironmentObject private var auth: ProfileAuthModel
    @Environment(\.locale) private var locale
    @Environment(\.cuadraoGuestWelcome) private var guestWelcome

    private var spanish: Bool { CuadraoCopy.isSpanish() }

    /// After an account has signed in here, the signed-out screen is the login form alone.
    @ViewBuilder private var signedOutRoot: some View {
        if let guestWelcome, case .loginOnly(let line) = guestWelcome.shape {
            ConnectedCreateAccount(spanish: spanish, signingIn: true)
                .safeAreaInset(edge: .bottom, spacing: 0) {
                    if line { GuestOpenLine(spanish: spanish, open: guestWelcome.open) }
                }
        } else {
            welcome.toolbar(.hidden, for: .navigationBar)
        }
    }

    var body: some View {
        NavigationStack {
            Group {
                if auth.state == .configurationInvalid {
                    authNotice(title: CuadraoCopy.text("copy.connectedCuadraoAuth.5275fc6fe9", spanish: spanish),
                               detail: String(localized: "auth.error.configuration"))
                } else if auth.state == .pendingSignOut {
                    pendingSignOut
                } else if auth.state == .credentialValidationRequired || auth.state == .reauthenticationRequired {
                    validationRequired
                } else if auth.state == .unsupportedAnonymous {
                    authNotice(title: CuadraoCopy.text("copy.connectedCuadraoAuth.3f57cb9f7c", spanish: spanish),
                               detail: String(localized: "auth.error.anonymous"))
                } else if let deletion = auth.deletion {
                    ConnectedDeletionOutcome(model: deletion, unresolved: auth.state == .accountDeletionUncertain) {
                        signedOutRoot
                    }
                } else {
                    signedOutRoot
                }
            }
        }
        // Cover pushed email forms when signup requires confirmation (root swap alone can leave the stack).
        .fullScreenCover(isPresented: Binding(
            get: { auth.confirmationRequired },
            set: { if !$0 { auth.returnToSignIn() } }
        )) {
            ConnectedEmailConfirmation(spanish: spanish, email: auth.profile?.email ?? "")
                .environmentObject(auth)
        }
        .tint(WelcomePalette.pine)
        .foregroundStyle(WelcomePalette.ink)
        .background(WelcomePalette.background.ignoresSafeArea())
    }

    private var welcome: some View {
        GeometryReader { geometry in
            ScrollView {
                VStack(spacing: 0) {
                    Spacer(minLength: 32)
                    CuadraoWelcomeLockup()
                    Spacer(minLength: 40)
                    VStack(spacing: 12) {
                        NavigationLink {
                            ConnectedCreateAccount(spanish: spanish)
                        } label: {
                            Text(CuadraoCopy.text("copy.connectedCuadraoAuth.87ab2b1835", spanish: spanish))
                                .font(.system(.body, weight: .semibold))
                                .multilineTextAlignment(.center)
                                .padding(.vertical, 14)
                                .frame(maxWidth: .infinity, minHeight: 56)
                                .foregroundStyle(WelcomePalette.onAccent)
                                .background(WelcomePalette.pine, in: RoundedRectangle(cornerRadius: 16))
                        }.buttonStyle(.plain)
                        .accessibilityIdentifier("cuadrao.welcome.signup")
                        NavigationLink {
                            ConnectedCreateAccount(spanish: spanish, signingIn: true)
                        } label: {
                            Text(CuadraoCopy.text("copy.connectedCuadraoAuth.99024c1d78", spanish: spanish))
                                .font(.system(.body, weight: .semibold))
                                .multilineTextAlignment(.center)
                                .padding(.vertical, 14)
                                .frame(maxWidth: .infinity, minHeight: 56)
                                .overlay {
                                    RoundedRectangle(cornerRadius: 16)
                                        .stroke(WelcomePalette.border, lineWidth: 1)
                                }
                                .contentShape(Rectangle())
                        }.buttonStyle(.plain)
                        .accessibilityIdentifier("cuadrao.welcome.signin")
                        GuestWelcomeAction(spanish: spanish)
                    }.padding(.bottom, 28)
                }
                .padding(.horizontal, 28)
                .frame(minHeight: geometry.size.height, alignment: .topLeading)
            }.scrollIndicators(.hidden)
        }
        .background(WelcomePalette.brandPaper.ignoresSafeArea())
    }

    private var validationRequired: some View {
        VStack(alignment: .leading, spacing: 20) {
            RegistrationHeading(title: String(localized: "auth.apple.validation.title"),
                                detail: String(localized: auth.state == .reauthenticationRequired ? "auth.apple.signInAgain.detail" : "auth.apple.validation.detail"))
            if auth.busy { ProgressView("auth.working") }
            Button(auth.state == .reauthenticationRequired ? "auth.apple.signInAgain.action" : "auth.retry") {
                Task { if auth.state == .reauthenticationRequired { await auth.signOut() } else { await auth.restore() } }
            }
            .buttonStyle(PillButtonStyle()).disabled(auth.busy)
            .accessibilityIdentifier("auth.validation.retry")
            if auth.state == .credentialValidationRequired {
                Button("auth.signOut") { Task { await auth.signOut() } }
                    .buttonStyle(PillButtonStyle(primary: false)).disabled(auth.busy)
                    .accessibilityIdentifier("auth.signOut")
            }
            if let key = auth.errorKey { Text(LocalizedStringKey(key)).foregroundStyle(.secondary) }
            Spacer()
        }
        .padding(28)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    }

    private var pendingSignOut: some View {
        VStack(alignment: .leading, spacing: 20) {
            RegistrationHeading(title: CuadraoCopy.text("copy.connectedCuadraoAuth.81547b0a2d", spanish: spanish),
                                detail: String(localized: "auth.signOut.pending"))
            if auth.busy { ProgressView("auth.working") }
            Button("auth.signOut.retry") { Task { await auth.retryPendingSignOut() } }
                .buttonStyle(PillButtonStyle())
                .disabled(auth.busy)
                .accessibilityIdentifier("auth.retry")
            if let key = auth.errorKey {
                Text(LocalizedStringKey(key)).foregroundStyle(.secondary)
            }
            Spacer()
        }
        .padding(28)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .background(WelcomePalette.background.ignoresSafeArea())
    }

    private func authNotice(title: String, detail: String) -> some View {
        VStack(alignment: .leading, spacing: 20) {
            RegistrationHeading(title: title, detail: detail)
            Spacer()
        }
        .padding(28)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .background(WelcomePalette.background.ignoresSafeArea())
    }
}

struct ConnectedCreateAccount: View {
    let spanish: Bool
    @State private var signingIn: Bool
    @EnvironmentObject private var auth: ProfileAuthModel

    init(spanish: Bool, signingIn: Bool = false) {
        self.spanish = spanish
        _signingIn = State(initialValue: signingIn)
    }

    var body: some View {
        if signingIn {
            form
        } else {
            AgeRangeObservationView(observation: auth.ageRangeObservation) { form }
        }
    }

    private var form: some View {
        GeometryReader { geometry in
            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    RegistrationHeading(
                        title: signingIn ? (CuadraoCopy.text("copy.connectedCuadraoAuth.4e250a863e", spanish: spanish))
                            : (CuadraoCopy.text("copy.connectedCuadraoAuth.b12eabc5ce", spanish: spanish)),
                        detail: signingIn ? (CuadraoCopy.text("copy.connectedCuadraoAuth.adf63b5a8b", spanish: spanish))
                            : (CuadraoCopy.text("copy.connectedCuadraoAuth.a20acd8081", spanish: spanish)))
                    Spacer(minLength: 64)
                    ConnectedProviderButtons(spanish: spanish)
                    NavigationLink {
                        if signingIn {
                            ConnectedEmailSignIn(spanish: spanish)
                        } else {
                            ConnectedEmailRegistration(spanish: spanish)
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
                    if !signingIn {
                        CuadraoSignupAcceptance(spanish: spanish)
                    }
                    Button { signingIn.toggle() } label: {
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
    }
}

private enum ConnectedAuthSurface: Equatable {
    case idle, loading, rejected, offline
}

struct ConnectedEmailSignIn: View {
    let spanish: Bool
    @EnvironmentObject private var auth: ProfileAuthModel
    @Environment(\.locale) private var locale
    @Environment(\.openURL) private var openURL
    @State private var email = ""
    @State private var password = ""
    @State private var visible = false
    @State private var emailEdited = false
    @State private var surface: ConnectedAuthSurface = .idle
    @State private var challenge: ConnectedCaptchaRequest?
    @FocusState private var focus: Field?
    private enum Field: Hashable { case email, password, visiblePassword }

    private var ready: Bool { PreviewEmail.isValid(email) && !password.isEmpty }
    private var invalidEmail: Bool { emailEdited && !email.isEmpty && !PreviewEmail.isValid(email) && focus != .email }
    private var passwordFocused: Bool { focus == .password || focus == .visiblePassword }
    private var language: String { CuadraoCopy.isSpanish() ? "es-419" : "en" }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 32) {
                RegistrationHeading(title: CuadraoCopy.text("copy.connectedCuadraoAuth.535b037434", spanish: spanish),
                                    detail: CuadraoCopy.text("copy.connectedCuadraoAuth.9ff95daec1", spanish: spanish))
                VStack(alignment: .leading, spacing: 24) {
                    emailInput
                    passwordInput
                }
                if surface == .rejected {
                    RegistrationNotice(symbol: "exclamationmark.circle",
                        title: CuadraoCopy.text("copy.nativeProviderSignIn.7fe06b0d57", spanish: spanish),
                        detail: CuadraoCopy.text("copy.connectedCuadraoAuth.993baa086c", spanish: spanish))
                } else if surface == .offline {
                    RegistrationNotice(title: CuadraoCopy.text("copy.connectedCuadraoAuth.a97f4e5c01", spanish: spanish),
                        detail: CuadraoCopy.text("copy.connectedCuadraoAuth.fe4b7ee370", spanish: spanish))
                }
            }
            .padding(.horizontal, 28).padding(.vertical, 24)
        }
        .scrollDismissesKeyboard(.interactively)
        .safeAreaInset(edge: .bottom, spacing: 0) {
            RegistrationButton(title: surface == .loading ? (CuadraoCopy.text("copy.connectedCuadraoAuth.2117a94ad6", spanish: spanish))
                               : surface == .offline ? (CuadraoCopy.text("copy.connectedCuadraoAuth.ada77fc089", spanish: spanish))
                               : (CuadraoCopy.text("copy.connectedCuadraoAuth.99024c1d78", spanish: spanish)),
                               busy: surface == .loading, enabled: ready) {
                focus = nil
                beginChallenge()
            }
            .accessibilityLabel(Text("auth.signIn"))
            .accessibilityIdentifier("auth.submit")
            .padding(.horizontal, 28).padding(.top, 16).padding(.bottom, 20)
            .background(WelcomePalette.background)
        }
        .background(WelcomePalette.background.ignoresSafeArea())
        .foregroundStyle(WelcomePalette.ink)
        .navigationTitle("").navigationBarTitleDisplayMode(.inline)
        .toolbar(.visible, for: .navigationBar)
        .onChange(of: focus) { old, _ in if old == .email { emailEdited = true } }
        .onChange(of: email) { _, _ in if surface == .rejected { surface = .idle } }
        .onChange(of: password) { _, _ in if surface == .rejected { surface = .idle } }
        .onChange(of: auth.busy) { _, busy in
            if busy { surface = .loading }
            else if !auth.confirmationRequired { mapAuthError() }
        }
        .onChange(of: auth.errorKey) { _, _ in if !auth.busy { mapAuthError() } }
        .sheet(item: $challenge) { request in
            CaptchaChallengeView(sourceURL: request.url) { result in
                challenge = nil
                switch result {
                case .failure(.cancelled): surface = .idle
                case .failure(.unavailable):
                    auth.presentationError("auth.captcha.error")
                    surface = .offline
                case .success(let token):
                    let submittedPassword = password
                    let submittedEmail = email.trimmingCharacters(in: .whitespacesAndNewlines)
                    password = ""
                    surface = .loading
                    Task {
                        await auth.authenticate(email: submittedEmail, password: submittedPassword,
                                                captchaToken: token, signup: false,
                                                language: language, displayName: "")
                        mapAuthError()
                    }
                }
            }
        }
    }

    private var emailInput: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(CuadraoCopy.text("copy.connectedCuadraoAuth.4e184d5fb9", spanish: spanish)).font(.subheadline.weight(.medium))
            TextField(CuadraoCopy.text("copy.connectedCuadraoAuth.f99371c667", spanish: spanish), text: $email)
                .textContentType(.username).keyboardType(.emailAddress)
                .textInputAutocapitalization(.never).autocorrectionDisabled()
                .focused($focus, equals: .email).submitLabel(.next)
                .onSubmit { focus = visible ? .visiblePassword : .password }
                .frame(minHeight: 44)
                .contentShape(Rectangle())
                .modifier(RegistrationField(focused: focus == .email, invalid: invalidEmail))
                .disabled(surface == .loading)
                .accessibilityLabel(Text("auth.email"))
                .accessibilityIdentifier("auth.email")
            if invalidEmail {
                Label(CuadraoCopy.text("copy.connectedCuadraoAuth.f72b1dead3", spanish: spanish), systemImage: "exclamationmark.circle")
                    .font(.footnote).foregroundStyle(.red)
            }
        }
    }

    private var passwordInput: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(CuadraoCopy.text("copy.connectedCuadraoAuth.e355fe3205", spanish: spanish)).font(.subheadline.weight(.medium))
            HStack(spacing: 0) {
                Group {
                    if visible {
                        TextField(CuadraoCopy.text("copy.connectedCuadraoAuth.9d9941b718", spanish: spanish), text: $password)
                            .focused($focus, equals: .visiblePassword)
                    } else {
                        SecureField(CuadraoCopy.text("copy.connectedCuadraoAuth.9d9941b718", spanish: spanish), text: $password)
                            .focused($focus, equals: .password)
                    }
                }
                .textContentType(.password).textInputAutocapitalization(.never).autocorrectionDisabled()
                .submitLabel(.go)
                .onSubmit { if ready { focus = nil; beginChallenge() } }
                .frame(minHeight: 44)
                .contentShape(Rectangle())
                .accessibilityLabel(Text("auth.password"))
                .accessibilityIdentifier("auth.password")
                Button {
                    let wasFocused = passwordFocused
                    visible.toggle()
                    if wasFocused { focus = visible ? .visiblePassword : .password }
                } label: {
                    Image(systemName: visible ? "eye.slash" : "eye")
                        .foregroundStyle(.secondary).frame(width: 44, height: 44).contentShape(Rectangle())
                }
                .buttonStyle(.plain)
            }
            .modifier(RegistrationField(focused: passwordFocused)).disabled(surface == .loading)
            Button(CuadraoCopy.text("copy.connectedCuadraoAuth.ec29b296f1", spanish: spanish)) {
                focus = nil
                recover()
            }
            .font(.subheadline.weight(.medium)).foregroundStyle(WelcomePalette.pine)
            .frame(minHeight: 44).contentShape(Rectangle()).disabled(surface == .loading)
            .accessibilityLabel(Text("auth.forgotPassword"))
            .accessibilityIdentifier("auth.forgotPassword")
        }
    }

    private func beginChallenge() {
        guard let configuration = auth.configuration else {
            auth.presentationError("auth.error.configuration")
            surface = .offline
            return
        }
        surface = .idle
        challenge = ConnectedCaptchaRequest(url: configuration.captchaURL)
    }

    private func recover() {
        guard let url = auth.configuration?.recoveryURL else {
            auth.presentationError("auth.recovery.failed")
            return
        }
        openURL(url) { accepted in
            if !accepted { auth.presentationError("auth.recovery.failed") }
        }
    }

    private func mapAuthError() {
        if auth.state == .authenticated || auth.confirmationRequired {
            surface = .idle
            return
        }
        switch auth.errorKey {
        case "auth.error.unauthorized", "auth.error.rejected": surface = .rejected
        case "auth.error.unavailable", "auth.error.rateLimit", "auth.captcha.error", "auth.recovery.failed":
            surface = .offline
        case nil where !auth.busy: surface = .idle
        default:
            if auth.errorKey != nil { surface = .offline }
        }
    }
}

struct ConnectedEmailRegistration: View {
    let spanish: Bool
    @EnvironmentObject private var auth: ProfileAuthModel
    @Environment(\.locale) private var locale
    @State private var email = ""
    @State private var password = ""
    @State private var passwordVisible = false
    @State private var emailEdited = false
    @State private var surface: ConnectedAuthSurface = .idle
    @State private var challenge: ConnectedCaptchaRequest?
    @FocusState private var focus: Field?
    private enum Field: Hashable { case email, password, visiblePassword }

    private var validEmail: Bool { PreviewEmail.isValid(email) }
    private var emailError: Bool { emailEdited && !email.isEmpty && !validEmail && focus != .email }
    private var passwordFocused: Bool { focus == .password || focus == .visiblePassword }
    private var canSubmit: Bool { validEmail && password.count >= 8 }
    private var language: String { CuadraoCopy.isSpanish() ? "es-419" : "en" }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 32) {
                RegistrationHeading(
                    title: CuadraoCopy.text("copy.connectedCuadraoAuth.0a7068bf7e", spanish: spanish),
                    detail: CuadraoCopy.text("copy.connectedCuadraoAuth.4246ac82f7", spanish: spanish))
                VStack(alignment: .leading, spacing: 24) {
                    emailField
                    passwordField
                }
                if surface == .offline {
                    RegistrationNotice(
                        title: CuadraoCopy.text("copy.connectedCuadraoAuth.a97f4e5c01", spanish: spanish),
                        detail: CuadraoCopy.text("copy.connectedCuadraoAuth.fe4b7ee370", spanish: spanish))
                } else if surface == .rejected {
                    RegistrationNotice(symbol: "exclamationmark.circle",
                        title: CuadraoCopy.text("copy.connectedCuadraoAuth.17f005005e", spanish: spanish),
                        detail: CuadraoCopy.text("copy.connectedCuadraoAuth.4d61d56fd7", spanish: spanish))
                }
            }
            .padding(.horizontal, 28)
            .padding(.top, 24)
            .padding(.bottom, 24)
        }
        .scrollDismissesKeyboard(.interactively)
        .safeAreaInset(edge: .bottom, spacing: 0) {
            RegistrationButton(
                title: surface == .loading
                    ? (CuadraoCopy.text("copy.connectedCuadraoAuth.35d3f284c0", spanish: spanish))
                    : surface == .offline ? (CuadraoCopy.text("copy.connectedCuadraoAuth.ada77fc089", spanish: spanish))
                    : (CuadraoCopy.text("copy.connectedCuadraoAuth.87ab2b1835", spanish: spanish)),
                busy: surface == .loading, enabled: canSubmit) {
                    focus = nil
                    beginChallenge()
                }
                .accessibilityLabel(Text("auth.createAccount"))
                .accessibilityIdentifier("auth.submit")
                .padding(.horizontal, 28)
                .padding(.top, 16)
                .padding(.bottom, 20)
                .background(WelcomePalette.background)
        }
        .background(WelcomePalette.background.ignoresSafeArea())
        .foregroundStyle(WelcomePalette.ink)
        .navigationTitle("")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar(.visible, for: .navigationBar)
        .onChange(of: focus) { old, _ in if old == .email { emailEdited = true } }
        .onChange(of: auth.busy) { _, busy in
            if busy { surface = .loading }
            else if !auth.confirmationRequired { mapAuthError() }
        }
        .onChange(of: auth.errorKey) { _, _ in if !auth.busy { mapAuthError() } }
        .sheet(item: $challenge) { request in
            CaptchaChallengeView(sourceURL: request.url) { result in
                challenge = nil
                switch result {
                case .failure(.cancelled): surface = .idle
                case .failure(.unavailable):
                    auth.presentationError("auth.captcha.error")
                    surface = .offline
                case .success(let token):
                    let submittedPassword = password
                    let submittedEmail = email.trimmingCharacters(in: .whitespacesAndNewlines)
                    password = ""
                    surface = .loading
                    Task {
                        await auth.authenticate(email: submittedEmail, password: submittedPassword,
                                                captchaToken: token, signup: true,
                                                language: language, displayName: "")
                        mapAuthError()
                    }
                }
            }
        }
    }

    private var emailField: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(CuadraoCopy.text("copy.connectedCuadraoAuth.4e184d5fb9", spanish: spanish)).font(.subheadline.weight(.medium))
            TextField(CuadraoCopy.text("copy.connectedCuadraoAuth.f99371c667", spanish: spanish), text: $email)
                .keyboardType(.emailAddress)
                .textContentType(.emailAddress)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
                .focused($focus, equals: .email)
                .submitLabel(.next)
                .onSubmit { focus = passwordVisible ? .visiblePassword : .password }
                .frame(minHeight: 44)
                .contentShape(Rectangle())
                .modifier(RegistrationField(focused: focus == .email, invalid: emailError))
                .disabled(surface == .loading)
                .accessibilityLabel(Text("auth.email"))
                .accessibilityIdentifier("auth.email")
            if emailError {
                Label(CuadraoCopy.text("copy.connectedCuadraoAuth.1176476358", spanish: spanish), systemImage: "exclamationmark.circle")
                    .font(.footnote).foregroundStyle(.red)
            }
        }
    }

    private var passwordField: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(CuadraoCopy.text("copy.connectedCuadraoAuth.e355fe3205", spanish: spanish)).font(.subheadline.weight(.medium))
            HStack(spacing: 0) {
                Group {
                    if passwordVisible {
                        TextField(CuadraoCopy.text("copy.connectedCuadraoAuth.88359f60f2", spanish: spanish), text: $password)
                            .focused($focus, equals: .visiblePassword)
                    } else {
                        SecureField(CuadraoCopy.text("copy.connectedCuadraoAuth.88359f60f2", spanish: spanish), text: $password)
                            .focused($focus, equals: .password)
                    }
                }
                .textContentType(.newPassword)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
                .submitLabel(.done)
                .onSubmit { focus = nil }
                .frame(minHeight: 44)
                .contentShape(Rectangle())
                .accessibilityLabel(Text("auth.password"))
                .accessibilityIdentifier("auth.password")
                Button {
                    let wasFocused = passwordFocused
                    passwordVisible.toggle()
                    if wasFocused { focus = passwordVisible ? .visiblePassword : .password }
                } label: {
                    Image(systemName: passwordVisible ? "eye.slash" : "eye")
                        .foregroundStyle(.secondary)
                        .frame(width: 44, height: 44)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
            }
            .modifier(RegistrationField(focused: passwordFocused))
            .disabled(surface == .loading)
            Label(CuadraoCopy.text("copy.connectedCuadraoAuth.3abe4914e5", spanish: spanish),
                  systemImage: password.count >= 8 ? "checkmark.circle.fill" : "circle")
                .font(.footnote)
                .foregroundStyle(password.count >= 8 ? WelcomePalette.pine : Color.secondary)
                .accessibilityLabel(Text("auth.password.requirement"))
        }
    }

    private func beginChallenge() {
        guard let configuration = auth.configuration else {
            auth.presentationError("auth.error.configuration")
            surface = .offline
            return
        }
        surface = .idle
        challenge = ConnectedCaptchaRequest(url: configuration.captchaURL)
    }

    private func mapAuthError() {
        if auth.confirmationRequired || auth.state == .authenticated {
            surface = .idle
            return
        }
        switch auth.errorKey {
        case "auth.error.unauthorized", "auth.error.rejected": surface = .rejected
        case "auth.error.unavailable", "auth.error.rateLimit", "auth.captcha.error": surface = .offline
        case nil where !auth.busy: surface = .idle
        default:
            if auth.errorKey != nil { surface = .offline }
        }
    }
}

struct ConnectedEmailConfirmation: View {
    let spanish: Bool
    let email: String
    @EnvironmentObject private var auth: ProfileAuthModel

    var body: some View {
        GeometryReader { geometry in
            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    Image(systemName: "envelope.badge.shield.half.filled")
                        .font(.system(size: 32, weight: .light))
                        .foregroundStyle(WelcomePalette.pine)
                        .frame(width: 72, height: 72)
                        .background(WelcomePalette.sage, in: RoundedRectangle(cornerRadius: 22))
                        .accessibilityHidden(true)
                        .padding(.bottom, 28)
                    RegistrationHeading(
                        title: CuadraoCopy.text("copy.connectedCuadraoAuth.2096f1a523", spanish: spanish),
                        detail: CuadraoCopy.text("copy.connectedCuadraoAuth.1132cc3fad", spanish: spanish))
                    Text(email.isEmpty ? String(localized: "auth.confirmation.detail") : email)
                        .font(.body.weight(.semibold))
                        .textSelection(.enabled)
                        .padding(.top, 10)
                        .accessibilityIdentifier("auth.confirmation")
                    Button(CuadraoCopy.text("copy.connectedCuadraoAuth.2883c17995", spanish: spanish)) { auth.returnToSignIn() }
                        .font(.subheadline.weight(.medium))
                        .foregroundStyle(WelcomePalette.pine)
                        .frame(minHeight: 44)
                        .padding(.top, 6)
                        .accessibilityIdentifier("auth.return.signIn")
                    Spacer(minLength: 40)
                    Text(CuadraoCopy.text("copy.connectedCuadraoAuth.ab25824af2", spanish: spanish))
                        .font(.body).foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                        .padding(.bottom, 24)
                    NavigationLink {
                        ConnectedEmailSignIn(spanish: spanish)
                    } label: {
                        Text(CuadraoCopy.text("copy.connectedCuadraoAuth.93dde646b9", spanish: spanish))
                            .font(.body.weight(.semibold))
                            .frame(maxWidth: .infinity, minHeight: 56)
                            .foregroundStyle(WelcomePalette.onAccent)
                            .background(WelcomePalette.pine, in: RoundedRectangle(cornerRadius: 16))
                    }.buttonStyle(.plain)
                }
                .padding(.horizontal, 28)
                .padding(.top, 24)
                .padding(.bottom, 20)
                .frame(minHeight: geometry.size.height, alignment: .topLeading)
            }
        }
        .background(WelcomePalette.background.ignoresSafeArea())
        .foregroundStyle(WelcomePalette.ink)
        .navigationTitle("")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar(.visible, for: .navigationBar)
    }
}

private struct ConnectedCaptchaRequest: Identifiable {
    let id = UUID()
    let url: URL
}
