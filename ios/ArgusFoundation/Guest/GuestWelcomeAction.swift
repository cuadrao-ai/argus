import SwiftUI

/// The quiet third action on the welcome screen. It renders only while the guest door is open (the router sets the
/// entry), so a Release welcome screen has the two native actions and nothing else.
struct GuestWelcomeAction: View {
    let spanish: Bool
    @Environment(\.cuadraoGuestEntry) private var entry

    var body: some View {
        if let entry {
            Button(action: entry) {
                Text(spanish ? "Probar sin cuenta" : "Try without an account")
                    .font(.system(.body, weight: .medium))
                    .multilineTextAlignment(.center)
                    .foregroundStyle(WelcomePalette.pine)
                    .frame(maxWidth: .infinity, minHeight: 44)
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier("cuadrao.welcome.guest")
        }
    }
}
