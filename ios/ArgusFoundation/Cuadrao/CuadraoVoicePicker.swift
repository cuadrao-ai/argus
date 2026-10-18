import SwiftUI
import AVFoundation

// A curated preview subset of xAI's documented voices. Preference has one durable owner.
enum CuadraoVoiceOption: String, CaseIterable, Identifiable {
    case ara, eve, sal
    static let preferenceKey = "cuadrao.design.voice"
    var id: String { rawValue }
    var name: String { rawValue.capitalized }
    func detail(_ es: Bool) -> String {
        switch self {
        case .ara: CuadraoCopy.text("copy.cuadraoVoicePicker.a0ca2caed3", spanish: es)
        case .eve: CuadraoCopy.text("copy.cuadraoVoicePicker.ffc9eab0c9", spanish: es)
        case .sal: CuadraoCopy.text("copy.cuadraoVoicePicker.564f4b15d8", spanish: es)
        }
    }
}

struct CuadraoVoicePreference: View {
    let spanish: Bool
    @AppStorage(CuadraoVoiceOption.preferenceKey) private var selected = CuadraoVoiceOption.ara
    @State private var choosing = false
    var body: some View {
        Button { choosing = true } label: {
            HStack {
                Text(CuadraoCopy.text("copy.cuadraoVoicePicker.d0a8b9cb41", spanish: spanish))
                Spacer()
                Text(selected.name).foregroundStyle(.secondary)
                Image(systemName: "chevron.right").font(.caption).foregroundStyle(.tertiary)
            }.foregroundStyle(.primary).frame(minHeight: 44)
        }.accessibilityIdentifier("voice-preference").accessibilityValue(selected.name)
            .sheet(isPresented: $choosing) { CuadraoVoicePicker(spanish: spanish) }
    }
}

struct CuadraoVoicePicker: View {
    let spanish: Bool
    @AppStorage(CuadraoVoiceOption.preferenceKey) private var selected = CuadraoVoiceOption.ara
    @State private var sample = CuadraoVoiceSamplePlayer()
    @Environment(\.dismiss) private var dismiss
    @Environment(\.scenePhase) private var scenePhase
    @Environment(\.dynamicTypeSize) private var typeSize

    var body: some View {
        ScrollView {
            VStack(spacing: 12) {
                header
                TabView(selection: Binding(get: { selected }, set: choose)) {
                    ForEach(CuadraoVoiceOption.allCases) { option in
                        VStack(spacing: 8) {
                            Text(option.name).font(.title2.weight(.semibold))
                            Text(option.detail(spanish)).font(.subheadline)
                                .foregroundStyle(.secondary).multilineTextAlignment(.center)
                        }.padding(.horizontal, 16).tag(option)
                    }
                }
                .tabViewStyle(.page(indexDisplayMode: .never))
                .frame(height: typeSize.isAccessibilitySize ? 180 : 86)
                .accessibilityIdentifier("voice-carousel")
                pages
                sampleControl
                Text(CuadraoCopy.text("copy.cuadraoVoicePicker.17319f2ff9", spanish: spanish))
                    .font(.footnote).foregroundStyle(.secondary).multilineTextAlignment(.center)
                    .padding(.horizontal, 20)
                if sample.failed {
                    Text(CuadraoCopy.text("copy.cuadraoVoicePicker.bd5310a64e", spanish: spanish))
                        .font(.footnote).foregroundStyle(.secondary)
                }
            }.padding(.horizontal, 24).padding(.top, 16).padding(.bottom, 24)
        }
        .scrollBounceBehavior(.basedOnSize)
        .background(WelcomePalette.background).foregroundStyle(WelcomePalette.ink)
        .tint(WelcomePalette.pine)
        .presentationDetents(typeSize.isAccessibilitySize ? [.large] : [.height(360), .large])
        .presentationDragIndicator(.visible).presentationCornerRadius(32)
        .onDisappear { sample.stop() }
        .onChange(of: scenePhase) { _, phase in if phase != .active { sample.stop() } }
    }

    private var header: some View {
        HStack {
            Text(CuadraoCopy.text("copy.cuadraoVoicePicker.a6bf36ec17", spanish: spanish))
                .font(.subheadline.weight(.medium)).foregroundStyle(.secondary)
            Spacer()
            Button { sample.stop(); dismiss() } label: {
                Image(systemName: "checkmark").font(.body.weight(.semibold))
                    .frame(width: 44, height: 44)
                    .background(WelcomePalette.surface, in: Circle())
            }.accessibilityLabel(CuadraoCopy.text("copy.guestClaimModel.bd6b05a681", spanish: spanish))
                .accessibilityIdentifier("voice-picker-done")
        }
    }

    private var pages: some View {
        HStack(spacing: 0) {
            ForEach(CuadraoVoiceOption.allCases) { option in
                Button { choose(option) } label: {
                    Circle().fill(selected == option ? WelcomePalette.pine : Color.secondary.opacity(0.3))
                        .frame(width: 7, height: 7).frame(width: 44, height: 44)
                        .contentShape(Rectangle())
                }.buttonStyle(.plain)
                    .accessibilityLabel(option.name + ", " + option.detail(spanish))
                    .accessibilityIdentifier("voice-option-" + option.rawValue)
                    .accessibilityAddTraits(selected == option ? .isSelected : [])
            }
        }
    }

    private var sampleControl: some View {
        Button { sample.toggle(selected) } label: {
            HStack(spacing: 8) {
                Image(systemName: sample.playing == selected ? "stop.fill" : "play.fill")
                    .font(.system(size: 12, weight: .semibold))
                Text(sample.playing == selected
                     ? (CuadraoCopy.text("copy.cuadraoVoicePicker.9ea5a91e8d", spanish: spanish))
                     : (CuadraoCopy.text("copy.cuadraoVoicePicker.cd3f844181", spanish: spanish)))
                    .font(.subheadline.weight(.medium))
            }.frame(minWidth: 180, minHeight: 44)
                .background(WelcomePalette.surface, in: Capsule())
        }.buttonStyle(.plain)
            .accessibilityLabel((sample.playing == selected
                ? (CuadraoCopy.text("copy.cuadraoVoicePicker.b77398b1da", spanish: spanish))
                : (CuadraoCopy.text("copy.cuadraoVoicePicker.fea399e9df", spanish: spanish))) + selected.name)
            .accessibilityIdentifier("voice-sample")
    }

    private func choose(_ option: CuadraoVoiceOption) {
        guard selected != option else { return }
        sample.stop()
        selected = option
        sample.toggle(option)
    }
}

@MainActor @Observable final class CuadraoVoiceSamplePlayer: NSObject, AVAudioPlayerDelegate {
    private(set) var playing: CuadraoVoiceOption?
    private(set) var failed = false
    @ObservationIgnored private var player: AVAudioPlayer?
    func toggle(_ option: CuadraoVoiceOption) {
        let wasPlaying = playing == option
        stop(); failed = false
        guard !wasPlaying else { return }
        do {
            guard let url = Bundle.main.url(forResource: "voice_" + option.rawValue, withExtension: "mp3") else {
                failed = true; return
            }
            try AVAudioSession.sharedInstance().setCategory(.playback, mode: .spokenAudio, options: [.duckOthers])
            try AVAudioSession.sharedInstance().setActive(true)
            let audio = try AVAudioPlayer(contentsOf: url)
            audio.delegate = self
            player = audio
            guard audio.play() else { failed = true; stop(); return }
            playing = option
        } catch { failed = true; stop() }
    }
    func stop() {
        player?.stop(); player = nil; playing = nil
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
    }
    nonisolated func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully flag: Bool) {
        Task { @MainActor [weak self] in self?.stop() }
    }
}
