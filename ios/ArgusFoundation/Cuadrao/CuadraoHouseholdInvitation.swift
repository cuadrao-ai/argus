import SwiftUI
import UIKit

struct CanvasHouseholdInvitation: Identifiable {
    let id = UUID()
    // Reserved non-resolving domain: the native sheet never exposes a real invitation.
    var url: URL { URL(string: "https://cuadrao.invalid/invite/\(id.uuidString)")! }
}

struct CuadraoInvitationShareSheet: UIViewControllerRepresentable {
    let invitation: CanvasHouseholdInvitation
    let spanish: Bool

    func makeUIViewController(context: Context) -> UIActivityViewController {
        let message = CuadraoCopy.text("copy.cuadraoHouseholdInvitation.c640de1476", spanish: spanish)
        // Sharing completion is not evidence of delivery, recipient identity or acceptance.
        return UIActivityViewController(activityItems: [message, invitation.url], applicationActivities: nil)
    }
    func updateUIViewController(_ controller: UIActivityViewController, context: Context) {}
}

struct CuadraoInvitationRecipient: View {
    let data: CuadraoAccountsPreview
    let invitation: CanvasHouseholdInvitation
    let spanish: Bool
    @Environment(\.dismiss) private var dismiss
    @State private var accepted = false
    private var available: Bool {
        if case .invitation(let current) = data.household { return current.id == invitation.id }
        return false
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 28) {
                Image(systemName: accepted ? "checkmark" : "person.2")
                    .font(.system(size: 28, weight: .light)).foregroundStyle(WelcomePalette.pine)
                    .frame(width: 60, height: 60)
                    .background(WelcomePalette.sage, in: RoundedRectangle(cornerRadius: 18)).accessibilityHidden(true)
                if accepted {
                    RegistrationHeading(title: CuadraoCopy.text("copy.cuadraoHouseholdInvitation.0284df75d9", spanish: spanish),
                        detail: CuadraoCopy.text("copy.cuadraoHouseholdInvitation.c43a47d315", spanish: spanish))
                    RegistrationButton(title: CuadraoCopy.text("copy.cuadraoDesignGallery.c27a4762b9", spanish: spanish)) { dismiss() }
                } else if available {
                    RegistrationHeading(title: CuadraoCopy.text("copy.cuadraoHouseholdInvitation.c2266a9366", spanish: spanish),
                        detail: CuadraoCopy.text("copy.cuadraoHouseholdInvitation.e222fc80fb", spanish: spanish))
                    VStack(alignment: .leading, spacing: 20) {
                        Label(CuadraoCopy.text("copy.cuadraoHouseholdInvitation.9aec09e5c0", spanish: spanish), systemImage: "person.2")
                        Label(CuadraoCopy.text("copy.cuadraoHouseholdInvitation.816154db34", spanish: spanish), systemImage: "lock")
                    }.font(.subheadline).fixedSize(horizontal: false, vertical: true)
                    RegistrationButton(title: CuadraoCopy.text("copy.cuadraoHouseholdInvitation.deac7853ea", spanish: spanish)) {
                        guard available else { return }
                        data.household = .joined("Alex")
                        accepted = true
                    }.accessibilityIdentifier("household-accept-invitation")
                    Button(CuadraoCopy.text("copy.guestClaimModel.12e8d67ee6", spanish: spanish)) { dismiss() }
                        .frame(maxWidth: .infinity, minHeight: 44)
                } else {
                    RegistrationHeading(title: CuadraoCopy.text("copy.cuadraoHouseholdInvitation.3d06492751", spanish: spanish),
                        detail: CuadraoCopy.text("copy.cuadraoHouseholdInvitation.14fec7aac9", spanish: spanish))
                    RegistrationButton(title: CuadraoCopy.text("copy.cuadraoHouseholdInvitation.48bff92372", spanish: spanish)) { dismiss() }
                }
            }.padding(24)
        }.background(WelcomePalette.background)
            .navigationTitle(CuadraoCopy.text("copy.cuadraoHouseholdInvitation.6bcc87c51e", spanish: spanish))
            .navigationBarTitleDisplayMode(.inline)
    }
}
