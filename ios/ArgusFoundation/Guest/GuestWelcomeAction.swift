import SwiftUI

/// The quiet third action on the welcome screen. It renders only while the guest door is open and no account has
/// signed in on this iPhone, so a Release welcome screen has the two native actions and nothing else.
struct GuestWelcomeAction: View {
    let spanish: Bool
    @Environment(\.cuadraoGuestWelcome) private var welcome
    @State private var confirmingAge = false

    var body: some View {
        if let welcome, case .full(true) = welcome.shape {
            Button { confirmingAge = true } label: {
                Text(CuadraoCopy.text("copy.guestWelcomeAction.b5d1e831c5", spanish: spanish))
                    .font(.system(.body, weight: .medium))
                    .multilineTextAlignment(.center)
                    .foregroundStyle(WelcomePalette.pine)
                    .frame(maxWidth: .infinity, minHeight: 44)
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier("cuadrao.welcome.guest")
            .sheet(isPresented: $confirmingAge) {
                AgeConfirmationGate {
                    Color.clear.onAppear { confirmingAge = false; welcome.open() }
                }
            }
        }
    }
}

/// The one quiet line under the login form when guest data is still on this iPhone.
struct GuestOpenLine: View {
    let spanish: Bool
    let open: () -> Void
    @State private var confirmingAge = false

    var body: some View {
        Button { confirmingAge = true } label: {
            (Text(CuadraoCopy.text("copy.guestWelcomeAction.56622585c5", spanish: spanish))
                .foregroundColor(.secondary)
             + Text(CuadraoCopy.text("copy.guestWelcomeAction.fcb3911249", spanish: spanish)).foregroundColor(WelcomePalette.pine).bold())
                .font(.footnote)
                .multilineTextAlignment(.center)
                .frame(maxWidth: .infinity, minHeight: 44)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .padding(.horizontal, 28).padding(.bottom, 8)
        .accessibilityIdentifier("cuadrao.login.guestLine")
        .sheet(isPresented: $confirmingAge) {
            AgeConfirmationGate {
                Color.clear.onAppear { confirmingAge = false; open() }
            }
        }
    }
}
