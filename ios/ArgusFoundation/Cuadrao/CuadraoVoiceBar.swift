import SwiftUI

struct CuadraoVoiceBar: View {
    let voice: CuadraoVoicePreview
    let spanish: Bool
    var embedded = false

    var body: some View {
        if embedded {
            content
        } else {
            content
                .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 24))
                .overlay { RoundedRectangle(cornerRadius: 24).stroke(WelcomePalette.separator, lineWidth: 0.5) }
                .padding(.horizontal, 20).padding(.bottom, 8)
        }
    }

    private var content: some View {
        HStack(spacing: 0) {
            Button { voice.presentation = .expanded } label: {
                HStack(spacing: 10) {
                    CuadraoVoiceWave(voice: voice, compact: true)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(voice.resting ? (CuadraoCopy.text("copy.cuadraoVoiceBar.2dc881f5a9", spanish: spanish)) : voice.status(spanish)).font(.subheadline.weight(.medium)).lineLimit(1)
                        Text(CuadraoCopy.text("copy.cuadraoVoiceBar.50a58652a9", spanish: spanish)).font(.caption).foregroundStyle(.secondary)
                    }
                    Spacer(minLength: 0)
                    Image(systemName: "arrow.up.left.and.arrow.down.right")
                        .font(.system(size: 12)).foregroundStyle(.secondary).padding(.trailing, 10)
                }.padding(.leading, embedded ? 4 : 16).frame(minHeight: 54).contentShape(Rectangle())
            }.buttonStyle(.plain).accessibilityLabel(CuadraoCopy.text("copy.cuadraoVoiceBar.e87c02dbb5", spanish: spanish))
                .accessibilityValue(voice.status(spanish))
                .accessibilityIdentifier("voice-expand")
            Button { voice.muted.toggle() } label: {
                Image(systemName: voice.muted ? "mic.slash" : "mic").frame(width: 44, height: 48).contentShape(Rectangle())
            }.buttonStyle(.plain).accessibilityIdentifier("voice-mute-compact").accessibilityLabel(voice.muted ? (CuadraoCopy.text("copy.cuadraoVoiceBar.a21d2ac6af", spanish: spanish)) : (CuadraoCopy.text("copy.cuadraoVoiceBar.978e185dcc", spanish: spanish)))
            Button { voice.end() } label: {
                Image(systemName: "xmark").frame(width: 44, height: 48).contentShape(Rectangle())
            }.buttonStyle(.plain).accessibilityLabel(CuadraoCopy.text("copy.cuadraoVoiceBar.5c003a60ac", spanish: spanish))
                .accessibilityIdentifier("voice-end-compact")
        }.foregroundStyle(WelcomePalette.ink)
    }
}
