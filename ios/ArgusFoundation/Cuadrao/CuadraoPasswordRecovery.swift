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
                        RegistrationHeading(title: CuadraoCopy.text("copy.cuadraoPasswordRecovery.fc17bdd4b4", spanish: spanish),
                            detail: CuadraoCopy.text("copy.cuadraoPasswordRecovery.c44dd944d1", spanish: spanish))
                        VStack(alignment: .leading, spacing: 10) {
                            Text(CuadraoCopy.text("copy.connectedCuadraoAuth.4e184d5fb9", spanish: spanish)).font(.subheadline.weight(.medium))
                            TextField(CuadraoCopy.text("copy.connectedCuadraoAuth.f99371c667", spanish: spanish), text: $email)
                                .textContentType(.emailAddress).keyboardType(.emailAddress)
                                .textInputAutocapitalization(.never).autocorrectionDisabled()
                                .focused($focused).submitLabel(.send)
                                .onSubmit { send() }
                                .modifier(RegistrationField(focused: focused, invalid: invalid))
                                .disabled(state == .sending)
                                .accessibilityLabel(CuadraoCopy.text("copy.connectedCuadraoAuth.4e184d5fb9", spanish: spanish))
                                .accessibilityIdentifier("cuadrao.recovery.email")
                            if invalid {
                                Label(CuadraoCopy.text("copy.connectedCuadraoAuth.f72b1dead3", spanish: spanish), systemImage: "exclamationmark.circle")
                                    .font(.footnote).foregroundStyle(.red)
                            }
                        }
                        if state == .offline {
                            RegistrationNotice(title: CuadraoCopy.text("copy.connectedCuadraoAuth.a97f4e5c01", spanish: spanish),
                                detail: CuadraoCopy.text("copy.cuadraoPasswordRecovery.9c7cd3524c", spanish: spanish))
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
            CuadraoCancelToolbar(title: CuadraoCopy.text("copy.cuadraoAccountsCollection.f296f2cba3", spanish: spanish)) { dismiss() }
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
            RegistrationHeading(title: CuadraoCopy.text("copy.cuadraoPasswordRecovery.e7c08d7a55", spanish: spanish),
                detail: CuadraoCopy.text("copy.cuadraoPasswordRecovery.9dcfb22b24", spanish: spanish))
            Text(PreviewEmail.normalized(email)).font(.body.weight(.semibold))
                .textSelection(.enabled).padding(.top, 14)
            Button(CuadraoCopy.text("copy.connectedCuadraoAuth.2883c17995", spanish: spanish)) { state = .entry; showHelp = false }
                .font(.subheadline.weight(.medium)).frame(minHeight: 44)
                .foregroundStyle(WelcomePalette.pine).padding(.top, 6)
            Button(CuadraoCopy.text("copy.cuadraoEmailConfirmation.0036b29e79", spanish: spanish)) { showHelp.toggle() }
                .font(.subheadline).frame(minHeight: 44).padding(.top, 24)
            if showHelp {
                Text(CuadraoFirstRelease.showsSocialSignIn
                    ? (CuadraoCopy.text("copy.cuadraoPasswordRecovery.7e19949836", spanish: spanish))
                    : (CuadraoCopy.text("copy.cuadraoPasswordRecovery.ccf0b939a8", spanish: spanish)))
                    .font(.footnote).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
                    .padding(.top, 8)
            }
        }
    }

    private var buttonTitle: String {
        switch state {
        case .entry: CuadraoCopy.text("copy.cuadraoPasswordRecovery.75cee94b5e", spanish: spanish)
        case .sending: CuadraoCopy.text("copy.cuadraoPasswordRecovery.92664cc038", spanish: spanish)
        case .sent: CuadraoCopy.text("copy.cuadraoPasswordRecovery.544f420979", spanish: spanish)
        case .offline: CuadraoCopy.text("copy.connectedCuadraoAuth.ada77fc089", spanish: spanish)
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
