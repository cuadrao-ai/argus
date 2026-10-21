import SwiftUI

public struct ReleaseAIConsentView: View {
    public let disclosure: ReleaseAIConsentDisclosure
    public let state: ReleaseAIConsentState
    public let onAllow: () -> Void
    public let onDecline: () -> Void
    public let onContinue: () -> Void
    @Environment(\.locale) private var locale

    public init(disclosure: ReleaseAIConsentDisclosure, state: ReleaseAIConsentState,
                onAllow: @escaping () -> Void, onDecline: @escaping () -> Void,
                onContinue: @escaping () -> Void) {
        self.disclosure = disclosure; self.state = state
        self.onAllow = onAllow; self.onDecline = onDecline; self.onContinue = onContinue
    }

    private var spanish: Bool { CuadraoCopy.isSpanish() }

    public var body: some View {
        List {
            Section {
                Text(CuadraoCopy.text("copy.releaseAIConsentView.e2fc23120b", spanish: spanish))
                    .font(CuadraoTypography.feature).accessibilityAddTraits(.isHeader)
                Text(disclosure.purpose)
                Text(CuadraoCopy.text("copy.releaseAIConsentView.d942a110e5", spanish: spanish, String(describing: disclosure.providerName)))
                ForEach(Array(disclosure.dataItems.enumerated()), id: \.offset) { _, item in
                    Label(item, systemImage: "doc.text").font(CuadraoTypography.supporting)
                }
                Link(CuadraoCopy.text("copy.releaseAIConsentView.f0fa625f4e", spanish: spanish, String(describing: disclosure.providerName)),
                     destination: disclosure.privacyURL)
                    .frame(minHeight: 44).accessibilityIdentifier("identity.ai.privacy")
            }
            Section {
                if state == .accepted {
                    Label(CuadraoCopy.text("copy.releaseAIConsentView.212bfe3583", spanish: spanish), systemImage: "checkmark.circle")
                    Button(CuadraoCopy.text("copy.releaseAIConsentView.c27a4762b9", spanish: spanish), action: onContinue)
                        .accessibilityIdentifier("identity.ai.continue")
                } else {
                    if state == .failed {
                        Label(CuadraoCopy.text("copy.releaseAIConsentView.03c75422ac", spanish: spanish), systemImage: "exclamationmark.circle")
                    }
                    if state == .submitting { ProgressView(CuadraoCopy.text("copy.releaseAIConsentView.5f4c79aff9", spanish: spanish)) }
                    Button(CuadraoCopy.text("copy.releaseAIConsentView.a46c35bca8", spanish: spanish), action: onAllow)
                        .disabled(state == .submitting).accessibilityIdentifier("identity.ai.allow")
                    Button(CuadraoCopy.text("copy.releaseAIConsentView.12e8d67ee6", spanish: spanish), action: onDecline)
                        .disabled(state == .submitting).accessibilityIdentifier("identity.ai.decline")
                }
            }
        }
        .font(CuadraoTypography.body).tint(WelcomePalette.pine)
        .navigationTitle(CuadraoCopy.text("copy.releaseAIConsentView.fb62820a9a", spanish: spanish))
        .navigationBarTitleDisplayMode(.inline)
        .accessibilityIdentifier("identity.ai.screen")
    }
}
