import Foundation

enum CuadraoCopy {
    static func locale(preferredLanguages: [String]) -> Locale {
        for identifier in preferredLanguages {
            switch Locale(identifier: identifier).language.languageCode?.identifier {
            case "en": return Locale(identifier: "en")
            case "es": return Locale(identifier: "es-419")
            default: continue
            }
        }
        return Locale(identifier: "es-419")
    }

    static func isSpanish(preferredLanguages: [String] = Locale.preferredLanguages) -> Bool {
        locale(preferredLanguages: preferredLanguages).language.languageCode?.identifier == "es"
    }

    static func text(_ key: String, spanish: Bool = isSpanish(), _ values: String...) -> String {
        let language = spanish ? "es-419" : "en"
        let bundle = Bundle.main.path(forResource: language, ofType: "lproj")
            .flatMap(Bundle.init(path:)) ?? Bundle.main
        let format = bundle.localizedString(forKey: key, value: nil, table: nil)
        guard !values.isEmpty else { return format.replacingOccurrences(of: "%%", with: "%") }
        return String(format: format, locale: Locale(identifier: language), arguments: values)
    }
}
