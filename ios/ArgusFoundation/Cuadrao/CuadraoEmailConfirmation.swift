import SwiftUI

struct CuadraoEmailConfirmation: View {
    let spanish: Bool
    let email: String
    @Environment(\.dismiss) private var dismiss
    @State private var showingHelp = false

    var body: some View {
        GeometryReader { geometry in
            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    Image(systemName: "envelope.badge.shield.half.filled")
                        .font(.system(size: 32, weight: .light))
                        .foregroundStyle(WelcomePalette.pine)
                        .frame(width: 72, height: 72)
                        .background(WelcomePalette.sage, in: RoundedRectangle(cornerRadius: 22))
                        .accessibilityHidden(true)
                        .padding(.bottom, 28)
                    RegistrationHeading(
                        title: CuadraoCopy.text("copy.connectedCuadraoAuth.2096f1a523", spanish: spanish),
                        detail: CuadraoCopy.text("copy.connectedCuadraoAuth.1132cc3fad", spanish: spanish))
                    Text(email)
                        .font(.body.weight(.semibold))
                        .textSelection(.enabled)
                        .padding(.top, 10)
                    Button(CuadraoCopy.text("copy.connectedCuadraoAuth.2883c17995", spanish: spanish)) { dismiss() }
                        .font(.subheadline.weight(.medium))
                        .foregroundStyle(WelcomePalette.pine)
                        .frame(minHeight: 44)
                        .padding(.top, 6)
                    Spacer(minLength: 40)
                    Text(CuadraoCopy.text("copy.connectedCuadraoAuth.ab25824af2", spanish: spanish))
                        .font(.body).foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                        .padding(.bottom, 24)
                    NavigationLink {
                        CuadraoEmailSignIn(spanish: spanish, initialEmail: email)
                    } label: {
                        Text(CuadraoCopy.text("copy.connectedCuadraoAuth.93dde646b9", spanish: spanish))
                            .font(.body.weight(.semibold))
                            .frame(maxWidth: .infinity, minHeight: 56)
                            .foregroundStyle(WelcomePalette.onAccent)
                            .background(WelcomePalette.pine, in: RoundedRectangle(cornerRadius: 16))
                    }.buttonStyle(.plain)
                    Button(CuadraoCopy.text("copy.cuadraoEmailConfirmation.0036b29e79", spanish: spanish)) {
                        showingHelp.toggle()
                    }
                    .font(.subheadline)
                    .frame(maxWidth: .infinity, minHeight: 48)
                    .padding(.top, 8)
                    if showingHelp {
                        Text(CuadraoCopy.text("copy.cuadraoEmailConfirmation.8e69c00c3a", spanish: spanish))
                            .font(.footnote).foregroundStyle(.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                            .padding(.top, 8)
                    }
                }
                .padding(.horizontal, 28)
                .padding(.top, 24)
                .padding(.bottom, 20)
                .frame(minHeight: geometry.size.height, alignment: .topLeading)
            }
        }
        .background(WelcomePalette.background.ignoresSafeArea())
        .foregroundStyle(WelcomePalette.ink)
        .navigationTitle("")
        .navigationBarTitleDisplayMode(.inline)

    }
}

#Preview("Email · Confirmation") {
    NavigationStack { CuadraoEmailConfirmation(spanish: true, email: "alex@example.com") }
}
