import SwiftUI

public struct ReleaseDeleteAccountView: View {
    public let consequences: ReleaseDeletionConsequences
    public let state: ReleaseDeletionState
    public let verification: ReleaseDeletionVerification
    public let onSubmit: (String) -> Void
    public let onRetry: () -> Void
    public let onComplete: () -> Void
    public let onResendCode: (() -> Void)?
    public let appleAuthorization: AnyView?
    @Environment(\.locale) private var locale
    @State private var showingVerification = false
    @State private var confirmation = ""
    @FocusState private var focused: Bool

    public init(consequences: ReleaseDeletionConsequences, state: ReleaseDeletionState,
                verification: ReleaseDeletionVerification = .typedDelete,
                onSubmit: @escaping (String) -> Void, onRetry: @escaping () -> Void,
                onComplete: @escaping () -> Void, onResendCode: (() -> Void)? = nil, appleAuthorization: AnyView? = nil) {
        self.consequences = consequences; self.state = state; self.verification = verification
        self.onSubmit = onSubmit; self.onRetry = onRetry; self.onComplete = onComplete
        self.onResendCode = onResendCode; self.appleAuthorization = appleAuthorization
        _showingVerification = State(initialValue: state == .verificationRejected || state == .verificationResending)
    }

    private var spanish: Bool { CuadraoCopy.isSpanish() }

    public var body: some View {
        List {
            switch state {
            case .ready, .verificationRejected, .verificationResending: review
            case .submitting, .pending:
                Section {
                    if state == .submitting {
                        ProgressView(CuadraoCopy.text("copy.releaseDeleteAccountView.2bdaef9df7", spanish: spanish))
                    } else {
                        Label(CuadraoCopy.text("copy.releaseDeleteAccountView.a30ecb6ca3", spanish: spanish), systemImage: "clock")
                        Text(CuadraoCopy.text("copy.releaseDeleteAccountView.3f8ab92e62", spanish: spanish))
                            .foregroundStyle(.secondary)
                            .accessibilityIdentifier("identity.delete.inProgress")
                        Button(CuadraoCopy.text("copy.releaseDeleteAccountView.bd6b05a681", spanish: spanish), action: onComplete)
                            .accessibilityIdentifier("identity.delete.pendingDone")
                    }
                }
            case .failed:
                Section {
                    Label(CuadraoCopy.text("copy.releaseDeleteAccountView.7c121271cd", spanish: spanish), systemImage: "exclamationmark.circle")
                    Text(CuadraoCopy.text("copy.releaseDeleteAccountView.23c67c0ebd", spanish: spanish))
                        .foregroundStyle(.secondary)
                    Button(CuadraoCopy.text("copy.releaseDeleteAccountView.e4bd371375", spanish: spanish), action: onRetry)
                        .accessibilityIdentifier("identity.delete.retry")
                }
            case .completed:
                Section {
                    Label(CuadraoCopy.text("copy.releaseDeleteAccountView.4eb1b70a64", spanish: spanish), systemImage: "checkmark.circle")
                    Text(CuadraoCopy.text("copy.releaseDeleteAccountView.70ec8fec0b", spanish: spanish))
                        .foregroundStyle(.secondary)
                    Button(CuadraoCopy.text("copy.releaseDeleteAccountView.bd6b05a681", spanish: spanish), action: onComplete)
                        .accessibilityIdentifier("identity.delete.complete")
                }
            case .uncertain(let canRetry):
                Section {
                    Label("auth.deletion.uncertain", systemImage: "exclamationmark.triangle")
                        .accessibilityIdentifier("identity.delete.uncertain")
                    if canRetry {
                        Button("auth.deletion.checkAgain", action: onRetry)
                            .accessibilityIdentifier("identity.delete.checkAgain")
                    } else {
                        Text("auth.deletion.uncertain.support").foregroundStyle(.secondary)
                            .accessibilityIdentifier("identity.delete.uncertainSupport")
                    }
                }
            case .appleAuthorizationRequired:
                Section {
                    Label("auth.deletion.apple", systemImage: "apple.logo")
                        .accessibilityIdentifier("identity.delete.apple")
                    if let appleAuthorization { appleAuthorization }
                }
            case .supportRequested:
                Section {
                    Label("auth.deletion.support.requested", systemImage: "envelope")
                        .accessibilityIdentifier("identity.delete.supportRequested")
                    Button(CuadraoCopy.text("copy.releaseDeleteAccountView.bd6b05a681", spanish: spanish), action: onComplete)
                        .accessibilityIdentifier("identity.delete.supportDone")
                }
            case .supportUnavailable:
                Section {
                    Label("auth.deletion.support.unavailable", systemImage: "exclamationmark.circle")
                        .accessibilityIdentifier("identity.delete.supportUnavailable")
                    Button(CuadraoCopy.text("copy.releaseDeleteAccountView.e4bd371375", spanish: spanish), action: onRetry)
                        .accessibilityIdentifier("identity.delete.supportRetry")
                }
            }
        }
        .font(CuadraoTypography.body)
        .tint(WelcomePalette.pine)
        .navigationTitle(CuadraoCopy.text("copy.releaseDeleteAccountView.a094025062", spanish: spanish))
        .navigationBarTitleDisplayMode(.inline)
        .interactiveDismissDisabled(state == .submitting || state == .pending)
        .accessibilityIdentifier("identity.delete.screen")
        .onChange(of: state) { _, _ in
            presentVerificationIfNeeded()
            if state == .completed { confirmation = "" }
        }
    }

    private var review: some View {
        Group {
            Section {
                Text(CuadraoCopy.text("copy.releaseDeleteAccountView.8f6cdc6f2f", spanish: spanish))
                    .font(CuadraoTypography.feature).accessibilityAddTraits(.isHeader)
                Text(CuadraoCopy.text("copy.releaseDeleteAccountView.ff723f2a17", spanish: spanish))
            }
            if !consequences.households.isEmpty || consequences.hasLockedHistory {
                Section(CuadraoCopy.text("copy.releaseDeleteAccountView.55abd9bccb", spanish: spanish)) {
                    ForEach(Array(consequences.households.enumerated()), id: \.offset) { _, household in
                        Text(householdConsequence(household))
                    }
                    if consequences.hasLockedHistory {
                        Text(CuadraoCopy.text("copy.releaseDeleteAccountView.2d51901272", spanish: spanish))
                    }
                }
            }
            if consequences.hasSharedPlans {
                Section(CuadraoCopy.text("copy.releaseDeleteAccountView.3f4adf217e", spanish: spanish)) {
                    Text(CuadraoCopy.text("copy.releaseDeleteAccountView.8244b5e893", spanish: spanish))
                        .accessibilityIdentifier("identity.delete.sharedConsequences")
                    Text(CuadraoCopy.text("copy.releaseDeleteAccountView.55e2dfc0f4", spanish: spanish))
                }
            }
            Section(CuadraoCopy.text("copy.releaseDeleteAccountView.2bd4cc492a", spanish: spanish)) {
                Text(CuadraoCopy.text("copy.releaseDeleteAccountView.51ab27ebc9", spanish: spanish))
                Text(CuadraoCopy.text("copy.releaseDeleteAccountView.53f1e453de", spanish: spanish))
            }
            if showingVerification {
                Section {
                    if state == .verificationRejected {
                        Label(verification == .code
                              ? CuadraoCopy.text("copy.releaseDeleteAccountView.00ba086a48", spanish: spanish)
                              : CuadraoCopy.text("copy.releaseDeleteAccountView.ca30fe6fc2", spanish: spanish),
                              systemImage: "exclamationmark.circle")
                            .accessibilityIdentifier("identity.delete.verificationRejected")
                    }
                    Text(verification == .typedDelete
                         ? CuadraoCopy.text("copy.releaseDeleteAccountView.c991dbe1de", spanish: spanish)
                         : CuadraoCopy.text("copy.releaseDeleteAccountView.215b4daf9a", spanish: spanish))
                    TextField(verification == .typedDelete ? "DELETE" : CuadraoCopy.text("copy.releaseDeleteAccountView.afea7ee5bf", spanish: spanish), text: $confirmation)
                        .textInputAutocapitalization(.never).autocorrectionDisabled()
                        .textContentType(verification == .code ? .oneTimeCode : nil)
                        .focused($focused)
                        .disabled(!state.allowsVerificationInput)
                        .accessibilityIdentifier("identity.delete.verification")
                    if state == .verificationResending {
                        ProgressView(CuadraoCopy.text("copy.releaseDeleteAccountView.74218026cc", spanish: spanish))
                            .accessibilityIdentifier("identity.delete.resending")
                    } else {
                        Button(role: .destructive) {
                            focused = false
                            onSubmit(confirmation.trimmingCharacters(in: .whitespacesAndNewlines))
                        } label: {
                            Text(CuadraoCopy.text("copy.releaseDeleteAccountView.a28f5504bf", spanish: spanish))
                                .font(CuadraoTypography.action).frame(minHeight: 44)
                        }
                        .disabled(!verification.accepts(confirmation))
                        .accessibilityIdentifier("identity.delete.submit")
                        if verification == .code, let onResendCode {
                            Button(CuadraoCopy.text("copy.releaseDeleteAccountView.12a8b81e3a", spanish: spanish)) {
                                focused = false; confirmation = ""; onResendCode()
                            }
                                .accessibilityIdentifier("identity.delete.resend")
                        }
                        Button(CuadraoCopy.text("copy.releaseDeleteAccountView.62a128b722", spanish: spanish)) {
                            focused = false
                            confirmation = ""
                            showingVerification = false
                        }.accessibilityIdentifier("identity.delete.cancelVerification")
                    }
                }
            } else {
                Section {
                    Button(role: .destructive) { showingVerification = true } label: {
                        Text(CuadraoCopy.text("copy.releaseDeleteAccountView.c27a4762b9", spanish: spanish)).font(CuadraoTypography.action).frame(minHeight: 44)
                    }.foregroundStyle(.red).accessibilityIdentifier("identity.delete.continue")
                }
            }
        }
    }

    private func presentVerificationIfNeeded() {
        if state == .verificationRejected || state == .verificationResending { showingVerification = true }
    }

    private func householdConsequence(_ household: ReleaseDeletionConsequences.Household) -> String {
        switch household {
        case .member(let name):
            CuadraoCopy.text("copy.releaseDeleteAccountView.2a88f8765a", spanish: spanish, String(describing: name))
        case .admin(let name, let successor):
            CuadraoCopy.text("copy.releaseDeleteAccountView.6911d28eea", spanish: spanish, String(describing: successor), String(describing: name))
        case .soleMember(let name):
            CuadraoCopy.text("copy.releaseDeleteAccountView.260d816f2a", spanish: spanish, String(describing: name))
        }
    }
}
