import SwiftUI

/// A local preview preference, isolated from the connected Argus app settings.
struct CuadraoAppearancePicker: View {
    static let storageKey = "cuadrao.design.appearance"
    let spanish: Bool
    @AppStorage(Self.storageKey) private var selection = AppearancePreference.light

    var body: some View {
        CuadraoAppearanceChoices(spanish: spanish, selection: $selection)
    }
}

struct CuadraoAppearanceChoices: View {
    let spanish: Bool
    @Binding var selection: AppearancePreference
    @Environment(\.dynamicTypeSize) private var typeSize

    var body: some View {
        let layout = typeSize.isAccessibilitySize ? AnyLayout(VStackLayout(spacing: 16)) : AnyLayout(HStackLayout(spacing: 12))
        layout {
            ForEach(AppearancePreference.allCases, id: \.self) { option in
                Button { selection = option } label: {
                    VStack(spacing: 10) {
                        preview(option)
                            .frame(height: 76)
                            .clipShape(RoundedRectangle(cornerRadius: 11))
                            .padding(4)
                            .overlay {
                                RoundedRectangle(cornerRadius: 15)
                                    .stroke(selection == option ? WelcomePalette.pine : Color.clear, lineWidth: 2)
                            }
                            .overlay(alignment: .topTrailing) {
                                Image(systemName: "checkmark.circle.fill")
                                    .font(.caption.weight(.semibold))
                                    .foregroundStyle(WelcomePalette.pine, WelcomePalette.background)
                                    .padding(7).opacity(selection == option ? 1 : 0)
                                    .accessibilityHidden(true)
                            }
                        Text(title(option)).font(.subheadline)
                            .foregroundStyle(selection == option ? WelcomePalette.pine : Color.secondary)
                    }.frame(maxWidth: .infinity).contentShape(Rectangle())
                }.buttonStyle(.plain)
                    .accessibilityLabel(title(option))
                    .accessibilityAddTraits(selection == option ? .isSelected : [])
                    .accessibilityIdentifier("cuadrao.appearance.\(option.rawValue)")
            }
        }.padding(.vertical, 8)
    }

    private func title(_ option: AppearancePreference) -> String {
        switch option {
        case .light: CuadraoCopy.text("copy.cuadraoAppearancePicker.a806b3e338", spanish: spanish)
        case .dark: CuadraoCopy.text("copy.cuadraoAppearancePicker.d0713df468", spanish: spanish)
        case .system: CuadraoCopy.text("copy.cuadraoAppearancePicker.403824e29d", spanish: spanish)
        }
    }

    @ViewBuilder private func preview(_ option: AppearancePreference) -> some View {
        switch option {
        case .light: miniature(dark: false)
        case .dark: miniature(dark: true)
        case .system:
            miniature(dark: false).overlay {
                miniature(dark: true).clipShape(AppearanceDiagonal())
            }
        }
    }

    private func miniature(dark: Bool) -> some View {
        let ink = dark ? Color(white: 0.80) : Color(white: 0.35)
        let accent = dark ? Color(red: 0.67, green: 0.83, blue: 0.75) : Color(red: 0.16, green: 0.29, blue: 0.25)
        return VStack(alignment: .leading, spacing: 7) {
            HStack(spacing: 3) {
                RoundedRectangle(cornerRadius: 2).fill(accent).frame(width: 9, height: 9)
                Capsule().fill(ink.opacity(0.55)).frame(width: 22, height: 3)
                Spacer(minLength: 0)
            }
            Capsule().fill(ink).frame(width: 35, height: 4)
            HStack(spacing: 4) {
                RoundedRectangle(cornerRadius: 3).fill(accent.opacity(0.15)).frame(width: 13, height: 13)
                VStack(alignment: .leading, spacing: 3) {
                    Capsule().fill(ink.opacity(0.6)).frame(width: 25, height: 2)
                    Capsule().fill(ink.opacity(0.25)).frame(width: 18, height: 2)
                }
            }
        }.padding(10).frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
            .background(dark ? Color(white: 0.105) : Color.white)
            .accessibilityHidden(true)
    }
}

private struct AppearanceDiagonal: Shape {
    func path(in rect: CGRect) -> Path {
        Path { path in
            path.move(to: CGPoint(x: rect.maxX, y: rect.minY))
            path.addLine(to: CGPoint(x: rect.maxX, y: rect.maxY))
            path.addLine(to: CGPoint(x: rect.minX, y: rect.maxY))
            path.closeSubpath()
        }
    }
}
