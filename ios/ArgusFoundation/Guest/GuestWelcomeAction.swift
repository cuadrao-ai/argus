import SwiftUI

/// The quiet third action on the welcome screen. It renders only while the guest door is open and no account has
/// signed in on this iPhone, so a Release welcome screen has the two native actions and nothing else.
struct GuestWelcomeAction: View {
    let spanish: Bool
    @Environment(\.cuadraoGuestWelcome) private var welcome

    var body: some View {
        if let welcome, case .full(true) = welcome.shape {
            Button(action: welcome.open) {
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

/// The one quiet line under the login form when guest data is still on this iPhone.
struct GuestOpenLine: View {
    let spanish: Bool
    let open: () -> Void

    var body: some View {
        Button(action: open) {
            (Text(spanish ? "Tienes datos de invitado en este iPhone · " : "You have guest data on this iPhone · ")
                .foregroundColor(.secondary)
             + Text(spanish ? "Abrir" : "Open").foregroundColor(WelcomePalette.pine).bold())
                .font(.footnote)
                .multilineTextAlignment(.center)
                .frame(maxWidth: .infinity, minHeight: 44)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .padding(.horizontal, 28).padding(.bottom, 8)
        .accessibilityIdentifier("cuadrao.login.guestLine")
    }
}

/// Always at the top of the book, so it is never mistaken for the account.
struct GuestModeBanner: View {
    let spanish: Bool

    var body: some View {
        Text(spanish ? "Modo invitado · solo en este iPhone" : "Guest mode · only on this iPhone")
            .font(.footnote.weight(.medium))
            .foregroundStyle(WelcomePalette.ink)
            .frame(maxWidth: .infinity, minHeight: 28)
            .background(WelcomePalette.brandPaper)
            .accessibilityIdentifier("guest.banner")
    }
}
