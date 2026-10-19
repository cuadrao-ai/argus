#if DEBUG
import SwiftUI
import ArgusSession
import Security

struct AgeConfirmationHarness: View {
    @State private var appearance = AppearancePreference.light
    @StateObject private var auth: ProfileAuthModel
    private let fixture: String
    private let signupProof: Bool

    init() {
        _appearance = State(initialValue: AppearancePreference(rawValue: UserDefaults.standard.string(forKey: AppearancePreference.storageKey) ?? "light") ?? .light)
        let arguments = ProcessInfo.processInfo.arguments
        fixture = arguments.first { $0.hasPrefix("--age-response=") }?
            .replacingOccurrences(of: "--age-response=", with: "") ?? "adult"
        signupProof = arguments.contains("--age-signup-proof")
        let observation = signupProof || arguments.contains("--age-legal-entry")
            ? AgeRangeObservation(checker: HarnessAgeRangeChecker(fixture: fixture),
                                  now: { Date(timeIntervalSince1970: 1767225600) }) : nil
        if signupProof {
            let service = "local.cuadrao.age-signup-proof"
            SecItemDelete([kSecClass: kSecClassGenericPassword, kSecAttrService: service] as CFDictionary)
            let origin = URL(string: "http://127.0.0.1:59920")!
            let config = try! SessionConfiguration(argusAPIURL: origin, supabaseURL: origin,
                publicAnonKey: "sb_publishable_synthetic", keychainService: service)
            let controller = try! SessionController(configuration: config, appleChecker: NativeAppleCredentialChecker())
            _auth = StateObject(wrappedValue: ProfileAuthModel(
                configuration: .init(session: config, webURL: origin, captchaURL: origin), controller: controller,
                ageRangeObservation: observation))
        } else {
            _auth = StateObject(wrappedValue: ProfileAuthModel(configuration: nil, controller: nil,
                                                            ageRangeObservation: observation))
        }
    }

    var body: some View {
        Group {
            if CuadraoDesignPreview.isActive {
                CuadraoCanvas()
            } else {
                GuestModeRouter(appearance: $appearance) { ConnectedCuadraoRoot(appearance: $appearance) }
                    .environmentObject(auth)
                    .task {
                        await auth.start()
                        if signupProof {
                            let request = auth.ageRangeObservation.observe()
                            if fixture != "pending" { await request?.value }
                            await auth.authenticate(email: "synthetic@example.test", password: "synthetic-password",
                                captchaToken: "synthetic-captcha", signup: true, language: "es-419", displayName: "")
                        }
                    }
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
