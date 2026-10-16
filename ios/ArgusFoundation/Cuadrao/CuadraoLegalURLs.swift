import Foundation

/// The one owner of the privacy, terms and data-deletion page URLs. They stay empty until the Cuadrao pages are
/// published (Lucas, 2026-10-15), and a screen shows a legal link only for a URL that is set. Fill `published`
/// when the pages go live; nothing else changes.
struct CuadraoLegalURLs: Equatable {
    var privacy: URL?
    var terms: URL?
    var dataDeletion: URL?

    static let published = CuadraoLegalURLs()

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
