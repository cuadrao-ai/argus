#if DEBUG
import UIKit

/// Debug-only stand-in for the document camera (`--cuadrao-scan-stub`). The simulator has no scanner, so this
/// hands the real coordinator two full-size 12 MP pages after a "Listo" tap, exercising the same confirm path.
enum ScanStub {
    static let active = ProcessInfo.processInfo.arguments.contains("--cuadrao-scan-stub")

    static func controller(_ finish: @escaping ([UIImage]) -> Void) -> UIViewController {
        Controller(finish: finish)
    }

    private final class Controller: UIViewController {
        let finish: ([UIImage]) -> Void
        init(finish: @escaping ([UIImage]) -> Void) { self.finish = finish; super.init(nibName: nil, bundle: nil) }
        required init?(coder: NSCoder) { nil }
        override func viewDidLoad() {
            super.viewDidLoad()
            view.backgroundColor = .black
            let done = UIButton(type: .system)
            done.setTitle("Listo", for: .normal)
            done.accessibilityIdentifier = "scan.stub.done"
            done.translatesAutoresizingMaskIntoConstraints = false
            done.addAction(UIAction { [weak self] _ in
                guard let self else { return }
                let pages = ScanStub.pages()
                FrameGap.start()
                self.finish(pages)
            }, for: .touchUpInside)
            view.addSubview(done)
            NSLayoutConstraint.activate([done.centerXAnchor.constraint(equalTo: view.centerXAnchor),
                                         done.centerYAnchor.constraint(equalTo: view.centerYAnchor)])
        }
    }

    /// Logs the longest main-thread frame gap for 8 seconds after the confirm tap ("scan-stub max frame gap").
    private final class FrameGap: NSObject {
        static var current: FrameGap?
        private var link: CADisplayLink?, last: CFTimeInterval = 0, worst: CFTimeInterval = 0, begun: CFTimeInterval = 0
        static func start() { current = FrameGap(); current?.run() }
        private func run() {
            begun = CACurrentMediaTime(); last = begun
            link = CADisplayLink(target: self, selector: #selector(tick)); link?.add(to: .main, forMode: .common)
        }
        @objc private func tick(_ link: CADisplayLink) {
            let now = CACurrentMediaTime(); worst = max(worst, now - last); last = now
            if now - begun > 8 {
                NSLog("scan-stub max frame gap %d ms", Int(worst * 1000)); link.invalidate(); FrameGap.current = nil
            }
        }
    }

    /// Two pages the size of an iPhone camera frame, with detail so JPEG encoding does real work.
    static func pages() -> [UIImage] {
        let size = CGSize(width: 3024, height: 4032)
        let format = UIGraphicsImageRendererFormat.default(); format.scale = 1
        return (0..<2).map { page in
            UIGraphicsImageRenderer(size: size, format: format).image { context in
                UIColor.white.setFill(); context.fill(CGRect(origin: .zero, size: size))
                for line in 0..<400 {
                    let y = CGFloat(line) * 10
                    UIColor(hue: CGFloat((line + page * 37) % 100) / 100, saturation: 0.3, brightness: 0.4, alpha: 1).setFill()
                    context.fill(CGRect(x: CGFloat(line % 17) * 20, y: y, width: size.width - CGFloat(line % 23) * 40, height: 4))
                }
            }
        }
    }
}
#endif
