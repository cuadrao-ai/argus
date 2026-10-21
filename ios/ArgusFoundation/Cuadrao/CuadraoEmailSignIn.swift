import SwiftUI

/// Disconnected visual proposal. Typed values never leave this view hierarchy.
struct CuadraoEmailSignIn: View {
    let spanish: Bool
    @State private var email: String
    @State private var password: String
    @State private var visible = false
    @State private var emailEdited = false
    @State private var state: StateKind
    @State private var recovery = false
    @State private var previewComplete = false
    @FocusState private var focus: Field?
    private enum Field: Hashable { case email, password, visiblePassword }
    private enum StateKind: Equatable { case idle, loading, rejected, offline }

    enum Fixture: String {
        case empty, filled, rejected, offline
        static var launch: Fixture {
            let argument = ProcessInfo.processInfo.arguments.first { $0.hasPrefix("--signin-state=") }
            return argument.flatMap { Fixture(rawValue: String($0.dropFirst("--signin-state=".count))) } ?? .empty
        }
    }

    init(spanish: Bool, initialEmail: String = "", fixture: Fixture = .launch) {
        self.spanish = spanish
        _email = State(initialValue: initialEmail.isEmpty && fixture != .empty ? "alex@example.com" : initialEmail)
        _password = State(initialValue: fixture == .empty ? "" : "Cuadrao-preview")
        _state = State(initialValue: fixture == .rejected ? .rejected : fixture == .offline ? .offline : .idle)
    }

    private var ready: Bool { PreviewEmail.isValid(email) && !password.isEmpty }
    private var invalidEmail: Bool { emailEdited && !email.isEmpty && !PreviewEmail.isValid(email) && focus != .email }
    private var passwordFocused: Bool { focus == .password || focus == .visiblePassword }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 32) {
                RegistrationHeading(title: CuadraoCopy.text("copy.connectedCuadraoAuth.535b037434", spanish: spanish),
                                    detail: CuadraoCopy.text("copy.connectedCuadraoAuth.9ff95daec1", spanish: spanish))
                VStack(alignment: .leading, spacing: 24) {
                    emailInput
                    passwordInput
                }
                if state == .rejected {
                    RegistrationNotice(symbol: "exclamationmark.circle",
                        title: CuadraoCopy.text("copy.nativeProviderSignIn.7fe06b0d57", spanish: spanish),
                        detail: CuadraoCopy.text("copy.connectedCuadraoAuth.993baa086c", spanish: spanish))
                } else if state == .offline {
                    RegistrationNotice(title: CuadraoCopy.text("copy.connectedCuadraoAuth.a97f4e5c01", spanish: spanish),
                        detail: CuadraoCopy.text("copy.connectedCuadraoAuth.fe4b7ee370", spanish: spanish))
                }
            }
            .padding(.horizontal, 28).padding(.vertical, 24)
        }
        .scrollDismissesKeyboard(.interactively)
        .safeAreaInset(edge: .bottom, spacing: 0) {
            RegistrationButton(title: state == .loading ? (CuadraoCopy.text("copy.connectedCuadraoAuth.2117a94ad6", spanish: spanish))
                               : state == .offline ? (CuadraoCopy.text("copy.connectedCuadraoAuth.ada77fc089", spanish: spanish))
                               : (CuadraoCopy.text("copy.connectedCuadraoAuth.99024c1d78", spanish: spanish)), busy: state == .loading, enabled: ready) {
                focus = nil
                state = .loading
            }
            .accessibilityIdentifier("cuadrao.signin.submit")
            .padding(.horizontal, 28).padding(.top, 16).padding(.bottom, 20)
            .background(WelcomePalette.background)
        }
        .background(WelcomePalette.background.ignoresSafeArea())
        .foregroundStyle(WelcomePalette.ink)
        .navigationTitle("").navigationBarTitleDisplayMode(.inline)
        .toolbar(.visible, for: .navigationBar)
        .onChange(of: focus) { old, _ in if old == .email { emailEdited = true } }
        .onChange(of: email) { _, _ in clearRejection() }
        .onChange(of: password) { _, _ in clearRejection() }
        .sheet(isPresented: $recovery) {
            NavigationStack { CuadraoPasswordRecovery(spanish: spanish, email: $email) }
                .tint(WelcomePalette.pine)
        }
        .task(id: state) {
            guard state == .loading else { return }
            do { try await Task.sleep(for: .milliseconds(800)) } catch { return }
            guard !Task.isCancelled else { return }
            state = .idle
            previewComplete = true
        }
        .alert(CuadraoCopy.text("copy.cuadraoEmailSignIn.b111e08d45", spanish: spanish), isPresented: $previewComplete) {
            Button(CuadraoCopy.text("copy.cuadraoAccountCanvas.43385c465a", spanish: spanish), role: .cancel) {}
        } message: {
            Text(CuadraoCopy.text("copy.cuadraoEmailSignIn.a4b5b862c1", spanish: spanish))
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
                .modifier(RegistrationField(focused: focus == .email, invalid: invalidEmail))
                .disabled(state == .loading)
                .accessibilityLabel(CuadraoCopy.text("copy.connectedCuadraoAuth.4e184d5fb9", spanish: spanish))
                .accessibilityIdentifier("cuadrao.signin.email")
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
                .onSubmit { if ready { focus = nil; state = .loading } }
                .accessibilityLabel(CuadraoCopy.text("copy.connectedCuadraoAuth.e355fe3205", spanish: spanish))
                .accessibilityIdentifier("cuadrao.signin.password")
                Button {
                    let wasFocused = passwordFocused
                    visible.toggle()
                    if wasFocused { focus = visible ? .visiblePassword : .password }
                } label: {
                    Image(systemName: visible ? "eye.slash" : "eye")
                        .foregroundStyle(.secondary).frame(width: 44, height: 44).contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel(visible ? (CuadraoCopy.text("copy.cuadraoEmailRegistration.7b5b088b70", spanish: spanish))
                                    : (CuadraoCopy.text("copy.cuadraoEmailRegistration.45cf1d96bc", spanish: spanish)))
            }
            .modifier(RegistrationField(focused: passwordFocused)).disabled(state == .loading)
            Button(CuadraoCopy.text("copy.connectedCuadraoAuth.ec29b296f1", spanish: spanish)) {
                focus = nil
                recovery = true
            }
            .font(.subheadline.weight(.medium)).foregroundStyle(WelcomePalette.pine)
            .frame(minHeight: 44).disabled(state == .loading)
            .accessibilityIdentifier("cuadrao.signin.recover")
        }
    }

    private func clearRejection() { if state == .rejected { state = .idle } }
}

#Preview("Sign in · Empty") { NavigationStack { CuadraoEmailSignIn(spanish: true, fixture: .empty) } }
#Preview("Sign in · Rejected") { NavigationStack { CuadraoEmailSignIn(spanish: true, fixture: .rejected) } }
#Preview("Sign in · Offline") { NavigationStack { CuadraoEmailSignIn(spanish: true, fixture: .offline) } }
#Preview("Sign in · English") { NavigationStack { CuadraoEmailSignIn(spanish: false, fixture: .filled) } }
