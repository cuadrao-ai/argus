import SwiftUI
import CoreLocation
import PDFKit

struct ReceiptLineEditor: View {
    @State var line: ReceiptLine
    let currency: String
    let spanish: Bool
    let existing: Bool
    let save: (ReceiptLine?) -> Void
    @State private var error = ""
    @Environment(\.dismiss) private var dismiss
    var body: some View {
        NavigationStack {
            Form {
                TextField(spanish ? "Artículo" : "Item", text: $line.name).accessibilityIdentifier("receipt-item-name")
                Stepper((spanish ? "Cantidad: " : "Quantity: ") + String(line.quantity), value: $line.quantity, in: 1...999)
                    .accessibilityIdentifier("receipt-item-quantity")
                CanvasMoneyValueInput(value: Binding(get: { Double(line.unitCents) / 100 }, set: { line.unitCents = Int(($0 * 100).rounded()) }),
                                      error: $error, currency: currency, spanish: spanish, identifier: "receipt-item-price",
                                      title: spanish ? "Precio unitario" : "Unit price", size: .prominent, alignment: .left).frame(minHeight: 54)
                if !error.isEmpty { Text(error).font(.caption).foregroundStyle(.red) }
                if existing { Button(spanish ? "Quitar artículo" : "Remove item", role: .destructive) { save(nil); dismiss() } }
            }.cuadraoFormKeyboard().navigationTitle(spanish ? "Artículo" : "Item").navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    CuadraoCancelToolbar(title: spanish ? "Cancelar" : "Cancel") { dismiss() }
                    CuadraoConfirmToolbar(title: spanish ? "Guardar" : "Save",
                                          disabled: !error.isEmpty || line.name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
                                          identifier: "receipt-item-save") { save(line); dismiss() }
                }
        }
    }
}

struct ReceiptSourceViewer: View {
    let draft: ReceiptDraft
    let store: CuadraoReceiptStore
    let spanish: Bool
    @Environment(\.dismiss) private var dismiss
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 24) {
                    ForEach(draft.source, id: \.filename) { source in
                        VStack(alignment: .leading, spacing: 12) {
                            Text(source.name).font(.caption).foregroundStyle(.secondary)
                            if source.pdf {
                                ReceiptPDF(url: store.url(source)).frame(height: 560)
                            } else if let data = try? Data(contentsOf: store.url(source)), let image = UIImage(data: data) {
                                Image(uiImage: image).resizable().scaledToFit().accessibilityLabel(source.name)
                            } else { Text(spanish ? "No pudimos abrir esta página." : "This page could not be opened.") }
                        }
                    }
                }.padding(24)
            }.navigationTitle(spanish ? "Recibo original" : "Original receipt").navigationBarTitleDisplayMode(.inline)
                .toolbar { CuadraoDoneToolbar(title: spanish ? "Listo" : "Done") { dismiss() } }
        }
    }
}
private struct ReceiptPDF: UIViewRepresentable {
    let url: URL
    func makeUIView(context: Context) -> PDFView {
        let view = PDFView(); view.autoScales = true; view.document = PDFDocument(url: url); return view
    }
    func updateUIView(_ view: PDFView, context: Context) {}
}

@Observable final class ReceiptLocationRequest: NSObject, CLLocationManagerDelegate {
    var value: ReceiptLocation?
    var unavailable = false
    var isAvailable: Bool { CuadraoDesignPreview.isActive }
    private let manager = CLLocationManager()
    private var requested = false
    override init() { super.init(); manager.delegate = self; manager.desiredAccuracy = kCLLocationAccuracyHundredMeters }
    func request() {
        guard isAvailable else { unavailable = true; return }
        requested = true; unavailable = false
        switch manager.authorizationStatus {
        case .notDetermined: manager.requestWhenInUseAuthorization()
        case .authorizedWhenInUse, .authorizedAlways: manager.requestLocation()
        default: unavailable = true
        }
    }
    func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        guard requested else { return }
        switch manager.authorizationStatus {
        case .authorizedWhenInUse, .authorizedAlways: manager.requestLocation()
        case .denied, .restricted: unavailable = true
        default: break
        }
    }
    func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        guard let location = locations.last, abs(location.timestamp.timeIntervalSinceNow) < 60 else { unavailable = true; return }
        value = ReceiptLocation(recordedAt: location.timestamp, latitude: location.coordinate.latitude, longitude: location.coordinate.longitude)
        requested = false
    }
    func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) { unavailable = true; requested = false }
}

struct CuadraoOwedRow: View {
    let cents: Int
    let currency: String
    let spanish: Bool
    var own = true
    var compact = false
    var body: some View {
        let layout = compact ? AnyLayout(VStackLayout(alignment: .trailing, spacing: 4)) : AnyLayout(HStackLayout())
        layout {
            Label(label, systemImage: cents > 0 ? "arrow.down.left" : cents < 0 ? "arrow.up.right" : "checkmark")
                .font(compact ? CuadraoTypography.caption : CuadraoTypography.supporting)
            if !compact { Spacer() }
            Text(CanvasMoney.format(Decimal(abs(cents)) / 100, currency: currency)).font(CuadraoTypography.rowAmount)
        }.foregroundStyle(color)
    }
    private var label: String {
        if cents == 0 { return spanish ? "Al día" : "Settled" }
        if own { return cents > 0 ? (spanish ? "Te deben" : "You're owed") : (spanish ? "Debes" : "You owe") }
        return cents > 0 ? (spanish ? "Por recibir" : "To receive") : (spanish ? "Debe" : "Owes")
    }
    private var color: Color { cents > 0 ? WelcomePalette.pine : cents < 0 ? WelcomePalette.owedNegative : .secondary }
}

struct ReceiptCard: View {
    let draft: ReceiptDraft
    let spanish: Bool
    let open: () -> Void
    var body: some View {
        Button(action: open) {
            HStack(spacing: 14) {
                Image(systemName: draft.prepared ? "receipt" : "checkmark.seal").frame(width: 40, height: 44)
                    .foregroundStyle(WelcomePalette.pine)
                VStack(alignment: .leading, spacing: 4) {
                    Text(draft.merchant.isEmpty ? (spanish ? "Recibo guardado" : "Saved receipt") : draft.merchant).font(CuadraoTypography.supporting)
                    Text(draft.prepared ? (spanish ? "Por revisar · solo tú" : "Ready to review · only you") : (spanish ? "Confirmado" : "Confirmed")).font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
                if draft.total > 0, let currency = draft.currency { Text(CanvasMoney.format(Decimal(draft.total) / 100, currency: currency)).font(CuadraoTypography.rowAmount) }
                Image(systemName: "chevron.right").font(.caption2).foregroundStyle(.secondary)
            }.foregroundStyle(WelcomePalette.ink).padding(12).background(WelcomePalette.surface, in: RoundedRectangle(cornerRadius: 18))
        }.buttonStyle(.plain).accessibilityIdentifier("receipt-card-\(draft.id)")
    }
}

struct ReceiptSavedList: View {
    let workspace: ReceiptWorkspace
    let groupID: UUID?
    let spanish: Bool
    var body: some View {
        List {
            Menu {
                ReceiptSourceActions(spanish: spanish) { workspace.capture(ReceiptOrigin(groupID: groupID, threadID: nil), $0) }
            } label: {
                Label(spanish ? "Añadir recibo" : "Add receipt", systemImage: "plus")
                    .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                    .contentShape(Rectangle())
            }.buttonStyle(.borderless).accessibilityIdentifier("saved-add-receipt")
            if !workspace.receipts.loadFailed && !workspace.receipts.receipts.contains(where: { $0.groupID == groupID }) {
                ContentUnavailableView(spanish ? "Sin recibos todavía" : "No receipts yet", systemImage: "receipt",
                    description: Text(spanish ? "Guarda uno ahora y revísalo después." : "Save one now and review it later."))
            }
            ForEach(workspace.receipts.receipts.filter { $0.groupID == groupID }.sorted { $0.updatedAt > $1.updatedAt }) { draft in
                ReceiptCard(draft: draft, spanish: spanish) { workspace.open(draft.id) }.listRowSeparator(.hidden)
            }
            if workspace.receipts.loadFailed {
                Text(spanish ? "No pudimos abrir los recibos guardados. Los archivos siguen en este dispositivo." : "Saved receipts could not be opened. The files remain on this device.")
            }
        }.listStyle(.plain).navigationTitle(spanish ? "Recibos guardados" : "Saved receipts").navigationBarTitleDisplayMode(.inline)
    }
}
