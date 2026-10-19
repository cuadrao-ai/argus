import DeclaredAgeRange
import UIKit
#if DEBUG
import OSLog
#endif

@MainActor
struct AppleAgeRangeChecker: AgeRangeChecking {
    func requirement() async throws -> AgeRangeRequirement {
        guard #available(iOS 26.2, *) else { return .unsupported }
        if #available(iOS 26.4, *) {
            do {
                let features = try await AgeRangeService.shared.requiredRegulatoryFeatures
                return features.contains(.declaredAgeRangeRequired) ? .required : .optional
            } catch {
                log(error, stage: .requirement)
                throw error
            }
        }
        return .optional
    }

    func request() async throws -> DeclaredAgeAssessment {
        guard #available(iOS 26.2, *) else { return .notShared }
        guard let scene = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene })
            .first(where: { $0.activationState == .foregroundActive }),
              var presenter = scene.windows.first(where: \.isKeyWindow)?.rootViewController else {
            let error = AgeRangeService.Error.notAvailable
            log(error, stage: .presentation)
            throw error
        }
        while let presented = presenter.presentedViewController { presenter = presented }
        let response: AgeRangeService.Response
        do {
            response = try await AgeRangeService.shared.requestAgeRange(ageGates: 18, in: presenter)
        } catch {
            log(error, stage: .request)
            throw error
        }
        switch response {
        case .sharing(let range):
            return AgeConfirmationPolicy.assessment(lowerBound: range.lowerBound, upperBound: range.upperBound)
        case .declinedSharing: return .notShared
        @unknown default: return .notShared
        }
    }

    private enum DiagnosticStage: String { case requirement, presentation, request }

    private func log(_ error: Error, stage: DiagnosticStage) {
        #if DEBUG
        let failure = error as NSError
        Logger(subsystem: "local.cuadrao.age-confirmation", category: "native-age-check")
            .error("stage=\(stage.rawValue, privacy: .public) domain=\(failure.domain, privacy: .public) code=\(failure.code) description=\(failure.localizedDescription, privacy: .public)")
        #endif
    }
}
