#if DEBUG
import SwiftUI

/// Synthetic Apple responses exercise the real gate without a server or Apple account.
struct AgeConfirmationHarness: View {
    @State private var conversion = false
    private let store: AgeConfirmationStore
    private let checker: HarnessAgeRangeChecker

    init() {
        let arguments = ProcessInfo.processInfo.arguments
        let suite = UserDefaults.standard.string(forKey: "ageHarnessSuite") ?? "local.cuadrao.age-harness"
        let defaults = UserDefaults(suiteName: suite)!
        if arguments.contains("--age-reset") { defaults.removePersistentDomain(forName: suite) }
        store = AgeConfirmationStore(defaults: defaults)
        checker = HarnessAgeRangeChecker(fixture: arguments.first { $0.hasPrefix("--age-response=") }?
            .replacingOccurrences(of: "--age-response=", with: "") ?? "older")
    }

    var body: some View {
        NavigationStack {
            AgeConfirmationGate(model: AgeConfirmationModel(store: store, checker: checker)) {
                VStack {
                    Text("Synthetic entry allowed").accessibilityIdentifier("age.harness.allowed")
                    Text(store.confirmation?.timestamp ?? "missing").accessibilityIdentifier("age.harness.timestamp")
                    Button("Synthetic conversion") { conversion = true }
                        .accessibilityIdentifier("age.harness.conversion")
                }
            }
            .id(conversion)
        }
    }
}

@MainActor
private struct HarnessAgeRangeChecker: AgeRangeChecking {
    let fixture: String
    enum Failure: Error { case synthetic }
    func requirement() async throws -> AgeRangeRequirement {
        switch fixture {
        case "older": .unsupported
        case "optional-error", "under18": .optional
        default: .required
        }
    }
    func request() async throws -> DeclaredAgeAssessment {
        switch fixture {
        case "required-error", "optional-error": throw Failure.synthetic
        case "under18": return .under18
        case "declined": return .notShared
        default: return .adult
        }
    }
}
#endif
