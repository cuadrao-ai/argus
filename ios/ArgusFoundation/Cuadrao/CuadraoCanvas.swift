import SwiftUI

enum WelcomePalette {
    static let adaptsToAppearance = true

    static let pine = adaptive(
                               UIColor(red: 0.16, green: 0.29, blue: 0.25, alpha: 1),
                               UIColor(red: 0.67, green: 0.83, blue: 0.75, alpha: 1))
    static let moneyInput = adaptive(
                                     UIColor(red: 0.18, green: 0.47, blue: 0.40, alpha: 1),
                                     UIColor(red: 0.67, green: 0.83, blue: 0.75, alpha: 1))
    static let sage = adaptive(
                               UIColor(red: 0.91, green: 0.93, blue: 0.91, alpha: 1),
                               UIColor(red: 0.17, green: 0.22, blue: 0.20, alpha: 1))
    static let overlap = adaptive(
                                  UIColor(red: 0.25, green: 0.38, blue: 0.33, alpha: 1),
                                  UIColor(red: 0.37, green: 0.53, blue: 0.44, alpha: 1))
    static let sunshine = Color(red: 0.67, green: 0.43, blue: 0.13)
    static let bloom = Color(red: 0.48, green: 0.40, blue: 0.64)
    static let owedNegative = adaptive(
                                       UIColor(red: 0.68, green: 0.36, blue: 0.26, alpha: 1),
                                       UIColor(red: 0.94, green: 0.63, blue: 0.48, alpha: 1))
    static let clay = Color(red: 0.68, green: 0.36, blue: 0.26)
    static let background = adaptive(.white, UIColor(white: 0.10, alpha: 1))
    static let surface = adaptive(UIColor(white: 0.965, alpha: 1), UIColor(white: 0.14, alpha: 1))
    static let ink = adaptive(UIColor(white: 0.08, alpha: 1), UIColor(white: 0.94, alpha: 1))
    static let onAccent = adaptive(.white, UIColor(red: 0.08, green: 0.15, blue: 0.12, alpha: 1))
    static let separator: Color = adaptsToAppearance ? Color(uiColor: .separator).opacity(0.45) : Color(white: 0.85)
    static let border: Color = adaptsToAppearance ? Color(uiColor: .separator) : Color(white: 0.80)
    static let disabledInk: Color = adaptsToAppearance ? Color.secondary : Color(white: 0.43)

    private static func adaptive(_ light: UIColor, _ dark: UIColor) -> Color {
        return Color(uiColor: UIColor { $0.userInterfaceStyle == .dark ? dark : light })
    }
}

/// The native visual canvas. Add only the UI elements selected during design review.
struct CuadraoCanvas: View {
    static var standalonePreview: Bool { CuadraoDesignPreview.standalone }

    private let language = "es"

    private var spanish: Bool { language == "es" }

    var body: some View {
        if ProcessInfo.processInfo.arguments.contains("--design-gallery") {
            CuadraoDesignGallery()
        } else if Self.standalonePreview || ProcessInfo.processInfo.arguments.contains("--cuadrao-home") {
            CuadraoHomeCanvas()
        } else {
        NavigationStack {
            welcome
                .toolbar(.hidden, for: .navigationBar)
        }
        .tint(WelcomePalette.ink)
        }
    }

    private var welcome: some View {
        GeometryReader { geometry in
            ScrollView {
                VStack(spacing: 0) {
                    Spacer(minLength: 32)
                    CuadraoWelcomeLockup()

                    Spacer(minLength: 40)

                    VStack(spacing: 12) {
                        NavigationLink {
                            CuadraoCreateAccount(spanish: spanish)
                        } label: {
                            Text(spanish ? "Crear cuenta" : "Create account")
                                .font(.system(.body, weight: .semibold))
                                .multilineTextAlignment(.center)
                                .padding(.vertical, 14)
                                .frame(maxWidth: .infinity, minHeight: 56)
                                .foregroundStyle(WelcomePalette.onAccent)
                                .background(WelcomePalette.pine, in: RoundedRectangle(cornerRadius: 16))
                        }.buttonStyle(.plain)

                        NavigationLink {
                            CuadraoCreateAccount(spanish: spanish, signingIn: true)
                        } label: {
                            Text(spanish ? "Iniciar sesión" : "Sign in")
                                .font(.system(.body, weight: .semibold))
                                .multilineTextAlignment(.center)
                                .padding(.vertical, 14)
                                .frame(maxWidth: .infinity, minHeight: 56)
                                .overlay {
                                    RoundedRectangle(cornerRadius: 16)
                                        .stroke(WelcomePalette.border, lineWidth: 1)
                                }
                                .contentShape(Rectangle())
                        }.buttonStyle(.plain)
                    }.padding(.bottom, 28)
                }
                .padding(.horizontal, 28)
                .frame(minHeight: geometry.size.height, alignment: .topLeading)
            }.scrollIndicators(.hidden)
        }
        .background(WelcomePalette.brandPaper.ignoresSafeArea())
        .foregroundStyle(WelcomePalette.ink)

    }
}

/// The large decorative mark on the invitation pages: the approved Cuadrao mark (tile-less; light-surface colours on
/// light, Marketing's dark-surface mark on dark), in the 208 pt frame the provisional squares used.
struct WelcomeSquares: View {
    var body: some View {
        Image("CuadraoMark")
            .resizable()
            .scaledToFit()
            .frame(maxWidth: .infinity)
            .frame(height: 208)
            .accessibilityHidden(true)
    }
}

#Preview("Cuadrao · Welcome") {
    CuadraoCanvas().preferredColorScheme(.light)
}
