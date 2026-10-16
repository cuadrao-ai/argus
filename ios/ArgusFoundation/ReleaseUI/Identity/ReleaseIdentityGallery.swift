#if DEBUG
import SwiftUI

public struct ReleaseIdentityGallery: View {
    @Environment(\.locale) private var locale
    public init() {}
    private var spanish: Bool { locale.language.languageCode?.identifier == "es" }

    public var body: some View {
        List {
            Section {
                NavigationLink(spanish ? "Eliminar cuenta" : "Delete account") { DeletionFixture() }
                    .accessibilityIdentifier("identity.gallery.delete")
                NavigationLink(spanish ? "Apple y Google" : "Apple and Google") { SocialFixture() }
                    .accessibilityIdentifier("identity.gallery.social")
                NavigationLink(spanish ? "Permiso para IA" : "AI permission") { ConsentFixture() }
                    .accessibilityIdentifier("identity.gallery.ai")
                NavigationLink(spanish ? "Fuentes conectadas" : "Connected sources") { SourcesFixture() }
                    .accessibilityIdentifier("identity.gallery.sources")
                NavigationLink(spanish ? "Memoria" : "Memory") { MemoryFixture() }
                    .accessibilityIdentifier("identity.gallery.memory")
            }
        }
        .navigationTitle(spanish ? "Identidad y datos" : "Identity and data")
        .navigationBarTitleDisplayMode(.inline)
        .font(CuadraoTypography.body).tint(WelcomePalette.pine)
        .accessibilityIdentifier("identity.gallery")
    }
}

private struct DeletionFixture: View {
    @Environment(\.locale) private var locale
    @State private var state: ReleaseDeletionState = .ready
    @State private var profile = 1
    @State private var verification: ReleaseDeletionVerification = .typedDelete
    @State private var finished = false
    private var spanish: Bool { locale.language.languageCode?.identifier == "es" }
    private var consequences: ReleaseDeletionConsequences {
        switch profile {
        case 1: .init(households: [.admin(name: spanish ? "Nuestro hogar" : "Our household", successor: "Alex")],
                      hasSharedPlans: true, hasLockedHistory: true)
        case 2: .init(households: [.soleMember(name: spanish ? "Mi hogar" : "My household")])
        case 3: .init(households: [.member(name: spanish ? "Nuestro hogar" : "Our household")], hasSharedPlans: true)
        default: .init()
        }
    }

    var body: some View {
        Group {
            if finished {
                ContentUnavailableView(spanish ? "Sesión cerrada" : "Signed out", systemImage: "person.crop.circle")
                    .toolbar { Button(spanish ? "Reiniciar" : "Reset") { finished = false; state = .ready } }
            } else {
                ReleaseDeleteAccountView(consequences: consequences, state: state, verification: verification,
                                         onSubmit: { _ in state = .submitting }, onRetry: { state = .submitting },
                                         onComplete: { finished = true }, onResendCode: { state = .verificationResending })
                    .id("\(profile)-\(verification)")
                    .toolbar {
                        Menu {
                            Section(spanish ? "Estado" : "State") {
                                Button(spanish ? "Confirmación" : "Review") { state = .ready }
                                Button(spanish ? "Verificación rechazada" : "Verification rejected") { state = .verificationRejected }
                                Button(spanish ? "Código enviado" : "Code sent") { state = .ready }
                                Button(spanish ? "En proceso" : "Submitting") { state = .submitting }
                                Button(spanish ? "Pendiente" : "Pending") { state = .pending }
                                Button(spanish ? "Error" : "Error") { state = .failed }
                                Button(spanish ? "Completada" : "Completed") { state = .completed }
                                Button(spanish ? "Sin confirmar" : "Unconfirmed") { state = .uncertain(canRetry: true) }
                                Button(spanish ? "Sin confirmar, soporte" : "Unconfirmed, support") { state = .uncertain(canRetry: false) }
                                Button("Apple") { state = .appleAuthorizationRequired }
                                Button(spanish ? "Solicitud enviada" : "Support request sent") { state = .supportRequested }
                                Button(spanish ? "Solicitud no enviada" : "Support request failed") { state = .supportUnavailable }
                            }
                            Section(spanish ? "Cuenta" : "Account") {
                                Button(spanish ? "Personal" : "Personal") { profile = 0; state = .ready }
                                Button(spanish ? "Administrador" : "Administrator") { profile = 1; state = .ready }
                                Button(spanish ? "Único miembro" : "Only member") { profile = 2; state = .ready }
                                Button(spanish ? "Miembro" : "Member") { profile = 3; state = .ready }
                            }
                            Section(spanish ? "Verificación" : "Verification") {
                                Button("DELETE") { verification = .typedDelete; state = .ready }
                                Button(spanish ? "Código" : "Code") { verification = .code; state = .ready }
                            }
                        } label: { Image(systemName: "slider.horizontal.3") }
                        .accessibilityLabel(spanish ? "Estados de muestra" : "Sample states")
                        .accessibilityIdentifier("identity.delete.fixtureStates")
                    }
            }
        }
    }
}

private struct SocialFixture: View {
    @Environment(\.locale) private var locale
    @State private var state: ReleaseSocialSignInState = .idle
    @State private var hasInvite = true
    @State private var continuing = false
    private var spanish: Bool { locale.language.languageCode?.identifier == "es" }
    private var invite: ReleasePendingInvite? {
        hasInvite ? .init(id: "local-invite", title: spanish ? "Viaje de diciembre" : "December trip") : nil
    }
    var body: some View {
        ReleaseSocialSignInView(state: state, pendingInvite: invite,
                               onSignIn: { provider, _ in state = .loading(provider) },
                               onSaveName: { _, _ in state = .savingName },
                               onContinue: { _ in continuing = true })
            .alert(spanish ? "Continuar" : "Continue", isPresented: $continuing) {
                Button("OK", role: .cancel) {}
            } message: {
                Text(hasInvite ? (spanish ? "Abrir invitación" : "Open invitation") : (spanish ? "Abrir inicio" : "Open Home"))
            }
            .toolbar {
                Menu {
                    Button(spanish ? "Inicio" : "Idle") { state = .idle }
                    Button(spanish ? "Cancelado" : "Cancelled") { state = .cancelled }
                    Button("Error") { state = .failed }
                    Button(spanish ? "Falta nombre" : "Missing name") { state = .missingName }
                    Button(spanish ? "Error al guardar nombre" : "Name save failed") { state = .nameFailed }
                    Button(spanish ? "Completado" : "Complete") { state = .complete }
                    Toggle(spanish ? "Con invitación" : "With invitation", isOn: $hasInvite)
                } label: { Image(systemName: "slider.horizontal.3") }
                .accessibilityLabel(spanish ? "Estados de muestra" : "Sample states")
                .accessibilityIdentifier("identity.social.fixtureStates")
            }
    }
}

private struct ConsentFixture: View {
    @Environment(\.locale) private var locale
    @Environment(\.dismiss) private var dismiss
    @State private var state: ReleaseAIConsentState = .required
    private var spanish: Bool { locale.language.languageCode?.identifier == "es" }
    var body: some View {
        ReleaseAIConsentView(disclosure: .init(providerName: "OpenRouter",
            purpose: spanish ? "Para preparar una respuesta a tu pregunta." : "To prepare an answer to your question.",
            dataItems: [spanish ? "Tu mensaje" : "Your message", spanish ? "El contexto que elijas" : "The context you choose"],
            privacyURL: URL(string: "https://openrouter.ai/privacy")!), state: state,
            onAllow: { state = .submitting }, onDecline: { dismiss() }, onContinue: { dismiss() })
            .toolbar {
                Menu {
                    Button(spanish ? "Pedir permiso" : "Ask permission") { state = .required }
                    Button("Error") { state = .failed }
                    Button(spanish ? "Guardado" : "Saved") { state = .accepted }
                } label: { Image(systemName: "slider.horizontal.3") }
                .accessibilityLabel(spanish ? "Estados de muestra" : "Sample states")
                .accessibilityIdentifier("identity.ai.fixtureStates")
            }
    }
}

private struct SourcesFixture: View {
    @Environment(\.locale) private var locale
    @State private var state: ReleaseConnectedSource.State = .connected
    @State private var empty = false
    private var spanish: Bool { locale.language.languageCode?.identifier == "es" }
    var body: some View {
        ReleaseConnectedSourcesView(sources: empty ? [] : [.init(id: "gmail", name: "Gmail", detail: "lucas@example.com", state: state)],
                                    onDisconnect: { _ in state = .disconnecting }, onRetry: { _ in state = .disconnecting })
            .toolbar {
                Menu {
                    Button(spanish ? "Conectada" : "Connected") { empty = false; state = .connected }
                    Button(spanish ? "Pendiente" : "Pending") { empty = false; state = .pending }
                    Button("Error") { empty = false; state = .failed }
                    Button(spanish ? "Desconectada" : "Disconnected") { empty = false; state = .disconnected }
                    Button(spanish ? "Sin fuentes" : "Empty") { empty = true }
                } label: { Image(systemName: "slider.horizontal.3") }
                .accessibilityLabel(spanish ? "Estados de muestra" : "Sample states")
                .accessibilityIdentifier("identity.sources.fixtureStates")
            }
    }
}

private struct MemoryFixture: View {
    @Environment(\.locale) private var locale
    @State private var state: ReleaseMemoryState = .off
    private var spanish: Bool { locale.language.languageCode?.identifier == "es" }
    var body: some View {
        ReleaseMemoryControlsView(state: state, onSetEnabled: { enabled in state = .updating(isEnabled: enabled) },
                                  onReset: { state = .resetting(isEnabled: state.isEnabled) })
            .toolbar {
                Menu {
                    Button(spanish ? "Desactivada" : "Off") { state = .off }
                    Button(spanish ? "Activada" : "On") { state = .on }
                    Button("Error") { state = .failed(isEnabled: state.isEnabled) }
                    Button(spanish ? "Restablecida" : "Reset") { state = .resetComplete(isEnabled: false) }
                } label: { Image(systemName: "slider.horizontal.3") }
                .accessibilityLabel(spanish ? "Estados de muestra" : "Sample states")
                .accessibilityIdentifier("identity.memory.fixtureStates")
            }
    }
}
#endif
