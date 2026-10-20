import Foundation

/// All legal surfaces read this owner. Configuration remains disabled until app-policy approval.
struct CuadraoLegalURLs: Equatable {
    var privacy: URL?
    var terms: URL?
    var dataDeletion: URL?

    static let published = configured(info: Bundle.main.infoDictionary ?? [:])

    static func configured(info: [String: Any]) -> CuadraoLegalURLs {
        let enabled = info["ARGUS_CUADRAO_LEGAL_LINKS_ENABLED"]
        guard (enabled as? Bool == true) || (enabled as? String)?.lowercased() == "true" else {
            return CuadraoLegalURLs()
        }
        return CuadraoLegalURLs(privacy: page("ARGUS_CUADRAO_PRIVACY_URL", info: info),
                               terms: page("ARGUS_CUADRAO_TERMS_URL", info: info))
    }

    /// The founder-approved under-18 refusal may link to configured terms while other legal surfaces stay gated.
    static func ageGateTerms(info: [String: Any] = Bundle.main.infoDictionary ?? [:]) -> URL? {
        page("ARGUS_CUADRAO_TERMS_URL", info: info)
    }

    private static func page(_ key: String, info: [String: Any]) -> URL? {
        guard let value = info[key] as? String, let url = URL(string: value),
              url.scheme == "https", let host = url.host, !host.isEmpty,
              url.user == nil, url.password == nil, url.fragment == nil else { return nil }
        return url
    }

    /// Debug builds only: fills the owner with test pages so a UI test can see the links appear.
    static let testArgument = "--cuadrao-legal-test-urls"

    static var current: CuadraoLegalURLs { current(arguments: ProcessInfo.processInfo.arguments) }

    static func current(arguments: [String]) -> CuadraoLegalURLs {
        #if DEBUG
        if arguments.contains("--cuadrao-legal-test-terms-only") {
            return CuadraoLegalURLs(terms: URL(string: "https://legal.example.test/terminos"))
        }
        if arguments.contains("--cuadrao-legal-test-privacy-only") {
            return CuadraoLegalURLs(privacy: URL(string: "https://legal.example.test/privacidad"))
        }
        if arguments.contains(testArgument) {
            return CuadraoLegalURLs(privacy: URL(string: "https://legal.example.test/privacidad"),
                                    terms: URL(string: "https://legal.example.test/terminos"),
                                    dataDeletion: URL(string: "https://legal.example.test/eliminar-datos"))
        }
        #endif
        return published
    }

    var hasPages: Bool { privacy != nil || terms != nil }

    /// Sign-up states the acceptance sentence only when the reader can open both documents it names.
    var hasTermsAndPrivacy: Bool { privacy != nil && terms != nil }
}
