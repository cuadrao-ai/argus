import DeclaredAgeRange
import UIKit

@MainActor
struct AppleAgeRangeChecker: AgeRangeChecking {
    func requirement() async throws -> AgeRangeRequirement {
        guard #available(iOS 26.2, *) else { return .unsupported }
        if #available(iOS 26.4, *) {
            let features = try await AgeRangeService.shared.requiredRegulatoryFeatures
            return features.contains(.declaredAgeRangeRequired) ? .required : .optional
        }
        return .optional
    }

    func request() async throws -> DeclaredAgeAssessment {
        guard #available(iOS 26.2, *) else { return .notShared }
        guard let scene = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene })
            .first(where: { $0.activationState == .foregroundActive }),
              var presenter = scene.windows.first(where: \.isKeyWindow)?.rootViewController else {
            throw AgeRangeService.Error.notAvailable
        }
        while let presented = presenter.presentedViewController { presenter = presented }
        let response = try await AgeRangeService.shared.requestAgeRange(ageGates: 18, in: presenter)
        switch response {
        case .sharing(let range):
            return AgeConfirmationPolicy.assessment(lowerBound: range.lowerBound, upperBound: range.upperBound)
        case .declinedSharing: return .notShared
        @unknown default: return .notShared
        }
    }
}
