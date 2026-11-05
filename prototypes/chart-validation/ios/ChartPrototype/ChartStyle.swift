import SwiftUI
import CoreText

/// Prototype-only rendering of DESIGN.md palette and type, with licensed font
/// bytes reused from the unmerged #729 foundation reference. No shell dependency.
enum ChartStyle {
    static let background = adaptive(light: 0xFFFFFF, dark: 0x191C1F)
    static let surface = adaptive(light: 0xF4F4F4, dark: 0x24282C)
    static let ink = adaptive(light: 0x191C1F, dark: 0xF4F4F5)
    static let secondary = adaptive(light: 0x505A63, dark: 0xB4BBC2)
    static let grid = adaptive(light: 0xE7E7E9, dark: 0x303438)
    private struct SeriesPalette: Decodable {
        struct Theme: Decodable { let actual: String; let projected: String }
        let light: Theme
        let dark: Theme
    }
    private static let palette: SeriesPalette = {
        let url = Bundle.main.url(forResource: "visual-style", withExtension: "json")!
        return try! JSONDecoder().decode(SeriesPalette.self, from: Data(contentsOf: url))
    }()
    private static func hex(_ value: String) -> UInt32 { UInt32(value.dropFirst(), radix: 16)! }
    static let actual = adaptive(light: hex(palette.light.actual), dark: hex(palette.dark.actual))
    static let projected = adaptive(light: hex(palette.light.projected), dark: hex(palette.dark.projected))

    static func registerFonts() {
        for name in ["Inter-Regular", "Inter-Medium", "SpaceGrotesk-Medium"] {
            guard let url = Bundle.main.url(forResource: name, withExtension: "ttf") else {
                assertionFailure("Missing bundled font: \(name)"); continue
            }
            CTFontManagerRegisterFontsForURL(url as CFURL, .process, nil)
            assert(UIFont(name: name, size: 16) != nil, "Font registration failed: \(name)")
        }
    }
    static func body(_ size: CGFloat = 16, relativeTo style: Font.TextStyle = .body) -> Font {
        .custom("Inter-Regular", size: size, relativeTo: style)
    }
    static func display(_ size: CGFloat = 24, relativeTo style: Font.TextStyle = .title2) -> Font {
        .custom("SpaceGrotesk-Medium", size: size, relativeTo: style)
    }
    private static func adaptive(light: UInt32, dark: UInt32) -> Color {
        Color(uiColor: UIColor { traits in
            let hex = traits.userInterfaceStyle == .dark ? dark : light
            return UIColor(red: CGFloat((hex >> 16) & 255) / 255,
                           green: CGFloat((hex >> 8) & 255) / 255,
                           blue: CGFloat(hex & 255) / 255, alpha: 1)
        })
    }
}

struct ChartPillStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(ChartStyle.body(14, relativeTo: .subheadline))
            .padding(.horizontal, 12)
            .frame(maxWidth: .infinity, minHeight: 44)
            .foregroundStyle(ChartStyle.ink)
            .background(ChartStyle.surface, in: Capsule())
            .opacity(configuration.isPressed ? 0.7 : 1)
    }
}
