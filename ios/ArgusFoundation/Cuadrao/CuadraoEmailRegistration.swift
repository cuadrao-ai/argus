import SwiftUI

/// Local visual states only. No account service, persistence, or outgoing requests.
struct CuadraoEmailRegistration: View {
    let spanish: Bool
    @State private var email: String
    @State private var password: String
    @State private var passwordVisible = false
    @State private var emailEdited = false
    @State private var submission: Submission
    @State private var showConfirmation = false
    @FocusState private var focus: Field?

    private enum Field: Hashable { case email, password, visiblePassword }
    private enum Submission: Equatable { case idle, submitting, offline }

    enum Fixture: String {
        case empty, filled, invalid, offline, loading

        static var launch: Fixture {
            let value = ProcessInfo.processInfo.arguments.first { $0.hasPrefix("--registration-state=") }
            return value.flatMap { Fixture(rawValue: String($0.dropFirst("--registration-state=".count))) } ?? .empty
        }
    }

    init(spanish: Bool, fixture: Fixture = .launch) {
        self.spanish = spanish
        _email = State(initialValue: fixture == .empty ? "" : fixture == .invalid ? "alex@" : "alex@example.com")
        _password = State(initialValue: fixture == .empty || fixture == .invalid ? "" : "Cuadrao-preview")
        _emailEdited = State(initialValue: fixture == .invalid)
        _submission = State(initialValue: fixture == .offline ? .offline : fixture == .loading ? .submitting : .idle)
    }

    private var normalizedEmail: String { PreviewEmail.normalized(email) }
    private var validEmail: Bool { PreviewEmail.isValid(email) }
    private var emailError: Bool { emailEdited && !email.isEmpty && !validEmail && focus != .email }
    private var passwordFocused: Bool { focus == .password || focus == .visiblePassword }
    private var canSubmit: Bool { validEmail && password.count >= 8 }

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
                if submission == .offline {
                    RegistrationNotice(
                        title: CuadraoCopy.text("copy.connectedCuadraoAuth.a97f4e5c01", spanish: spanish),
                        detail: CuadraoCopy.text("copy.connectedCuadraoAuth.fe4b7ee370", spanish: spanish))
                }
            }
            .padding(.horizontal, 28)
            .padding(.top, 24)
            .padding(.bottom, 24)
        }
        .scrollDismissesKeyboard(.interactively)
        .safeAreaInset(edge: .bottom, spacing: 0) {
            RegistrationButton(
                title: submission == .submitting
                    ? (CuadraoCopy.text("copy.connectedCuadraoAuth.35d3f284c0", spanish: spanish))
                    : submission == .offline ? (CuadraoCopy.text("copy.connectedCuadraoAuth.ada77fc089", spanish: spanish))
                    : (CuadraoCopy.text("copy.connectedCuadraoAuth.87ab2b1835", spanish: spanish)),
                busy: submission == .submitting, enabled: canSubmit) {
                    focus = nil
                    submission = .submitting
                }
                .accessibilityIdentifier("cuadrao.signup.submit")
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
        .navigationDestination(isPresented: $showConfirmation) {
            CuadraoEmailConfirmation(spanish: spanish, email: normalizedEmail)
        }
        .onChange(of: focus) { old, _ in
            if old == .email { emailEdited = true }
        }
        .task(id: submission) {
            guard submission == .submitting else { return }
            do { try await Task.sleep(for: .milliseconds(900)) } catch { return }
            guard !Task.isCancelled else { return }
            submission = .idle
            showConfirmation = true
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
                .modifier(RegistrationField(focused: focus == .email, invalid: emailError))
                .disabled(submission == .submitting)
                .accessibilityLabel(CuadraoCopy.text("copy.connectedCuadraoAuth.4e184d5fb9", spanish: spanish))
                .accessibilityIdentifier("cuadrao.signup.emailField")
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
                .accessibilityLabel(CuadraoCopy.text("copy.connectedCuadraoAuth.e355fe3205", spanish: spanish))
                .accessibilityIdentifier("cuadrao.signup.password")
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
                .accessibilityLabel(passwordVisible
                    ? (CuadraoCopy.text("copy.cuadraoEmailRegistration.7b5b088b70", spanish: spanish))
                    : (CuadraoCopy.text("copy.cuadraoEmailRegistration.45cf1d96bc", spanish: spanish)))
            }
            .modifier(RegistrationField(focused: passwordFocused))
            .disabled(submission == .submitting)
            Label(CuadraoCopy.text("copy.connectedCuadraoAuth.3abe4914e5", spanish: spanish),
                  systemImage: password.count >= 8 ? "checkmark.circle.fill" : "circle")
                .font(.footnote)
                .foregroundStyle(password.count >= 8 ? WelcomePalette.pine : Color.secondary)
                .accessibilityLabel(password.count >= 8
                    ? (CuadraoCopy.text("copy.cuadraoEmailRegistration.c47ca0506d", spanish: spanish))
                    : (CuadraoCopy.text("copy.cuadraoEmailRegistration.fad5da569f", spanish: spanish)))
        }
    }
}

#Preview("Email · Empty") {
    NavigationStack { CuadraoEmailRegistration(spanish: true, fixture: .empty) }
}
#Preview("Email · Invalid") {
    NavigationStack { CuadraoEmailRegistration(spanish: true, fixture: .invalid) }
}
#Preview("Email · Recovery") {
    NavigationStack { CuadraoEmailRegistration(spanish: true, fixture: .offline) }
}
#Preview("Email · English") {
    NavigationStack { CuadraoEmailRegistration(spanish: false, fixture: .filled) }
}
