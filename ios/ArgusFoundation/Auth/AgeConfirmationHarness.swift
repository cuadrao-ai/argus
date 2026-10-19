#if DEBUG
import SwiftUI

struct AgeConfirmationHarness: View {
    @State private var appearance = AppearancePreference.light
    @StateObject private var auth = ProfileAuthModel(configuration: nil, controller: nil)

    init() {
        _appearance = State(initialValue: AppearancePreference(rawValue: UserDefaults.standard.string(forKey: AppearancePreference.storageKey) ?? "light") ?? .light)
    }

    static func legalEntryObservation() -> AgeRangeObservation? {
        guard ProcessInfo.processInfo.arguments.contains("--age-legal-entry") else { return nil }
        let fixture = ProcessInfo.processInfo.arguments.first { $0.hasPrefix("--age-response=") }?
            .replacingOccurrences(of: "--age-response=", with: "") ?? "adult"
        return AgeRangeObservation(checker: HarnessAgeRangeChecker(fixture: fixture))
    }

    var body: some View {
        Group {
            if CuadraoDesignPreview.isActive {
                CuadraoCanvas()
            } else {
                GuestModeRouter(appearance: $appearance) { ConnectedCuadraoRoot(appearance: $appearance) }
                    .environmentObject(auth)
                    .task { await auth.start() }
            }
        }
        .preferredColorScheme(appearance.colorScheme)
    }
}

@MainActor
private struct HarnessAgeRangeChecker: AgeRangeChecking {
    let fixture: String
    enum Failure: Error { case synthetic }

    func request() async throws -> DeclaredAgeAssessment {
        switch fixture {
        case "older": return .unsupported
        case "required-error", "optional-error": throw Failure.synthetic
        case "cancelled": throw CancellationError()
        case "pending":
            try await Task.sleep(for: .seconds(3600))
            return .unknown
        case "under18": return .under18
        case "declined": return .notShared
        case "unknown": return .unknown
        default: return .adult
        }
    }
}
#endif
