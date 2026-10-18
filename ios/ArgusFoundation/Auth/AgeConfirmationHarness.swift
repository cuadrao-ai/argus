#if DEBUG
import SwiftUI

/// Synthetic Apple responses exercise the real gate without a server or Apple account.
struct AgeConfirmationHarness: View {
    @State private var conversion = false
    @State private var appearance = AppearancePreference.light
    @StateObject private var auth = ProfileAuthModel(configuration: nil, controller: nil)
    private let store: AgeConfirmationStore
    private let checker: HarnessAgeRangeChecker

    init() {
        _appearance = State(initialValue: AppearancePreference(rawValue: UserDefaults.standard.string(forKey: AppearancePreference.storageKey) ?? "light") ?? .light)
        let arguments = ProcessInfo.processInfo.arguments
        if arguments.contains("--age-legal-entry"), arguments.contains("--age-reset") {
            UserDefaults.standard.removeObject(forKey: AgeConfirmationStore.key)
        }
        let suite = UserDefaults.standard.string(forKey: "ageHarnessSuite") ?? "local.cuadrao.age-harness"
        let defaults = UserDefaults(suiteName: suite)!
        if arguments.contains("--age-reset") { defaults.removePersistentDomain(forName: suite) }
        store = AgeConfirmationStore(defaults: defaults)
        checker = HarnessAgeRangeChecker(fixture: arguments.first { $0.hasPrefix("--age-response=") }?
            .replacingOccurrences(of: "--age-response=", with: "") ?? "older")
    }

    static func legalEntryModel() -> AgeConfirmationModel? {
        guard ProcessInfo.processInfo.arguments.contains("--age-legal-entry") else { return nil }
        return AgeConfirmationModel(checker: HarnessAgeRangeChecker(fixture: "adult"))
    }

    var body: some View {
        if ProcessInfo.processInfo.arguments.contains("--age-legal-entry") {
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
        } else {
            gate
        }
    }

    private var gate: some View {
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
