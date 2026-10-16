import Foundation
import ArgusSession

/// Presents the session owner's deletion results. The journal, identity fence and cleanup obligation stay
/// in SessionController; this model only maps their results and never infers deletion from a response.
@MainActor
final class AccountDeletionModel: ObservableObject {
    @Published private(set) var state: ReleaseDeletionState = .ready
    var sessionChanged: ((SessionSnapshot) -> Void)?
    private let controller: SessionController
    private let appleAvailable: Bool
    private let cleanup: @Sendable (UUID) throws -> Void

    init(controller: SessionController, appleAvailable: Bool, cleanup: @escaping @Sendable (UUID) throws -> Void) {
        self.controller = controller
        self.appleAvailable = appleAvailable
        self.cleanup = cleanup
    }

    /// Accepted or confirmed outcomes outlive the signed-in surface until the person dismisses them.
    var presentsOutcome: Bool { state == .pending || state == .completed }

    func finish() { if state != .submitting { state = .ready } }

    func submit(appleAuthorizationCode code: String? = nil) async {
        await perform {
            let current = await controller.snapshot()
            let result = current.phase == .accountDeletionUncertain
                ? try await controller.resumePendingAccountDeletion(freshAppleAuthorizationCode: code)
                : try await controller.deleteAccount(expectedIdentity: current, freshAppleAuthorizationCode: code)
            try await present(result)
        }
    }

    func retry() async {
        if state == .supportUnavailable { await perform { try await requestSupport() } }
        else { await submit() }
    }

    /// Launch and post-sign-out readback. Confirmed and accepted deletions are acknowledged here when an earlier
    /// cleanup was interrupted; the controller refuses them while any account is signed in.
    func load() async {
        guard state != .submitting else { return }
        let statuses = (try? await controller.accountDeletionStatuses()) ?? []
        var confirmed = false
        for case .completed(let receipt) in statuses {
            await acknowledge(receipt)
            confirmed = true
        }
        for case .pending(let userID) in statuses { await acknowledgeAccepted(userID) }
        switch await controller.snapshot().phase {
        case .accountDeletionUncertain: state = uncertainState(statuses)
        case .accountDeletionPending: state = .pending
        case .signedOut where confirmed: state = .completed
        default: break
        }
    }

    private func perform(_ operation: () async throws -> Void) async {
        guard state != .submitting else { return }
        state = .submitting
        do { try await operation() }
        catch {
            let statuses = (try? await controller.accountDeletionStatuses()) ?? []
            switch await controller.snapshot().phase {
            case .accountDeletionUncertain: state = uncertainState(statuses)
            case .accountDeletionPending: state = .pending
            default: state = .failed
            }
        }
        sessionChanged?(await controller.snapshot())
    }

    private func present(_ result: AccountDeletionResult) async throws {
        switch result {
        case .completed(let receipt):
            await acknowledge(receipt)
            state = .completed
        case .pending(let userID):
            await acknowledgeAccepted(userID)
            state = .pending
        case .uncertain(_, _, let canRetry, let recovery):
            state = uncertain(canRetry: canRetry, recovery: recovery)
        case .refused(.freshAppleAuthorizationRequired) where appleAvailable:
            state = .appleAuthorizationRequired
        case .refused(.disabled), .refused(.forbidden), .refused(.freshAppleAuthorizationRequired):
            try await requestSupport()
        case .refused(.unavailable), .refused(.rateLimited), .refused(.invalidRequest):
            state = .failed
        }
    }

    private func requestSupport() async throws {
        do {
            try await controller.requestAccountDeletionSupport(expectedIdentity: await controller.snapshot())
            state = .supportRequested
        } catch { state = .supportUnavailable }
    }

    /// A failed cleanup keeps the controller's journal as the obligation for the next `load()`.
    private func acknowledge(_ receipt: ConfirmedAccountDeletion) async {
        try? await controller.acknowledgeConfirmedAccountDeletion(receipt, cleanup: cleanup)
    }

    private func acknowledgeAccepted(_ userID: UUID) async {
        try? await controller.acknowledgeAcceptedAccountDeletion(userID: userID, cleanup: cleanup)
    }

    private func uncertainState(_ statuses: [AccountDeletionResult]) -> ReleaseDeletionState {
        for case .uncertain(_, _, let canRetry, let recovery) in statuses {
            return uncertain(canRetry: canRetry, recovery: recovery)
        }
        return .uncertain(canRetry: false)
    }

    private func uncertain(canRetry: Bool, recovery: AccountDeletionRefusal?) -> ReleaseDeletionState {
        canRetry && recovery == .freshAppleAuthorizationRequired && appleAvailable
            ? .appleAuthorizationRequired : .uncertain(canRetry: canRetry)
    }
}
