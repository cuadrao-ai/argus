import SwiftUI

struct CanvasAvatarCropRequest: Identifiable {
    let id = UUID()
    let source: CanvasAvatarSource
    let crop: CGRect
}

struct CanvasAvatarCropSheet: View {
    let source: CanvasAvatarSource
    let spanish: Bool
    let onUse: (CanvasAvatarPhoto) -> Void
    @Environment(\.dismiss) private var dismiss
    @State private var crop: CGRect
    @State private var failed = false
    @State private var rendering = false
    @State private var renderTask: Task<Void, Never>?

    init(request: CanvasAvatarCropRequest, spanish: Bool, onUse: @escaping (CanvasAvatarPhoto) -> Void) {
        source = request.source; self.spanish = spanish; self.onUse = onUse
        _crop = State(initialValue: request.crop)
    }
    private var zoom: Double { Double(min(source.width, source.height)) / crop.width }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 24) {
                    Text(spanish ? "Mueve y amplía la foto" : "Move and zoom your photo")
                        .font(.body).foregroundStyle(.secondary).multilineTextAlignment(.center)
                    CanvasAvatarCropViewport(source: source, crop: $crop)
                        .aspectRatio(1, contentMode: .fit).clipShape(Circle())
                        .overlay { Circle().stroke(.white.opacity(0.8), lineWidth: 2).allowsHitTesting(false) }
                        .accessibilityLabel(spanish ? "Encuadre de la foto" : "Photo crop")
                        .accessibilityValue(String(format: "%.2fx, %.0f, %.0f", zoom, crop.midX, crop.midY))
                        .accessibilityIdentifier("cuadrao.profile.crop.viewport")
                    VStack(alignment: .leading, spacing: 12) {
                        Text(spanish ? "Ampliación" : "Zoom").font(.subheadline)
                        Slider(value: Binding(get: { zoom }, set: { value in
                            let side = CGFloat(min(source.width, source.height)) / value
                            crop = source.geometry.clamped(CGRect(x: crop.midX - side / 2, y: crop.midY - side / 2, width: side, height: side))
                        }), in: 1...4)
                        .accessibilityLabel(spanish ? "Ampliación" : "Zoom")
                        .accessibilityValue(String(format: "%.1fx", zoom))
                        .accessibilityIdentifier("cuadrao.profile.crop.zoom")
                        HStack {
                            move("left", symbol: "arrow.left", title: spanish ? "Mover a la izquierda" : "Move left", dx: -1, dy: 0)
                            move("right", symbol: "arrow.right", title: spanish ? "Mover a la derecha" : "Move right", dx: 1, dy: 0)
                            move("up", symbol: "arrow.up", title: spanish ? "Mover arriba" : "Move up", dx: 0, dy: -1)
                            move("down", symbol: "arrow.down", title: spanish ? "Mover abajo" : "Move down", dx: 0, dy: 1)
                        }.frame(maxWidth: .infinity)
                        Button(spanish ? "Restablecer" : "Reset") { crop = source.geometry.centered }
                            .frame(maxWidth: .infinity, minHeight: 44).accessibilityIdentifier("cuadrao.profile.crop.reset")
                    }
                    if failed {
                        Text(spanish ? "No pudimos preparar la foto. Inténtalo de nuevo." : "We couldn’t prepare the photo. Try again.")
                            .font(.footnote).foregroundStyle(.secondary)
                    }
                }.padding(24).frame(maxWidth: 440).frame(maxWidth: .infinity)
                    .disabled(rendering)
            }.background(Color(uiColor: .systemBackground))
                .navigationTitle(spanish ? "Ajustar foto" : "Adjust photo").navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    CuadraoCancelToolbar(title: spanish ? "Cancelar" : "Cancel", identifier: "cuadrao.profile.crop.cancel") { dismiss() }
                    CuadraoConfirmToolbar(title: spanish ? "Usar foto" : "Use photo", disabled: rendering,
                                          identifier: "cuadrao.profile.crop.use") { accept() }
                }
        }.tint(WelcomePalette.pine)
            .onDisappear { renderTask?.cancel() }
    }

    private func move(_ id: String, symbol: String, title: String, dx: CGFloat, dy: CGFloat) -> some View {
        let next = source.geometry.clamped(crop.offsetBy(dx: dx * crop.width * 0.1, dy: dy * crop.height * 0.1))
        return Button { crop = next } label: { Image(systemName: symbol).frame(maxWidth: .infinity, minHeight: 44) }
            .accessibilityLabel(title).disabled(next == crop)
            .accessibilityIdentifier("cuadrao.profile.crop.\(id)")
    }
    private func accept() {
        rendering = true; failed = false
        let source = source, crop = crop
        renderTask = Task {
            let worker = Task.detached(priority: .userInitiated) { try CanvasAvatarPhoto(source: source, crop: crop) }
            do {
                let photo = try await withTaskCancellationHandler { try await worker.value } onCancel: { worker.cancel() }
                try Task.checkCancellation()
                onUse(photo); dismiss()
            } catch {
                guard !Task.isCancelled else { return }
                failed = true; rendering = false
            }
        }
    }
}

private struct CanvasAvatarCropViewport: UIViewRepresentable {
    let source: CanvasAvatarSource
    @Binding var crop: CGRect
    func makeUIView(context: Context) -> AvatarCropScrollView {
        let view = AvatarCropScrollView(source: source)
        view.changed = { crop = $0 }
        return view
    }
    func updateUIView(_ view: AvatarCropScrollView, context: Context) {
        view.changed = { crop = $0 }
        view.setCrop(crop)
    }
}

private final class AvatarCropScrollView: UIScrollView, UIScrollViewDelegate {
    private let source: CanvasAvatarSource
    private let photo: UIImageView
    private var requested: CGRect
    private var viewportSize = CGSize.zero
    private var applying = false
    var changed: ((CGRect) -> Void)?

    init(source: CanvasAvatarSource) {
        self.source = source; requested = source.geometry.centered
        photo = UIImageView(image: UIImage(data: source.jpeg))
        super.init(frame: .zero)
        photo.frame = CGRect(origin: .zero, size: source.size)
        addSubview(photo); contentSize = source.size; delegate = self
        showsHorizontalScrollIndicator = false; showsVerticalScrollIndicator = false
        bounces = false; bouncesZoom = false; contentInsetAdjustmentBehavior = .never
        isAccessibilityElement = true
    }
    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }
    override func layoutSubviews() {
        super.layoutSubviews()
        guard bounds.width > 0, bounds.size != viewportSize else { return }
        viewportSize = bounds.size
        applyCrop()
    }
    func setCrop(_ rect: CGRect) {
        guard requested != rect else { return }
        requested = rect
        if bounds.width > 0 { applyCrop() }
    }
    private func applyCrop() {
        applying = true
        minimumZoomScale = bounds.width / CGFloat(min(source.width, source.height))
        maximumZoomScale = minimumZoomScale * 4
        setZoomScale(bounds.width / requested.width, animated: false)
        setContentOffset(CGPoint(x: requested.minX * zoomScale, y: requested.minY * zoomScale), animated: false)
        applying = false
    }
    func viewForZooming(in scrollView: UIScrollView) -> UIView? { photo }
    func scrollViewDidScroll(_ scrollView: UIScrollView) { reportCrop() }
    func scrollViewDidZoom(_ scrollView: UIScrollView) { reportCrop() }
    private func reportCrop() {
        guard !applying, bounds.width > 0 else { return }
        requested = source.geometry.clamped(CGRect(x: contentOffset.x / zoomScale, y: contentOffset.y / zoomScale,
                                          width: bounds.width / zoomScale, height: bounds.width / zoomScale))
        changed?(requested)
    }
}
