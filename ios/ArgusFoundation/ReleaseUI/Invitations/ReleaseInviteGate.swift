import SwiftUI

enum ReleaseInviteGateState: String, CaseIterable {
    case ready, checking, invalid, expired, full, waitlist, consumed, revoked, rateLimited, unavailable

    func title(spanish: Bool) -> String {
        switch self {
        case .ready: CuadraoCopy.text("copy.releaseInviteGate.86d60f9707", spanish: spanish)
        case .checking: CuadraoCopy.text("copy.releaseInviteGate.35b91d9108", spanish: spanish)
        case .invalid: CuadraoCopy.text("copy.releaseInviteGate.0b5e9dd244", spanish: spanish)
        case .expired: CuadraoCopy.text("copy.releaseInviteGate.014fa66195", spanish: spanish)
        case .full: CuadraoCopy.text("copy.releaseInviteGate.7359d3c619", spanish: spanish)
        case .waitlist: CuadraoCopy.text("copy.releaseInviteGate.3889fe8db3", spanish: spanish)
        case .consumed: CuadraoCopy.text("copy.releaseInviteGate.b84951f8f4", spanish: spanish)
        case .revoked: CuadraoCopy.text("copy.releaseInviteGate.9d438b1cc5", spanish: spanish)
        case .rateLimited: CuadraoCopy.text("copy.releaseInviteGate.85d408eb2c", spanish: spanish)
        case .unavailable: CuadraoCopy.text("copy.releaseInvitationsGallery.3350acd647", spanish: spanish)
        }
    }

    func message(spanish: Bool) -> String? {
        switch self {
        case .ready, .checking: nil
        case .invalid: CuadraoCopy.text("copy.releaseInviteGate.c25455a0fb", spanish: spanish)
        case .expired: CuadraoCopy.text("copy.releaseInviteGate.157d5684fd", spanish: spanish)
        case .full: CuadraoCopy.text("copy.releaseInviteGate.a0d1b555ba", spanish: spanish)
        case .waitlist: CuadraoCopy.text("copy.releaseInviteGate.b57fe5014e", spanish: spanish)
        case .consumed: CuadraoCopy.text("copy.releaseInviteGate.fe75190e9e", spanish: spanish)
        case .revoked: CuadraoCopy.text("copy.releaseInviteGate.b1f0006a6a", spanish: spanish)
        case .rateLimited: CuadraoCopy.text("copy.householdInvitationOutcome.d25b70018b", spanish: spanish)
        case .unavailable: CuadraoCopy.text("copy.releaseInviteGate.ad2d417e9d", spanish: spanish)
        }
    }
}

struct ReleaseInviteGate: View {
    let state: ReleaseInviteGateState
    @Binding var code: String
    let spanish: Bool
    let onSubmit: (String) -> Void
    let onWaitlist: () -> Void
    var showsWaitlist = true

    var body: some View {
        ReleaseInvitationPage(title: CuadraoCopy.text("copy.releaseInviteGate.9b4304b2ce", spanish: spanish),
                              subtitle: CuadraoCopy.text("copy.releaseInviteGate.6d5e9008f2", spanish: spanish)) {
            VStack(alignment: .leading, spacing: 16) {
                Text(CuadraoCopy.text("copy.releaseInvitationShare.0da28c8201", spanish: spanish)).font(CuadraoTypography.supporting)
                TextField(CuadraoCopy.text("copy.releaseInviteGate.e17513380c", spanish: spanish), text: $code)
                    .font(.system(.title3, design: .monospaced))
                    .textInputAutocapitalization(.characters).autocorrectionDisabled()
                    .submitLabel(.go).padding(16)
                    .background(WelcomePalette.surface, in: RoundedRectangle(cornerRadius: 16))
                    .disabled(state == .checking)
                    .accessibilityIdentifier("release.inviteGate.code")
                    .onSubmit { submit() }
                if let message = state.message(spanish: spanish) {
                    Label(message, systemImage: "info.circle")
                        .font(CuadraoTypography.supporting)
                        .accessibilityIdentifier("release.inviteGate.status." + state.rawValue)
                }
                Button(action: submit) {
                    HStack {
                        if state == .checking { ProgressView().tint(WelcomePalette.onAccent) }
                        Text(state == .checking ? (CuadraoCopy.text("copy.releaseInviteGate.073bc99acd", spanish: spanish)) : (CuadraoCopy.text("copy.cuadraoDesignGallery.c27a4762b9", spanish: spanish)))
                    }.frame(maxWidth: .infinity, minHeight: 48).modifier(ReleaseProminentLabel())
                }
                .buttonStyle(.borderedProminent)
                .disabled(code.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || state == .checking)
                .accessibilityIdentifier("release.inviteGate.submit")
                Text(CuadraoCopy.text("copy.releaseInviteGate.a6714b9a91", spanish: spanish))
                    .font(CuadraoTypography.caption).foregroundStyle(.secondary)
                if showsWaitlist {
                    Button(action: onWaitlist) {
                        Text(CuadraoCopy.text("copy.releaseInviteGate.bc43d8a224", spanish: spanish))
                            .frame(minHeight: 44)
                    }.accessibilityIdentifier("release.inviteGate.waitlist")
                    Text(CuadraoCopy.text("copy.releaseInviteGate.64be81e0d0", spanish: CuadraoCopy.isSpanish())).font(CuadraoTypography.caption).foregroundStyle(.secondary)
                }
            }
        }
    }

    private func submit() {
        let value = code.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !value.isEmpty, state != .checking else { return }
        onSubmit(value)
    }
}
