import Observation

/// Local presentation only: no microphone, provider session, audio or financial actions.
@Observable final class CuadraoVoicePreview {
    enum Phase { case listening, speaking }
    enum Presentation { case expanded, compact, keyboard }
    private(set) var active = false
    var presentation = Presentation.expanded
    var phase = Phase.listening
    var muted = false

    func start() {
        guard !active else { presentation = .expanded; return }
        active = true; muted = false; phase = .listening; presentation = .expanded
    }
    func end() { active = false; muted = false; phase = .listening; presentation = .expanded }
    func interrupt() { phase = .listening }
    var resting: Bool { muted && phase == .listening }
    func status(_ es: Bool) -> String {
        if phase == .speaking { return CuadraoCopy.text("copy.cuadraoVoicePreview.00f18b637b", spanish: es) }
        return muted ? (CuadraoCopy.text("copy.cuadraoVoicePreview.8a5e3ac697", spanish: es)) : (CuadraoCopy.text("copy.cuadraoVoicePreview.a4fcb403fc", spanish: es))
    }
}
