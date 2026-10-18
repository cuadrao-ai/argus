import SwiftUI

/// The things the on-device book says about itself, each at most once on this iPhone. Deleting the book starts it over.
enum GuestNotice: String, CaseIterable {
    case firstOpen = "cuadrao.guest.notice.firstOpen"
    case firstSave = "cuadrao.guest.notice.firstSave"

    var seen: Bool { UserDefaults.standard.bool(forKey: rawValue) }
    func markSeen() { UserDefaults.standard.set(true, forKey: rawValue) }
    static func reset() { for notice in allCases { UserDefaults.standard.removeObject(forKey: notice.rawValue) } }
}

/// Spanish first; English follows. No em dash.
struct GuestNoticeCopy {
    let spanish: Bool
    var modeLine: String { CuadraoCopy.text("copy.guestNotices.7f78eddbbd", spanish: spanish) }
    /// The one-time first-open toast. The Perfil identity line stays `modeLine`.
    var firstOpenNote: String {
        CuadraoCopy.text("copy.guestNotices.a01222bf1e", spanish: spanish)
    }
    var firstSaveTitle: String { CuadraoCopy.text("copy.guestNotices.cbe7db5ef8", spanish: spanish) }
    var createAccount: String { CuadraoCopy.text("copy.connectedCuadraoAuth.87ab2b1835", spanish: spanish) }
    var notNow: String { CuadraoCopy.text("copy.guestClaimModel.12e8d67ee6", spanish: spanish) }
}

/// Shown once, after the first expense is saved: half height, a grabber, swipe to dismiss. It never blocks the save,
/// which has already happened when it appears.
struct GuestFirstSaveSheet: View {
    let spanish: Bool
    let createAccount: () -> Void
    let dismiss: () -> Void

    private var copy: GuestNoticeCopy { GuestNoticeCopy(spanish: spanish) }

    /// The empty art region, the same rule as the Receipts empty state: a decorative region above the words, hidden from
    /// VoiceOver and from touches. It takes at most the Receipts art height and gives room back first, so the buttons stay
    /// on the half-height sheet. Art placed later goes in its overlay, so it cannot change the layout.
    private var artSlot: some View {
        Color.clear
            .frame(maxWidth: .infinity, minHeight: 0, maxHeight: 150)
            .accessibilityHidden(true).allowsHitTesting(false)
            .accessibilityIdentifier("guest.firstsave.art")
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 24) {
            artSlot
            Text(copy.firstSaveTitle)
                .font(CuadraoTypography.screen).fixedSize(horizontal: false, vertical: true)
                .accessibilityAddTraits(.isHeader).accessibilityIdentifier("guest.firstsave.title")
            VStack(spacing: 8) {
                RegistrationButton(title: copy.createAccount, action: createAccount)
                    .accessibilityIdentifier("guest.firstsave.create")
                Button(action: dismiss) {
                    Text(copy.notNow).font(.system(.body, weight: .medium)).frame(maxWidth: .infinity, minHeight: 48).contentShape(Rectangle())
                }.accessibilityIdentifier("guest.firstsave.later")
            }
        }
        .padding(.horizontal, 24).padding(.top, 32)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .background(WelcomePalette.background.ignoresSafeArea())
        .presentationDetents([.medium])
        .presentationDragIndicator(.visible)
    }
}
