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

    private var spanish: Bool { locale.language.languageCode?.identifier == "es" }
    private func text(_ es: String, _ en: String) -> String { spanish ? es : en }

    public var body: some View {
        List {
            switch state {
            case .ready, .verificationRejected, .verificationResending: review
            case .submitting, .pending:
                Section {
                    if state == .submitting {
                        ProgressView(text("Eliminando tu cuenta…", "Deleting your account…"))
                    } else {
                        Label(text("Eliminación en curso", "Deletion in progress"), systemImage: "clock")
                        Text(text("Estamos eliminando tu cuenta. Ya cerraste sesión y terminaremos de eliminarla en unos días. No tienes que hacer nada.",
                                  "Your account is being deleted. You're signed out now, and we'll finish removing it within a few days. You don't need to do anything."))
                            .foregroundStyle(.secondary)
                            .accessibilityIdentifier("identity.delete.inProgress")
                        Button(text("Listo", "Done"), action: onComplete)
                            .accessibilityIdentifier("identity.delete.pendingDone")
                    }
                }
            case .failed:
                Section {
                    Label(text("No se pudo eliminar", "Couldn't delete your account"), systemImage: "exclamationmark.circle")
                    Text(text("No pudimos eliminar tu cuenta en este momento. Inténtalo de nuevo.",
                              "We couldn't delete your account just now. Try again."))
                        .foregroundStyle(.secondary)
                    Button(text("Volver a intentar", "Try again"), action: onRetry)
                        .accessibilityIdentifier("identity.delete.retry")
                }
            case .completed:
                Section {
                    Label(text("Cuenta eliminada", "Account deleted"), systemImage: "checkmark.circle")
                    Text(text("Tu cuenta está eliminada. Ya cerraste sesión.",
                              "Your account is deleted. You're signed out."))
                        .foregroundStyle(.secondary)
                    Button(text("Listo", "Done"), action: onComplete)
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
                    Button(text("Listo", "Done"), action: onComplete)
                        .accessibilityIdentifier("identity.delete.supportDone")
                }
            case .supportUnavailable:
                Section {
                    Label("auth.deletion.support.unavailable", systemImage: "exclamationmark.circle")
                        .accessibilityIdentifier("identity.delete.supportUnavailable")
                    Button(text("Volver a intentar", "Try again"), action: onRetry)
                        .accessibilityIdentifier("identity.delete.supportRetry")
                }
            }
        }
        .font(CuadraoTypography.body)
        .tint(WelcomePalette.pine)
        .navigationTitle(text("Eliminar cuenta", "Delete account"))
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
                Text(text("Antes de irte", "Before you go"))
                    .font(CuadraoTypography.feature).accessibilityAddTraits(.isHeader)
                Text(text("Se eliminarán tu cuenta y tus datos personales, incluidos tus chats, documentos y planes privados. Tus conexiones se desconectarán. Esta acción no se puede deshacer.",
                          "Your account and personal data, including chats, documents and private plans, will be deleted. Your sources will be disconnected. This cannot be undone."))
            }
            if !consequences.households.isEmpty || consequences.hasLockedHistory {
                Section(text("Tu hogar", "Your household")) {
                    ForEach(Array(consequences.households.enumerated()), id: \.offset) { _, household in
                        Text(householdConsequence(household))
                    }
                    if consequences.hasLockedHistory {
                        Text(text("El hogar dejará de conservar la copia bloqueada de tu historial.",
                                  "The household will no longer retain the locked copy of your history."))
                    }
                }
            }
            if consequences.hasSharedPlans {
                Section(text("Planes compartidos", "Shared plans")) {
                    Text(text(
                        "En los planes que compartes, tus montos se quedan para que las cuentas de los demás sigan cuadrando, pero sin tu nombre: aparecerás como «Exmiembro». Tus recibos y notas se borran. Lo que debes o te deben queda cerrado en la app, no marcado como pagado. Los planes que creaste pasan a la persona que lleva más tiempo en cada uno, salvo los planes de deuda compartidos, que se cierran y quedan solo para consulta.",
                        "In plans you share, your amounts stay so everyone else's numbers still add up, but without your name: you'll show as \"Former member.\" Your receipts and notes are deleted. Anything you owe or are owed is closed in the app, not marked as paid. Plans you created pass to whoever has been in each one longest, except shared debt plans, which are closed and stay view-only."))
                        .accessibilityIdentifier("identity.delete.sharedConsequences")
                    Text(text("Si no queda nadie más en un plan que creaste, ese plan se elimina.",
                              "If no one else is in a plan you created, that plan is deleted."))
                }
            }
            Section(text("Qué se conserva", "What remains")) {
                Text(text("El registro anónimo de las invitaciones y sus conteos se conservan, sin identificarte.",
                          "Anonymous invitation records and counts remain, without identifying you."))
                Text(text("Las copias de mensajes ya enviados por correo a soporte no se borran automáticamente.",
                          "Copies of messages already emailed to support are not automatically erased."))
            }
            if showingVerification {
                Section {
                    if state == .verificationRejected {
                        Label(verification == .code
                              ? text("El código no es válido o venció. Revisa tu código y vuelve a intentarlo.",
                                     "The code is invalid or expired. Check your code and try again.")
                              : text("No se pudo verificar la confirmación. Escribe DELETE y vuelve a intentarlo.",
                                     "The confirmation could not be verified. Type DELETE and try again."),
                              systemImage: "exclamationmark.circle")
                            .accessibilityIdentifier("identity.delete.verificationRejected")
                    }
                    Text(verification == .typedDelete
                         ? text("Escribe DELETE para confirmar.", "Type DELETE to confirm.")
                         : text("Introduce tu código de verificación.", "Enter your verification code."))
                    TextField(verification == .typedDelete ? "DELETE" : text("Código", "Code"), text: $confirmation)
                        .textInputAutocapitalization(.never).autocorrectionDisabled()
                        .textContentType(verification == .code ? .oneTimeCode : nil)
                        .focused($focused)
                        .disabled(!state.allowsVerificationInput)
                        .accessibilityIdentifier("identity.delete.verification")
                    if state == .verificationResending {
                        ProgressView(text("Enviando otro código…", "Sending another code…"))
                            .accessibilityIdentifier("identity.delete.resending")
                    } else {
                        Button(role: .destructive) {
                            focused = false
                            onSubmit(confirmation.trimmingCharacters(in: .whitespacesAndNewlines))
                        } label: {
                            Text(text("Eliminar mi cuenta", "Delete my account"))
                                .font(CuadraoTypography.action).frame(minHeight: 44)
                        }
                        .disabled(!verification.accepts(confirmation))
                        .accessibilityIdentifier("identity.delete.submit")
                        if verification == .code, let onResendCode {
                            Button(text("Enviar otro código", "Send another code")) {
                                focused = false; confirmation = ""; onResendCode()
                            }
                                .accessibilityIdentifier("identity.delete.resend")
                        }
                        Button(text("Cancelar", "Cancel")) {
                            focused = false
                            confirmation = ""
                            showingVerification = false
                        }.accessibilityIdentifier("identity.delete.cancelVerification")
                    }
                }
            } else {
                Section {
                    Button(role: .destructive) { showingVerification = true } label: {
                        Text(text("Continuar", "Continue")).font(CuadraoTypography.action).frame(minHeight: 44)
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
            text("Saldrás de \(name). Los demás miembros verán una nota sin tu nombre.",
                 "You will leave \(name). Other members will see a note without your name.")
        case .admin(let name, let successor):
            text("\(successor) pasará a administrar \(name) por ser el miembro que lleva más tiempo.",
                 "\(successor) will manage \(name) as its longest-standing remaining member.")
        case .soleMember(let name):
            text("\(name) se cerrará porque eres su único miembro.",
                 "\(name) will close because you are its only member.")
        }
    }
}
