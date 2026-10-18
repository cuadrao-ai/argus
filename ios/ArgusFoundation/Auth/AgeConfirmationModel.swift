import Combine
import Foundation
import ArgusSession

@MainActor
final class AgeConfirmationModel: ObservableObject {
    enum State: Equatable { case idle, checking, allowed, under18, sharingRequired, unavailable }
    @Published private(set) var state = State.idle
    private let store: AgeConfirmationStore
    private let checker: any AgeRangeChecking
    private var pendingConfirmation: AgeConfirmation?
    var confirmation: AgeConfirmation? { store.confirmation ?? pendingConfirmation }

    init(store: AgeConfirmationStore = AgeConfirmationStore(), checker: any AgeRangeChecking) {
        self.store = store
        self.checker = checker
    }

    @discardableResult
    func authorize(checked: Bool) async -> Bool {
        guard state != .checking, state != .under18 else { return false }
        let confirmation = self.confirmation ?? (checked ? AgeConfirmation.recorded() : nil)
        pendingConfirmation = confirmation
        state = .checking
        switch await AgeConfirmationPolicy.authorize(confirmation: confirmation, checker: checker) {
        case .allowed(let confirmation): store.save(confirmation); state = .allowed; return true
        case .confirmationRequired: state = .idle
        case .under18: state = .under18
        case .sharingRequired: state = .sharingRequired
        case .unavailable: state = .unavailable
        }
        return false
    }
}
