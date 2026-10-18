import Foundation
import ArgusSession

enum AgeRangeRequirement { case unsupported, optional, required }
enum DeclaredAgeAssessment { case adult, under18, notShared }

@MainActor
protocol AgeRangeChecking {
    func requirement() async throws -> AgeRangeRequirement
    func request() async throws -> DeclaredAgeAssessment
}

enum AgeEntryDecision: Equatable {
    case allowed(AgeConfirmation)
    case confirmationRequired, under18, sharingRequired, unavailable
}

/// Both entry paths use this policy before opening the guest book or creating an account.
enum AgeConfirmationPolicy {
    @MainActor
    static func authorize(confirmation: AgeConfirmation?, checker: any AgeRangeChecking) async -> AgeEntryDecision {
        guard let confirmation else { return .confirmationRequired }
        let requirement: AgeRangeRequirement
        do { requirement = try await checker.requirement() }
        catch { return .unavailable }
        if case .unsupported = requirement { return .allowed(confirmation) }
        do {
            switch try await checker.request() {
            case .under18: return .under18
            case .adult: return .allowed(confirmation)
            case .notShared: return requirement == .required ? .sharingRequired : .allowed(confirmation)
            }
        } catch {
            return requirement == .required ? .unavailable : .allowed(confirmation)
        }
    }

    static func assessment(lowerBound: Int?, upperBound: Int?) -> DeclaredAgeAssessment {
        if lowerBound == nil { return .under18 }
        if let upperBound, upperBound < 18 { return .under18 }
        if let lowerBound, lowerBound >= 18 { return .adult }
        return .notShared
    }
}

final class AgeConfirmationStore {
    static let key = "cuadrao.age.confirmedAt"
    private let defaults: UserDefaults
    init(defaults: UserDefaults = .standard) { self.defaults = defaults }
    var confirmation: AgeConfirmation? {
        defaults.string(forKey: Self.key).flatMap { AgeConfirmation(timestamp: $0) }
    }
    func save(_ confirmation: AgeConfirmation) { defaults.set(confirmation.timestamp, forKey: Self.key) }
}
