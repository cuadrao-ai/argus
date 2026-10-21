import SwiftUI
import PhotosUI
import VisionKit
import PDFKit
import UniformTypeIdentifiers

struct ReceiptWorkspace {
    let receipts: CuadraoReceiptStore
    let groups: CuadraoGroupPreview
    let accounts: CuadraoAccountsPreview
    let chat: CuadraoChatPreview
    let capture: (ReceiptOrigin, ReceiptSourceChoice) -> Void
    let open: (UUID) -> Void
    var postingCapability: ReceiptPostingCapability { receipts.postingCapability }
}
private struct ReceiptWorkspaceKey: EnvironmentKey {
    static let defaultValue: ReceiptWorkspace? = nil
}
extension EnvironmentValues {
    var receiptWorkspace: ReceiptWorkspace? {
        get { self[ReceiptWorkspaceKey.self] }
        set { self[ReceiptWorkspaceKey.self] = newValue }
    }
}
enum ReceiptRoute: Identifiable {
    case capture(ReceiptOrigin, ReceiptSourceChoice), review(UUID)
    var id: String { switch self { case .capture: "capture"; case .review(let id): id.uuidString } }
}

extension View {
    func receiptPresentation(route: Binding<ReceiptRoute?>, workspace: ReceiptWorkspace?, spanish: Bool) -> some View {
        modifier(ReceiptPresentation(route: route, workspace: workspace, spanish: spanish))
    }
}

private struct ReceiptPresentation: ViewModifier {
    @Binding var route: ReceiptRoute?
    let workspace: ReceiptWorkspace?
    let spanish: Bool
    @State private var pendingReview: UUID?

    func body(content: Content) -> some View {
        content
            .fullScreenCover(item: captureRoute, onDismiss: openSavedReceipt) { route in
                if let workspace, case .capture(let origin, let source) = route {
                    CuadraoReceiptCapture(origin: origin, source: source, workspace: workspace, spanish: spanish,
                        cancel: { self.route = nil }, saved: { id in
                            pendingReview = id
                            self.route = nil
                        })
                        .interactiveDismissDisabled()
                }
            }
            .sheet(item: reviewRoute) { route in
                if let workspace, case .review(let id) = route {
                    CuadraoReceiptFlow(id: id, workspace: workspace, spanish: spanish)
                }
            }
    }
    private var captureRoute: Binding<ReceiptRoute?> {
        Binding(get: {
            if case .capture = route { return route }
            return nil
        }, set: { value in
            if case .capture = route { route = value }
        })
    }
    private var reviewRoute: Binding<ReceiptRoute?> {
        Binding(get: {
            if case .review = route { return route }
            return nil
        }, set: { value in
            if case .review = route { route = value }
        })
    }
    private func openSavedReceipt() {
        guard let id = pendingReview else { return }
        pendingReview = nil
        route = .review(id)
    }
}

struct CuadraoReceiptFlow: View {
    let id: UUID
    let workspace: ReceiptWorkspace
    let spanish: Bool
    @Environment(\.dismiss) private var dismiss
    var body: some View {
        NavigationStack {
            CuadraoReceiptReview(id: id, workspace: workspace, spanish: spanish)
                .toolbar {
                    CuadraoCancelToolbar(title: closeTitle, identifier: "receipt-later") { dismiss() }
                }
        }.tint(WelcomePalette.pine).presentationDragIndicator(.visible)
    }
    private var closeTitle: String {
        let confirmed = workspace.receipts.receipt(id).map { !$0.prepared } ?? false
        return confirmed ? (spanish ? "Listo" : "Done") : (spanish ? "Después" : "Later")
    }
}

enum ReceiptSourceChoice: String, CaseIterable, Identifiable {
    case scan, photos, file, sample
    var id: String { rawValue }
    func title(_ es: Bool) -> String {
        switch self {
        case .scan: es ? "Escanear recibo" : "Scan receipt"
        case .photos: es ? "Fotos" : "Photos"
        case .file: es ? "Archivos" : "Files"
        case .sample: es ? "Probar un recibo de ejemplo" : "Try a sample receipt"
        }
    }
    var symbol: String {
        switch self { case .scan: "doc.viewfinder"; case .photos: "photo"; case .file: "folder"; case .sample: "sparkles" }
    }
}

struct ReceiptSourceActions: View {
    let spanish: Bool
    let choose: (ReceiptSourceChoice) -> Void
    var body: some View {
        ForEach(ReceiptSourceChoice.allCases) { source in
            Button(source.title(spanish), systemImage: source.symbol) { choose(source) }
                .accessibilityIdentifier("receipt-" + source.rawValue)
        }
    }
}

typealias ReceiptCapturedFiles = [(data: Data, name: String, pdf: Bool)]

struct CuadraoReceiptCapture: View {
    let origin: ReceiptOrigin
    let source: ReceiptSourceChoice
    let workspace: ReceiptWorkspace
    let spanish: Bool
    let cancel: () -> Void
    let saved: (UUID) -> Void
    @State private var picker: ReceiptSourceChoice?
    @State private var pending: ReceiptCapturedFiles?
    @State private var selectedSource: ReceiptSourceChoice
    @State private var error = ""
    @State private var captured = false
    private var group: PlanGroup? { origin.groupID.flatMap(workspace.groups.group) }
    init(origin: ReceiptOrigin, source: ReceiptSourceChoice, workspace: ReceiptWorkspace, spanish: Bool,
         cancel: @escaping () -> Void, saved: @escaping (UUID) -> Void) {
        self.origin = origin; self.source = source; self.workspace = workspace; self.spanish = spanish
        self.cancel = cancel; self.saved = saved
        _selectedSource = State(initialValue: source)
        if origin.groupID != nil && origin.groupID.flatMap(workspace.groups.group) == nil {
            _error = State(initialValue: ReceiptError.destination.message(spanish))
        } else if source == .scan && !VNDocumentCameraViewController.isSupported {
            _error = State(initialValue: Self.scannerUnavailable(spanish))
        } else if source != .sample {
            _picker = State(initialValue: source)
        }
    }
    var body: some View {
        Group {
            if let picker {
                ReceiptNativePicker(source: picker, spanish: spanish, completed: finishPicker)
                    .id(picker)
                    .ignoresSafeArea()
            } else {
                NavigationStack {
                    recovery
                        .navigationTitle(spanish ? "Un recibo" : "A receipt")
                        .navigationBarTitleDisplayMode(.inline)
                        .toolbar {
                            CuadraoCancelToolbar(title: spanish ? "Cancelar" : "Cancel", identifier: "receipt-later", action: cancel)
                        }
                }
            }
        }.tint(WelcomePalette.pine)
            .task {
                if source == .sample && error.isEmpty && !captured { sample() }
            }
    }
    private var recovery: some View {
        VStack(spacing: 24) {
            if error.isEmpty {
                ProgressView(spanish ? "Guardando recibo…" : "Saving receipt…")
            } else {
                Image(systemName: "receipt").font(.largeTitle).foregroundStyle(WelcomePalette.pine)
                Text(error).font(CuadraoTypography.supporting).accessibilityIdentifier("receipt-error")
                if let pending {
                    Button(spanish ? "Guardar de nuevo" : "Save again") { commit(pending, example: selectedSource == .sample) }
                        .accessibilityIdentifier("receipt-retry")
                } else if selectedSource != .scan || VNDocumentCameraViewController.isSupported {
                    Button(spanish ? "Intentar de nuevo" : "Try again") { begin(selectedSource) }
                        .accessibilityIdentifier("receipt-retry")
                }
                ForEach(ReceiptSourceChoice.allCases.filter { $0 != .scan }) { alternative in
                    Button(alternative.title(spanish), systemImage: alternative.symbol) { begin(alternative) }
                        .accessibilityIdentifier("receipt-" + alternative.rawValue)
                }
            }
        }.padding(24).frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(WelcomePalette.background)
    }
    private static func scannerUnavailable(_ spanish: Bool) -> String {
        spanish ? "El escáner no está disponible aquí. Puedes elegir una foto o un archivo." : "The scanner is unavailable here. Choose a photo or file."
    }
    private func begin(_ source: ReceiptSourceChoice) {
        error = ""; pending = nil; selectedSource = source
        guard origin.groupID == nil || group != nil else { show(ReceiptError.destination); return }
        if source == .sample { sample() }
        else if source == .scan && !VNDocumentCameraViewController.isSupported {
            error = Self.scannerUnavailable(spanish)
        } else { picker = source }
    }
    private func finishPicker(_ outcome: Result<ReceiptCapturedFiles, Error>) {
        switch outcome {
        case .success(let files): commit(files)
        case .failure(let failure):
            if (failure as NSError).code == NSUserCancelledError { cancel() }
            else { show(failure) }
        }
    }
    private func show(_ failure: Error) {
        picker = nil
        error = (failure as? ReceiptError)?.message(spanish) ?? (spanish ? "No pudimos guardar el recibo. Inténtalo de nuevo." : "We couldn't save the receipt. Try again.")
    }
    private func commit(_ files: ReceiptCapturedFiles, example: Bool = false) {
        guard !captured else { return }
        pending = files
        do {
            let id = try workspace.receipts.capture(files: files, currency: example ? "DOP" : nil, origin: origin, group: group, example: example, spanish: spanish)
            captured = true; pending = nil
            if let threadID = origin.threadID { workspace.chat.attachReceipt(id, to: threadID) }
            saved(id)
        } catch { show(error) }
    }
    private func sample() {
        let renderer = UIGraphicsImageRenderer(size: CGSize(width: 600, height: 790))
        let data = renderer.jpegData(withCompressionQuality: 0.85) { context in
            UIColor.white.setFill(); context.fill(CGRect(x: 0, y: 0, width: 600, height: 790))
            let sample = ReceiptSample(spanish: spanish)
            func money(_ cents: Int) -> String { CanvasMoney.format(Decimal(cents) / 100, currency: group?.currency ?? "DOP") }
            let items = sample.lines.map { "\($0.quantity) × \($0.name)\n    \(money($0.cents))" }.joined(separator: "\n")
            let text = "\(sample.merchant)\n\(spanish ? "RECIBO DE EJEMPLO" : "SAMPLE RECEIPT")\n\n\(items)\n\nSubtotal  \(money(sample.subtotal))\n\(spanish ? "Impuesto" : "Tax")  \(money(sample.taxCents))\n\(spanish ? "Servicio" : "Service")  \(money(sample.serviceCents))\n\nTOTAL  \(money(sample.total))\n\(group?.currency ?? "DOP")"
            (text as NSString).draw(in: CGRect(x: 42, y: 48, width: 520, height: 700), withAttributes: [.font: UIFont.monospacedSystemFont(ofSize: 24, weight: .regular), .foregroundColor: UIColor.black])
        }
        commit([(data, spanish ? "Recibo de ejemplo" : "Sample receipt", false)], example: true)
    }
}
