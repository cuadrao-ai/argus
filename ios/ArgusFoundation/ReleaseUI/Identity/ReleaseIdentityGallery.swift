#if DEBUG
import SwiftUI

public struct ReleaseIdentityGallery: View {
    @Environment(\.locale) private var locale
    public init() {}
    private var spanish: Bool { CuadraoCopy.isSpanish() }

    public var body: some View {
        List {
            Section {
                NavigationLink(CuadraoCopy.text("copy.cuadraoProfilePage.a094025062", spanish: spanish)) { DeletionFixture() }
                    .accessibilityIdentifier("identity.gallery.delete")
                NavigationLink(CuadraoCopy.text("copy.releaseIdentityGallery.f6914554fc", spanish: spanish)) { SocialFixture() }
                    .accessibilityIdentifier("identity.gallery.social")
                NavigationLink(CuadraoCopy.text("copy.releaseIdentityGallery.fb62820a9a", spanish: spanish)) { ConsentFixture() }
                    .accessibilityIdentifier("identity.gallery.ai")
                NavigationLink(CuadraoCopy.text("copy.releaseIdentityGallery.3985a96bb5", spanish: spanish)) { SourcesFixture() }
                    .accessibilityIdentifier("identity.gallery.sources")
                NavigationLink(CuadraoCopy.text("copy.releaseIdentityGallery.7fa6d06e03", spanish: spanish)) { MemoryFixture() }
                    .accessibilityIdentifier("identity.gallery.memory")
            }
        }
        .navigationTitle(CuadraoCopy.text("copy.releaseIdentityGallery.ba2eba4b9a", spanish: spanish))
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
    private var spanish: Bool { CuadraoCopy.isSpanish() }
    private var consequences: ReleaseDeletionConsequences {
        switch profile {
        case 1: .init(households: [.admin(name: CuadraoCopy.text("copy.releaseIdentityGallery.b4d5a2ef2b", spanish: spanish), successor: "Alex")],
                      hasSharedPlans: true, hasLockedHistory: true)
        case 2: .init(households: [.soleMember(name: CuadraoCopy.text("copy.releaseIdentityGallery.fdd76e2776", spanish: spanish))])
        case 3: .init(households: [.member(name: CuadraoCopy.text("copy.releaseIdentityGallery.b4d5a2ef2b", spanish: spanish))], hasSharedPlans: true)
        default: .init()
        }
    }

    var body: some View {
        Group {
            if finished {
                ContentUnavailableView(CuadraoCopy.text("copy.releaseIdentityGallery.973f9b5859", spanish: spanish), systemImage: "person.crop.circle")
                    .toolbar { Button(CuadraoCopy.text("copy.releaseIdentityGallery.6416596952", spanish: spanish)) { finished = false; state = .ready } }
            } else {
                ReleaseDeleteAccountView(consequences: consequences, state: state, verification: verification,
                                         onSubmit: { _ in state = .submitting }, onRetry: { state = .submitting },
                                         onComplete: { finished = true }, onResendCode: { state = .verificationResending })
                    .id("\(profile)-\(verification)")
                    .toolbar {
                        Menu {
                            Section(CuadraoCopy.text("copy.releaseIdentityGallery.3f0dd2f033", spanish: spanish)) {
                                Button(CuadraoCopy.text("copy.releaseIdentityGallery.2a22f06301", spanish: spanish)) { state = .ready }
                                Button(CuadraoCopy.text("copy.releaseIdentityGallery.a89278a9c9", spanish: spanish)) { state = .verificationRejected }
                                Button(CuadraoCopy.text("copy.releaseIdentityGallery.7c05f7c61f", spanish: spanish)) { state = .ready }
                                Button(CuadraoCopy.text("copy.releaseIdentityGallery.28b2e237d7", spanish: spanish)) { state = .submitting }
                                Button(CuadraoCopy.text("copy.releaseIdentityGallery.de4ab1019f", spanish: spanish)) { state = .pending }
                                Button(CuadraoCopy.text("copy.releaseIdentityGallery.9160f189de", spanish: spanish)) { state = .failed }
                                Button(CuadraoCopy.text("copy.releaseIdentityGallery.72b13cf7ce", spanish: spanish)) { state = .completed }
                                Button(CuadraoCopy.text("copy.releaseIdentityGallery.70eb20b8d0", spanish: spanish)) { state = .uncertain(canRetry: true) }
                                Button(CuadraoCopy.text("copy.releaseIdentityGallery.6f2853fc53", spanish: spanish)) { state = .uncertain(canRetry: false) }
                                Button("Apple") { state = .appleAuthorizationRequired }
                                Button(CuadraoCopy.text("copy.releaseIdentityGallery.b6d18e1df4", spanish: spanish)) { state = .supportRequested }
                                Button(CuadraoCopy.text("copy.releaseIdentityGallery.78ffae52ca", spanish: spanish)) { state = .supportUnavailable }
                            }
                            Section(CuadraoCopy.text("copy.connectedAccountPresentation.f9d32ca2e5", spanish: spanish)) {
                                Button(CuadraoCopy.text("copy.releaseIdentityGallery.e49bf008a8", spanish: spanish)) { profile = 0; state = .ready }
                                Button(CuadraoCopy.text("copy.releaseIdentityGallery.c9d81a1648", spanish: spanish)) { profile = 1; state = .ready }
                                Button(CuadraoCopy.text("copy.releaseIdentityGallery.845d7515e4", spanish: spanish)) { profile = 2; state = .ready }
                                Button(CuadraoCopy.text("copy.releaseIdentityGallery.39166366b4", spanish: spanish)) { profile = 3; state = .ready }
                            }
                            Section(CuadraoCopy.text("copy.releaseIdentityGallery.48684a483a", spanish: spanish)) {
                                Button("DELETE") { verification = .typedDelete; state = .ready }
                                Button(CuadraoCopy.text("copy.releaseIdentityGallery.afea7ee5bf", spanish: spanish)) { verification = .code; state = .ready }
                            }
                        } label: { Image(systemName: "slider.horizontal.3") }
                        .accessibilityLabel(CuadraoCopy.text("copy.releaseIdentityGallery.0d8eb10350", spanish: spanish))
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
    private var spanish: Bool { CuadraoCopy.isSpanish() }
    private var invite: ReleasePendingInvite? {
        hasInvite ? .init(id: "local-invite", title: CuadraoCopy.text("copy.releaseIdentityGallery.60a186f0a5", spanish: spanish)) : nil
    }
    var body: some View {
        ReleaseSocialSignInView(state: state, pendingInvite: invite,
                               onSignIn: { provider, _ in state = .loading(provider) },
                               onSaveName: { _, _ in state = .savingName },
                               onContinue: { _ in continuing = true })
            .alert(CuadraoCopy.text("copy.cuadraoDesignGallery.c27a4762b9", spanish: spanish), isPresented: $continuing) {
                Button("OK", role: .cancel) {}
            } message: {
                Text(hasInvite ? (CuadraoCopy.text("copy.releaseIdentityGallery.e92d1b5484", spanish: spanish)) : (CuadraoCopy.text("copy.releaseIdentityGallery.828273848e", spanish: spanish)))
            }
            .toolbar {
                Menu {
                    Button(CuadraoCopy.text("copy.releaseIdentityGallery.8d64141a76", spanish: spanish)) { state = .idle }
                    Button(CuadraoCopy.text("copy.releaseIdentityGallery.4589be2a6f", spanish: spanish)) { state = .cancelled }
                    Button("Error") { state = .failed }
                    Button(CuadraoCopy.text("copy.releaseIdentityGallery.deb53eab09", spanish: spanish)) { state = .missingName }
                    Button(CuadraoCopy.text("copy.releaseIdentityGallery.7b8376b993", spanish: spanish)) { state = .nameFailed }
                    Button(CuadraoCopy.text("copy.releaseIdentityGallery.1b8cd4b822", spanish: spanish)) { state = .complete }
                    Toggle(CuadraoCopy.text("copy.releaseIdentityGallery.efb8797eba", spanish: spanish), isOn: $hasInvite)
                } label: { Image(systemName: "slider.horizontal.3") }
                .accessibilityLabel(CuadraoCopy.text("copy.releaseIdentityGallery.0d8eb10350", spanish: spanish))
                .accessibilityIdentifier("identity.social.fixtureStates")
            }
    }
}

private struct ConsentFixture: View {
    @Environment(\.locale) private var locale
    @Environment(\.dismiss) private var dismiss
    @State private var state: ReleaseAIConsentState = .required
    private var spanish: Bool { CuadraoCopy.isSpanish() }
    var body: some View {
        ReleaseAIConsentView(disclosure: .init(providerName: "OpenRouter",
            purpose: CuadraoCopy.text("copy.releaseIdentityGallery.dd93e6a449", spanish: spanish),
            dataItems: [CuadraoCopy.text("copy.releaseIdentityGallery.532d253bbc", spanish: spanish), CuadraoCopy.text("copy.releaseIdentityGallery.0be47af6d3", spanish: spanish)],
            privacyURL: URL(string: "https://openrouter.ai/privacy")!), state: state,
            onAllow: { state = .submitting }, onDecline: { dismiss() }, onContinue: { dismiss() })
            .toolbar {
                Menu {
                    Button(CuadraoCopy.text("copy.releaseIdentityGallery.9b0c068a2b", spanish: spanish)) { state = .required }
                    Button("Error") { state = .failed }
                    Button(CuadraoCopy.text("copy.releaseIdentityGallery.ee7c647644", spanish: spanish)) { state = .accepted }
                } label: { Image(systemName: "slider.horizontal.3") }
                .accessibilityLabel(CuadraoCopy.text("copy.releaseIdentityGallery.0d8eb10350", spanish: spanish))
                .accessibilityIdentifier("identity.ai.fixtureStates")
            }
    }
}

private struct SourcesFixture: View {
    @Environment(\.locale) private var locale
    @State private var state: ReleaseConnectedSource.State = .connected
    @State private var empty = false
    private var spanish: Bool { CuadraoCopy.isSpanish() }
    var body: some View {
        ReleaseConnectedSourcesView(sources: empty ? [] : [.init(id: "gmail", name: "Gmail", detail: "lucas@example.com", state: state)],
                                    onDisconnect: { _ in state = .disconnecting }, onRetry: { _ in state = .disconnecting })
            .toolbar {
                Menu {
                    Button(CuadraoCopy.text("copy.releaseIdentityGallery.d0b008d8fa", spanish: spanish)) { empty = false; state = .connected }
                    Button(CuadraoCopy.text("copy.releaseIdentityGallery.de4ab1019f", spanish: spanish)) { empty = false; state = .pending }
                    Button("Error") { empty = false; state = .failed }
                    Button(CuadraoCopy.text("copy.releaseIdentityGallery.906459808e", spanish: spanish)) { empty = false; state = .disconnected }
                    Button(CuadraoCopy.text("copy.releaseIdentityGallery.867ddb1e9b", spanish: spanish)) { empty = true }
                } label: { Image(systemName: "slider.horizontal.3") }
                .accessibilityLabel(CuadraoCopy.text("copy.releaseIdentityGallery.0d8eb10350", spanish: spanish))
                .accessibilityIdentifier("identity.sources.fixtureStates")
            }
    }
}

private struct MemoryFixture: View {
    @Environment(\.locale) private var locale
    @State private var state: ReleaseMemoryState = .off
    private var spanish: Bool { CuadraoCopy.isSpanish() }
    var body: some View {
        ReleaseMemoryControlsView(state: state, onSetEnabled: { enabled in state = .updating(isEnabled: enabled) },
                                  onReset: { state = .resetting(isEnabled: state.isEnabled) })
            .toolbar {
                Menu {
                    Button(CuadraoCopy.text("copy.releaseIdentityGallery.a6a98e19d6", spanish: spanish)) { state = .off }
                    Button(CuadraoCopy.text("copy.releaseIdentityGallery.13b1140708", spanish: spanish)) { state = .on }
                    Button("Error") { state = .failed(isEnabled: state.isEnabled) }
                    Button(CuadraoCopy.text("copy.releaseIdentityGallery.3be141de80", spanish: spanish)) { state = .resetComplete(isEnabled: false) }
                } label: { Image(systemName: "slider.horizontal.3") }
                .accessibilityLabel(CuadraoCopy.text("copy.releaseIdentityGallery.0d8eb10350", spanish: spanish))
                .accessibilityIdentifier("identity.memory.fixtureStates")
            }
    }
}
#endif
