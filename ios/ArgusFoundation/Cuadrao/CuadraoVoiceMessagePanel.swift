import SwiftUI

/// Review stays attached to its conversation, including a trip to another surface.
struct CuadraoVoiceMessagePanel: View {
    let message: CuadraoVoiceMessagePreview
    let spanish: Bool
    private var es: Bool { spanish }
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 10) {
                Image(systemName: "waveform").foregroundStyle(WelcomePalette.pine)
                Text(message.state == .review
                     ? (CuadraoCopy.text("copy.cuadraoVoiceMessagePanel.5f02e4be7b", spanish: es))
                     : (CuadraoCopy.text("copy.cuadraoVoiceMessagePanel.59ad6fe63d", spanish: es)))
                    .font(.subheadline.weight(.medium)).accessibilityIdentifier("voice-message-status")
                Spacer(minLength: 4)
                Text(Duration.seconds(message.duration).formatted(.time(pattern: .minuteSecond)))
                    .monospacedDigit().font(.caption).foregroundStyle(.secondary)
            }
            HStack {
                Button(CuadraoCopy.text("copy.cuadraoVoiceMessagePanel.adac3a9868", spanish: es)) { message.cancel() }
                Spacer()
                if message.state == .review {
                    Button(CuadraoCopy.text("copy.cuadraoVoiceMessagePanel.9318acd61f", spanish: es)) { message.submit() }
                        .accessibilityIdentifier("voice-message-send")
                }
            }.font(.subheadline.weight(.medium)).frame(minHeight: 44)
            Text(message.state == .submitted
                 ? (CuadraoCopy.text("copy.cuadraoVoiceMessagePanel.a384a9a51a", spanish: es))
                 : (CuadraoCopy.text("copy.cuadraoVoiceMessagePanel.78db2b617e", spanish: es)))
                .font(.caption).foregroundStyle(.secondary)
        }.padding(8)
    }
}

struct CuadraoVoiceRecordingOverlay: View {
    let message: CuadraoVoiceMessagePreview
    let spanish: Bool
    @State private var illustration = CuadraoVoicePreview()
    @Environment(\.dynamicTypeSize) private var typeSize
    private var es: Bool { spanish }

    var body: some View {
        ZStack(alignment: .bottom) {
            ZStack {
                if typeSize.isAccessibilitySize { WelcomePalette.background }
                LinearGradient(stops: [.init(color: .clear, location: 0),
                                       .init(color: WelcomePalette.background, location: 0.3),
                                       .init(color: WelcomePalette.background, location: 1)],
                               startPoint: .top, endPoint: .bottom)
                CuadraoVoiceSea(voice: illustration, cancelling: message.cancelArmed)
            }.mask {
                LinearGradient(stops: [.init(color: typeSize.isAccessibilitySize ? .black : .clear, location: 0), .init(color: .black, location: 0.3),
                                       .init(color: .black, location: 1)], startPoint: .top, endPoint: .bottom)
            }.accessibilityHidden(true)
            GeometryReader { geometry in
                ScrollView {
                    recordingContent
                        .frame(width: geometry.size.width)
                        .frame(minHeight: geometry.size.height, alignment: .bottom)
                }.defaultScrollAnchor(typeSize.isAccessibilitySize ? .top : .bottom).scrollBounceBehavior(.basedOnSize)
                    .scrollDisabled(message.held)
            }
        }.accessibilityIdentifier("voice-recording-overlay")
    }

    private var recordingContent: some View {
        VStack(spacing: 22) {
            // Both alternatives keep their measured space throughout the gesture.
            ZStack {
                lockHint.opacity(message.locked ? 0 : 1)
                    .accessibilityHidden(message.locked)
                TimelineView(.periodic(from: .now, by: 1)) { _ in
                    Label(Duration.seconds(message.elapsed()).formatted(.time(pattern: .minuteSecond)), systemImage: "lock.fill")
                        .font(.subheadline.monospacedDigit()).foregroundStyle(WelcomePalette.pine)
                        .accessibilityElement(children: .ignore)
                        .accessibilityLabel(CuadraoCopy.text("copy.cuadraoVoiceMessagePanel.5fe92c9ec9", spanish: es))
                        .accessibilityValue(Duration.seconds(message.elapsed()).formatted(.time(pattern: .minuteSecond)))
                        .accessibilityIdentifier("voice-recording-timer")
                }.opacity(message.locked ? 1 : 0).accessibilityHidden(!message.locked)
            }.frame(maxWidth: .infinity)
            CuadraoVoiceWave(voice: illustration, cancelling: message.cancelArmed)
            ZStack {
                Text(instruction).font(.subheadline.weight(.medium)).multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
                    .foregroundStyle(message.cancelArmed ? Color.red : WelcomePalette.ink)
                    .opacity(message.held ? 1 : 0).accessibilityHidden(!message.held)
                    .accessibilityIdentifier("voice-recording-instruction")
                // Measure the longest hint even when the current hint is shorter.
                Text(holdInstruction)
                    .font(.subheadline.weight(.medium)).multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true).hidden().accessibilityHidden(true)
                recordingActions.opacity(message.held ? 0 : 1)
                    .allowsHitTesting(!message.held).accessibilityHidden(message.held)
            }.frame(maxWidth: .infinity)
            Text(CuadraoCopy.text("copy.cuadraoVoiceMessagePanel.338852a5b2", spanish: es))
                .font(.caption).foregroundStyle(.secondary).multilineTextAlignment(.center)
        }.padding(.horizontal, 28).padding(.top, 24).padding(.bottom, 48)
    }

    private var recordingActions: some View {
        let layout = typeSize.isAccessibilitySize ? AnyLayout(VStackLayout(spacing: 16)) : AnyLayout(HStackLayout(spacing: 24))
        return layout {
            Button(role: .destructive) { message.cancel() } label: {
                Text(CuadraoCopy.text("copy.cuadraoVoiceMessagePanel.62a128b722", spanish: es)).frame(minWidth: 80, minHeight: 48).contentShape(Rectangle())
            }.buttonStyle(.plain).fixedSize(horizontal: false, vertical: true)
                .accessibilityIdentifier("voice-message-cancel")
            Button { message.stop() } label: {
                Label(CuadraoCopy.text("copy.cuadraoVoiceMessagePanel.787445349f", spanish: es), systemImage: "stop.fill")
                    .font(CuadraoTypography.action).fixedSize(horizontal: false, vertical: true)
                    .padding(.horizontal, 22).padding(.vertical, 10).frame(minHeight: 48)
                    .foregroundStyle(WelcomePalette.onAccent)
                    .background(WelcomePalette.pine, in: Capsule())
            }.buttonStyle(.plain).accessibilityIdentifier("voice-message-stop")
        }
    }

    private var lockHint: some View {
        Label(CuadraoCopy.text("copy.cuadraoVoiceMessagePanel.29367aa613", spanish: es), systemImage: "lock.open")
            .font(.footnote.weight(.medium)).fixedSize(horizontal: false, vertical: true)
            .padding(.horizontal, 16).frame(minHeight: 48)
            .background(.regularMaterial, in: Capsule())
            .foregroundStyle(WelcomePalette.pine)
            .opacity(message.cancelArmed ? 0.35 : 1)
            .accessibilityIdentifier("voice-lock-hint")
            .accessibilityLabel(CuadraoCopy.text("copy.cuadraoVoiceMessagePanel.4f69a0d7a8", spanish: es))
    }

    private var instruction: String {
        if message.cancelArmed { return CuadraoCopy.text("copy.cuadraoVoiceMessagePanel.59f2bd6184", spanish: es) }
        if message.locked { return CuadraoCopy.text("copy.cuadraoVoiceMessagePanel.e1091474ef", spanish: es) }
        return holdInstruction
    }

    private var holdInstruction: String {
        CuadraoCopy.text("copy.cuadraoVoiceMessagePanel.8ff3dc53c9", spanish: es)
    }
}
