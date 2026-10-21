import SwiftUI

struct CuadraoLiveVoiceCanvas: View {
    let chat: CuadraoChatPreview
    let spanish: Bool
    let keyboard: () -> Void
    let showProposal: (() -> Void)?
    @Environment(\.dynamicTypeSize) private var typeSize
    @State private var choosingVoice = false
    @State private var previewDetails = false
    private var es: Bool { spanish }
    private var voice: CuadraoVoicePreview { chat.voice }

    var body: some View {
        GeometryReader { geometry in
            ZStack {
                WelcomePalette.background.ignoresSafeArea()
                CuadraoVoiceSea(voice: voice).ignoresSafeArea()
                ScrollView {
                    VStack(spacing: 0) {
                        header
                        Spacer(minLength: 64)
                        status
                        Spacer(minLength: 64)
                        CuadraoVoiceWave(voice: voice).padding(.bottom, 36)
                        controls
                        previewNotice.padding(.top, 16).padding(.bottom, 16)
                    }.frame(minHeight: geometry.size.height)
                }.scrollBounceBehavior(.basedOnSize)
            }
        }.foregroundStyle(WelcomePalette.ink).tint(WelcomePalette.pine)
            .simultaneousGesture(DragGesture(minimumDistance: 24).onEnded { value in
                // Keep system-edge gestures and accessibility scrolling intact.
                guard !typeSize.isAccessibilitySize, value.startLocation.y > 64,
                      value.translation.height > 120,
                      value.translation.height > abs(value.translation.width) * 2 else { return }
                voice.presentation = .compact
            })
            .sheet(isPresented: $choosingVoice) { CuadraoVoicePicker(spanish: es) }
            .confirmationDialog(CuadraoCopy.text("copy.cuadraoLiveVoiceCanvas.4f792b334d", spanish: es),
                                isPresented: $previewDetails, titleVisibility: .visible) {
                if let showProposal { Button(CuadraoCopy.text("copy.cuadraoLiveVoiceCanvas.1616d5ca95", spanish: es), action: showProposal) }
                Button(CuadraoCopy.text("copy.cuadraoLiveVoiceCanvas.dc97fb4fd5", spanish: es)) { voice.phase = .listening }
                Button(CuadraoCopy.text("copy.cuadraoLiveVoiceCanvas.428292a8de", spanish: es)) { voice.phase = .speaking }
            } message: {
                Text(CuadraoCopy.text("copy.cuadraoLiveVoiceCanvas.df6dea0319", spanish: es))
            }
    }

    private var status: some View {
        VStack(spacing: 16) {
            Text(voice.status(es)).font(.title2.weight(.medium))
                .multilineTextAlignment(.center).contentTransition(.opacity)
                .accessibilityIdentifier("voice-status")
            if voice.phase == .speaking {
                Button(CuadraoCopy.text("copy.cuadraoLiveVoiceCanvas.c44c21e284", spanish: es)) { voice.interrupt() }
                    .font(.subheadline).frame(minHeight: 44)
                    .accessibilityIdentifier("voice-interrupt")
            }
            if chat.temporary {
                Label { Text(CuadraoCopy.text("copy.cuadraoLiveVoiceCanvas.9d6f2322f8", spanish: es)) } icon: {
                    Image("CuadraoTemporaryChat").resizable().scaledToFit().frame(width: 16, height: 16)
                }.font(.footnote).foregroundStyle(.secondary)
            }
        }.frame(maxWidth: .infinity).padding(.horizontal, 28)
    }

    private var header: some View {
        HStack {
            Button { voice.presentation = .compact } label: {
                Image(systemName: "chevron.down").font(.system(size: 18, weight: .medium))
                    .frame(width: 48, height: 48)
                    .background(.ultraThinMaterial, in: Circle())
            }.buttonStyle(.plain).accessibilityLabel(CuadraoCopy.text("copy.cuadraoLiveVoiceCanvas.dc2266e1fa", spanish: es))
                .accessibilityIdentifier("voice-minimize")
            Spacer()
            Text(CuadraoCopy.text("copy.cuadraoLiveVoiceCanvas.d6c2cf736d", spanish: CuadraoCopy.isSpanish())).font(.subheadline.weight(.medium)).foregroundStyle(.secondary)
            Spacer()
            if CuadraoDesignPreview.voiceSelection {
                Button { choosingVoice = true } label: {
                    Image(systemName: "slider.horizontal.3").font(.system(size: 20))
                        .frame(width: 48, height: 48)
                        .background(.ultraThinMaterial, in: Circle())
                }.buttonStyle(.plain).accessibilityLabel(CuadraoCopy.text("copy.cuadraoLiveVoiceCanvas.a6bf36ec17", spanish: es))
                    .accessibilityIdentifier("voice-choose")
            } else {
                // Keeps the title centered while voice selection is off.
                Color.clear.frame(width: 48, height: 48).accessibilityHidden(true)
            }
        }.padding(.horizontal, 24).padding(.top, 12)
    }

    private var controls: some View {
        HStack(spacing: 16) {
            control(voice.muted ? "mic.slash" : "mic",
                    voice.muted ? (CuadraoCopy.text("copy.cuadraoLiveVoiceCanvas.a21d2ac6af", spanish: es)) : (CuadraoCopy.text("copy.cuadraoLiveVoiceCanvas.978e185dcc", spanish: es)),
                    id: "voice-mute", selected: voice.muted) { voice.muted.toggle() }
            control("keyboard", CuadraoCopy.text("copy.cuadraoLiveVoiceCanvas.7335591a86", spanish: es), id: "voice-keyboard", action: keyboard)
            control("xmark", CuadraoCopy.text("copy.cuadraoLiveVoiceCanvas.5c003a60ac", spanish: es), id: "voice-end") { voice.end() }
        }.padding(8).background(.regularMaterial, in: Capsule())
            .overlay { Capsule().stroke(WelcomePalette.separator.opacity(0.5), lineWidth: 0.5) }
    }

    private var previewNotice: some View {
        Button { previewDetails = true } label: {
            Label(CuadraoCopy.text("copy.cuadraoLiveVoiceCanvas.71e4cb7a4c", spanish: es), systemImage: "info.circle")
                .font(.caption).foregroundStyle(.secondary).frame(minHeight: 44).contentShape(Rectangle())
        }.buttonStyle(.plain).accessibilityIdentifier("voice-preview-info")
    }

    private func control(_ symbol: String, _ title: String, id: String,
                         selected: Bool = false, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: symbol).font(.system(size: 22, weight: .regular))
                .frame(width: 52, height: 52)
                .background(selected ? WelcomePalette.sage : Color.clear, in: Circle()).contentShape(Rectangle())
        }.buttonStyle(.plain).accessibilityIdentifier(id)
            .accessibilityLabel(title).accessibilityValue(selected ? (CuadraoCopy.text("copy.cuadraoLiveVoiceCanvas.1cebfbcae0", spanish: es)) : "")
    }
}
