import ArgusSession
import Foundation

/// The real server behind a claim: the signed-in session that was open when the claim was started. If the session
/// changes, every call refuses and the claim stops.
struct SessionGuestClaimServer: GuestClaimServer {
    let controller: SessionController
    let identity: SessionSnapshot

    func owner() async -> UUID? {
        let now = await controller.snapshot()
        guard now == identity, now.phase == .authenticated else { return nil }
        return now.profile.flatMap { UUID(uuidString: $0.id) }
    }

    func accounts() async throws -> [FinancialAccount] {
        try await controller.financialAccounts(expectedIdentity: identity)
    }

    func createAccount(_ request: CreateFinancialAccountRequest) async throws -> FinancialAccount {
        try await controller.createFinancialAccount(request, expectedIdentity: identity)
    }

    func setArchived(_ id: UUID, version: Int) async throws -> FinancialAccount {
        try await controller.updateFinancialAccount(id: id, request: EditFinancialAccountRequest(expectedVersion: version, archived: true),
                                                    expectedIdentity: identity)
    }

    func preview(_ command: FinancialActivityCommand) async throws -> FinancialActivityPreview {
        try await controller.financialActivityPreview(command, expectedIdentity: identity)
    }

    func confirm(_ write: PendingFinancialConfirmation) async throws -> FinancialActivityReceipt {
        try await controller.sendFinancialConfirmation(write, expectedIdentity: identity)
    }
}
