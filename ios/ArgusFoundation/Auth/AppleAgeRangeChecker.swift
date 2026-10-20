import DeclaredAgeRange
import UIKit

@MainActor
struct AppleAgeRangeChecker: AgeRangeChecking {
    func request() async throws -> DeclaredAgeAssessment {
        guard #available(iOS 26.2, *) else { return .unsupported }
        guard let scene = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene })
            .first(where: { $0.activationState == .foregroundActive }),
              var presenter = scene.windows.first(where: \.isKeyWindow)?.rootViewController else {
            throw AgeRangeService.Error.notAvailable
        }
        while let presented = presenter.presentedViewController { presenter = presented }
        let response = try await AgeRangeService.shared.requestAgeRange(ageGates: 18, in: presenter)
        switch response {
        case .sharing(let range):
            return DeclaredAgeAssessment(lowerBound: range.lowerBound, upperBound: range.upperBound)
        case .declinedSharing: return .notShared
        @unknown default: return .unknown
        }
    }
}
