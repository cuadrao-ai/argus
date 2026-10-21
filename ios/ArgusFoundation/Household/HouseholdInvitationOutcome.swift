import SwiftUI
import ArgusSession

/// Why a Household invitation could not be previewed or accepted. Membership never changes here.
struct HouseholdInvitationProblemText: View {
    let problem: InvitationProblem
    @Environment(\.locale) private var locale
    private var spanish: Bool { CuadraoCopy.isSpanish() }

    var body: some View {
        Label(message, systemImage: "info.circle")
            .font(.footnote)
            .accessibilityIdentifier("household.invite.problem." + identifier)
    }

    private var identifier: String {
        switch problem {
        case .invalid: "invalid"
        case .expired: "expired"
        case .revoked: "revoked"
        case .used: "used"
        case .rateLimited: "rateLimited"
        default: "unavailable"
        }
    }

    private var message: String {
        switch problem {
        case .invalid:
            CuadraoCopy.text("copy.householdInvitationOutcome.050053bb17", spanish: spanish)
        case .expired:
            CuadraoCopy.text("copy.householdInvitationOutcome.2e8d513eef", spanish: spanish)
        case .revoked:
            CuadraoCopy.text("copy.householdInvitationOutcome.d40223198f", spanish: spanish)
        case .used:
            CuadraoCopy.text("copy.householdInvitationOutcome.19dd735ae2", spanish: spanish)
        case .rateLimited:
            CuadraoCopy.text("copy.householdInvitationOutcome.d25b70018b", spanish: spanish)
        default:
            CuadraoCopy.text("copy.householdInvitationOutcome.8fcdc6be8d", spanish: spanish)
        }
    }
}

struct HouseholdInvitationEntryHint: View {
    @Environment(\.locale) private var locale
    private var spanish: Bool { CuadraoCopy.isSpanish() }

    var body: some View {
        Text(CuadraoCopy.text("copy.householdInvitationOutcome.f8c568eab8", spanish: spanish))
            .font(.caption).foregroundStyle(.secondary)
            .accessibilityIdentifier("household.invite.hint")
    }
}
