import SwiftUI
import CoreImage.CIFilterBuiltins

struct CuadraoGroupCodeCard: View {
    let group: PlanGroup
    let look: CanvasPlanLook
    let cover: Data?
    let spanish: Bool
    @Environment(\.dismiss) private var dismiss
    @State private var share: GroupCodeImage?
    @State private var exportFailed = false

    private var sampleMessage: String {
        spanish ? "Código de muestra. No permite unirse a un grupo real." : "Sample code. It doesn't join a real group."
    }
    private var qr: UIImage? { Self.qr("Cuadrao design preview | \(group.id.uuidString)") }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 20) {
                    if let qr {
                        artwork(qr)
                        Button { export(qr) } label: {
                            Label(spanish ? "Compartir tarjeta de muestra" : "Share sample card", systemImage: "square.and.arrow.up")
                                .frame(maxWidth: .infinity, minHeight: 44)
                        }.accessibilityIdentifier("group-code-share")
                    } else {
                        ContentUnavailableView(spanish ? "Código no disponible" : "Code unavailable", systemImage: "qrcode",
                                               description: Text(spanish ? "Cierra esta tarjeta e inténtalo de nuevo." : "Close this card and try again."))
                    }
                    if exportFailed {
                        Text(spanish ? "No pudimos preparar la tarjeta. Inténtalo de nuevo." : "We couldn’t prepare the card. Try again.")
                            .font(.footnote).foregroundStyle(.secondary)
                    }
                }.padding(24).frame(maxWidth: 440).frame(maxWidth: .infinity)
            }.background(WelcomePalette.background)
                .navigationTitle(spanish ? "Código de muestra" : "Sample code").navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    CuadraoDoneToolbar(title: spanish ? "Listo" : "Done", identifier: "group-code-done") { dismiss() }
                }
                .sheet(item: $share) { item in GroupCodeShareSheet(image: item.image, message: sampleMessage) }
        }.tint(WelcomePalette.pine).presentationDragIndicator(.visible)
    }

    private func artwork(_ qr: UIImage) -> some View {
        VStack(spacing: 0) {
            ZStack(alignment: .bottomLeading) {
                PlanGroupArtwork(look: look, cover: cover).frame(height: 170)
                PlanAvatarStack(members: group.activeMembers).padding(20)
            }
            VStack(spacing: 18) {
                Text(group.name).font(CuadraoTypography.feature).multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
                Image(uiImage: qr).interpolation(.none).resizable().scaledToFit().frame(maxWidth: 260)
                    .background(.white).accessibilityLabel(spanish ? "Código QR de muestra" : "Sample QR code")
                    .accessibilityIdentifier("group-code-qr")
                Text(spanish ? "Juntos, cuadra mejor." : "Better, together.").font(.system(.title3, design: .serif))
                    .multilineTextAlignment(.center)
                Text(sampleMessage).font(.caption).foregroundStyle(.secondary).multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true).accessibilityIdentifier("group-code-disclosure")
            }.padding(24).frame(maxWidth: .infinity)
        }.background(WelcomePalette.surface, in: RoundedRectangle(cornerRadius: 28))
            .clipShape(RoundedRectangle(cornerRadius: 28))
    }
    private func export(_ qr: UIImage) {
        exportFailed = false
        let renderer = ImageRenderer(content: artwork(qr).padding(24).frame(width: 390)
            .background(WelcomePalette.background).environment(\.colorScheme, .light).environment(\.dynamicTypeSize, .large))
        renderer.scale = 2; renderer.isOpaque = true
        guard let image = renderer.uiImage, let pixels = image.cgImage,
              pixels.width * pixels.height <= 3_000_000 else { exportFailed = true; return }
        share = GroupCodeImage(image: image)
    }
    private static func qr(_ text: String) -> UIImage? {
        let filter = CIFilter.qrCodeGenerator()
        filter.message = Data(text.utf8); filter.correctionLevel = "M"
        guard let raw = filter.outputImage else { return nil }
        let tint = CIFilter.falseColor()
        tint.inputImage = raw
        tint.color0 = CIColor(red: 0.16, green: 0.29, blue: 0.25); tint.color1 = .white
        guard let tinted = tint.outputImage else { return nil }
        let scale: CGFloat = 8
        let expanded = raw.extent.insetBy(dx: -4, dy: -4)
        let white = CIImage(color: .white).cropped(to: expanded)
        let output = tinted.composited(over: white).transformed(by: CGAffineTransform(scaleX: scale, y: scale))
        guard let pixels = CIContext().createCGImage(output, from: expanded.applying(CGAffineTransform(scaleX: scale, y: scale))) else { return nil }
        return UIImage(cgImage: pixels)
    }
}

private struct GroupCodeImage: Identifiable {
    let id = UUID()
    let image: UIImage
}

private struct GroupCodeShareSheet: UIViewControllerRepresentable {
    let image: UIImage
    let message: String
    func makeUIViewController(context: Context) -> UIActivityViewController {
        UIActivityViewController(activityItems: [image, message], applicationActivities: nil)
    }
    func updateUIViewController(_ controller: UIActivityViewController, context: Context) {}
}
