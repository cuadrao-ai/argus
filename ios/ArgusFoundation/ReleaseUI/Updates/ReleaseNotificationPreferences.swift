import SwiftUI

struct ReleaseNotificationPreferences: View {
    let permission: ReleasePushPermission
    let spanish: Bool
    let requestPermission: () -> Void
    let openSettings: () -> Void

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                Text(CuadraoCopy.text("copy.releaseNotificationPreferences.b1bbe9526b", spanish: spanish)).font(CuadraoTypography.feature)
                Text(CuadraoCopy.text("copy.releaseNotificationPreferences.960997d9bb", spanish: spanish))
                    .font(CuadraoTypography.body)
                VStack(alignment: .leading, spacing: 8) {
                    Label(CuadraoCopy.text("copy.cuadraoVoiceBar.50a58652a9", spanish: spanish), systemImage: "bell").font(CuadraoTypography.caption)
                    Text(ReleaseSafePushCopy.title(spanish: spanish)).font(.body.weight(.semibold))
                    Text(ReleaseSafePushCopy.body(spanish: spanish)).font(CuadraoTypography.supporting)
                }.padding(20).frame(maxWidth: .infinity, alignment: .leading)
                    .background(WelcomePalette.surface, in: RoundedRectangle(cornerRadius: 20))
                    .accessibilityIdentifier("updates-safe-push-preview")
                Text(CuadraoCopy.text("copy.releaseNotificationPreferences.f7677f4d24", spanish: spanish))
                    .font(CuadraoTypography.supporting).foregroundStyle(.secondary)
                switch permission {
                case .unavailable:
                    Text(CuadraoCopy.text("copy.releaseNotificationPreferences.af336da3d0", spanish: spanish))
                case .notDetermined:
                    Button(CuadraoCopy.text("copy.releaseNotificationPreferences.98eafe0642", spanish: spanish), action: requestPermission)
                        .frame(minHeight: 44).accessibilityIdentifier("updates-enable-push")
                case .requesting:
                    ProgressView(CuadraoCopy.text("copy.releaseNotificationPreferences.825e2ddb68", spanish: spanish))
                case .authorized:
                    Label(CuadraoCopy.text("copy.releaseNotificationPreferences.618a1dc03a", spanish: spanish), systemImage: "checkmark")
                    settingsButton
                case .denied:
                    Text(CuadraoCopy.text("copy.releaseNotificationPreferences.bc60ae6852", spanish: spanish))
                    settingsButton
                }
            }.frame(maxWidth: .infinity, alignment: .leading).padding(24)
        }.background(WelcomePalette.background).foregroundStyle(WelcomePalette.ink)
            .navigationTitle(CuadraoCopy.text("copy.releaseNotificationPreferences.e66eecd5cf", spanish: spanish)).navigationBarTitleDisplayMode(.inline)
    }
    private var settingsButton: some View {
        Button(CuadraoCopy.text("copy.releaseNotificationPreferences.32576cf48b", spanish: spanish), action: openSettings)
            .frame(minHeight: 44).accessibilityIdentifier("updates-open-settings")
    }
}
