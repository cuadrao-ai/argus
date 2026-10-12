#if DEBUG
import SwiftUI
import ArgusSession

/// Debug-only stand-in for the receipt routes (`--cuadrao-saved-receipts-sample`), so the journey can be driven
/// without a server. Its replies have the API's exact shapes. Release builds do not compile this file.
actor SampleReceiptJourneyTransport: ReceiptJourneyTransport {
    static let accountID = "6a1f0b8e-3c55-4c2e-9a7d-2f1b4c6d8e90"
    private let files: SampleSavedReceiptsTransport
    private var reads = 0
    private var version = 1
    private var acceptedIDs: Set<String> = []
    private var accepted: Bool { acceptedIDs.contains(current) }
    private var current = "sample-receipt"
    /// A file named "Duplicado…" reads as a purchase that is already recorded.
    private var duplicate = false
    /// A file named "Ilegible…" cannot be read; "SinConexion…" never reaches the server.
    private var unreadable = false
    /// A file named "SinFecha…" reads without a date.
    private var undated = false

    /// Shares the sample file list, so a receipt saved here appears in Saved receipts.
    init(files: SampleSavedReceiptsTransport) { self.files = files }

    func upload(_ bytes: Data, mediaType: String, filename: String, consent: Bool, identity: SessionSnapshot) async throws -> SavedDocumentCapture {
        if filename.hasPrefix("SinConexion") { throw URLError(.notConnectedToInternet) }
        let saved = try await files.save(bytes, mediaType: mediaType, filename: filename, identity: identity)
        reads = 0
        duplicate = filename.hasPrefix("Duplicado")
        unreadable = filename.hasPrefix("Ilegible")
        undated = filename.hasPrefix("SinFecha")
        return SavedDocumentCapture(connectionID: saved.connectionID, status: consent ? "queued" : "saved", replayed: saved.replayed)
    }

    func document(_ connectionID: String, identity: SessionSnapshot) async throws -> FinancialDocumentDetail {
        reads += 1
        current = connectionID
        return try Self.decode(Self.document(connectionID, status: reads < 3 ? "preparing" : unreadable ? "needs_attention" : "review_ready", dated: !undated))
    }

    func prepare(_ connectionID: String, identity: SessionSnapshot) async throws -> SavedDocumentCapture {
        reads = 0
        return SavedDocumentCapture(connectionID: connectionID, status: "queued", replayed: false)
    }

    func openImports(identity: SessionSnapshot) async throws -> [FinancialImportEvent] {
        accepted ? [] : [try Self.decode(eventJSON(current, version: version, account: nil, activity: nil))]
    }

    func acceptedImports(identity: SessionSnapshot) async throws -> [FinancialImportEvent] {
        accepted ? [try Self.decode(eventJSON(current, version: version, account: Self.accountID, activity: Self.activityID))] : []
    }

    func resolve(_ event: FinancialImportEvent, changes: FinancialImportChanges, identity: SessionSnapshot) async throws -> FinancialImportEvent {
        version += 1
        return try Self.decode(eventJSON(current, version: version, account: changes.accountID?.uuidString.lowercased() ?? Self.accountID, activity: nil))
    }

    func preview(_ eventID: String, identity: SessionSnapshot) async throws -> FinancialImportPreview {
        try Self.decode(["event": eventJSON(current, version: version, account: Self.accountID, activity: nil),
                         "preview": ["ready": true, "expected_versions": [Self.accountID: 1], "affected_accounts": [],
                                     "reviewed_request": Self.request, "preview_token": "sample-token"]])
    }

    func accept(_ event: FinancialImportEvent, request: FinancialActivityCommand, key: UUID, identity: SessionSnapshot) async throws -> FinancialImportAcceptance {
        acceptedIDs.insert(current)
        return try Self.decode(["event": eventJSON(current, version: version, account: Self.accountID, activity: Self.activityID),
                                "activity": Self.activity, "replayed": false])
    }

    func link(_ event: FinancialImportEvent, activityID: UUID, identity: SessionSnapshot) async throws -> FinancialImportEvent {
        acceptedIDs.insert(current)
        return event
    }

    func options(identity: SessionSnapshot) async throws -> FinancialActivityOptions {
        try Self.decode(["accounts": [Self.account], "eligibility": ["expense": ["checking", "cash", "card"]],
                         "destination_eligibility": [:], "categories": ["groceries", "food", "transport"], "sources": []])
    }

    func source(_ connectionID: String, identity: SessionSnapshot) async throws -> Data {
        try await files.source(connectionID, identity: identity)
    }

    private static let activityID = "0b9c8d7e-6f5a-4b3c-8d2e-1f0a9b8c7d6e"

    private static func decode<T: Decodable>(_ value: [String: Any]) throws -> T {
        try JSONDecoder().decode(T.self, from: JSONSerialization.data(withJSONObject: value))
    }

    private static func document(_ connectionID: String, status: String, dated: Bool = true) -> [String: Any] {
        ["connection_id": connectionID, "filename": "Escaneo.png", "media_type": "image/png", "source_available": true,
         "status": status, "consent": true, "version": 1, "error_code": NSNull(), "created_at": "2026-10-11T12:00:00Z",
         "preparation": status == "review_ready" ? ["complete": true, "readable": true, "receipt": [
            "merchant": "La Sirena", "occurred_on": dated ? "2026-10-10" as Any : NSNull(), "currency": "DOP", "subtotal": "250.50", "tax": NSNull(),
            "service": NSNull(), "tip": NSNull(), "total": "250.50", "suggested_category": "groceries",
            "items": [["id": "1", "description": "Arroz", "quantity": "1", "unit_price": "150.00", "total": "150.00"],
                      ["id": "2", "description": "Leche", "quantity": "1", "unit_price": "100.50", "total": "100.50"]]]] as Any : NSNull()]
    }

    private func eventJSON(_ connectionID: String, version: Int, account: String?, activity: String?) -> [String: Any] {
        ["id": "sample-event", "state": activity == nil ? "open" : "accepted", "version": version, "attention": NSNull(),
         "activity_id": activity as Any? ?? NSNull(), "possible_duplicates": [], "recorded_duplicates": [],
         "existing_activity_matches": duplicate ? [Self.activityID] : [],
         "facts": ["amount": "250.50", "currency": "DOP", "direction": "outflow", "occurred_on": undated ? NSNull() as Any : "2026-10-10",
                   "account_id": account as Any? ?? NSNull(), "kind": "expense"],
         "unresolved": account == nil ? ["account_id"] : [],
         "observations": [["source": "statement", "connection_id": connectionID, "merchant": "La Sirena", "description": NSNull(),
                           "amount": "250.50", "currency": "DOP", "occurred_on": undated ? NSNull() as Any : "2026-10-10"]]]
    }

    private static var account: [String: Any] {
        ["id": accountID, "type": "checking", "nature": "asset", "currency": "DOP", "currency_fraction_digits": 2,
         "nickname": "Banreservas", "archived": false, "ownership_share_bps": 10000, "version": 1,
         "created_at": "2026-10-01T00:00:00Z", "updated_at": "2026-10-01T00:00:00Z", "opening": NSNull(), "asset": NSNull(),
         "balance": ["state": "unknown", "amount_minor": NSNull(), "amount": NSNull(), "as_of": NSNull(), "basis": NSNull(),
                     "activity_since_tracking_minor": 0]]
    }

    private static var request: [String: Any] {
        ["kind": "expense", "account_id": accountID, "source_account_id": NSNull(), "destination_account_id": NSNull(),
         "amount": "250.50", "occurred_at": "2026-10-10T12:00:00-04:00", "time_zone": "America/Santo_Domingo", "note": "La Sirena",
         "category_id": "groceries", "source_id": NSNull(), "purchase_activity_id": NSNull(), "expected_revision": NSNull(),
         "reason": NSNull(), "expected_versions": [accountID: 1], "coverage": [], "preview_token": NSNull()]
    }

    private static var activity: [String: Any] {
        ["activity_id": activityID, "revision": 1, "kind": "expense", "amount_minor": 25050, "amount": "250.50", "currency": "DOP",
         "currency_fraction_digits": 2, "occurred_at": "2026-10-10T12:00:00-04:00", "time_zone": "America/Santo_Domingo",
         "note": "La Sirena", "category_id": "groceries", "source_id": NSNull(), "purchase_activity_id": NSNull(),
         "purchase_revision": NSNull(), "reason": NSNull(), "recorded_at": "2026-10-11T12:00:00Z", "recorded_by": NSNull(), "legs": []]
    }
}

/// `--cuadrao-synthetic-receipt`: the + tray's receipt rows hand the real journey this drawn receipt instead of opening
/// the camera, photos or files, so a staging check can read a known synthetic receipt. Nothing else changes.
enum SyntheticReceipt {
    static var active: Bool { ProcessInfo.processInfo.arguments.contains("--cuadrao-synthetic-receipt") || chosenFile != nil }

    /// `--cuadrao-receipt-file <path>`: a staging check hands the journey this file instead of the drawn receipt.
    static var chosenFile: URL? {
        let arguments = ProcessInfo.processInfo.arguments
        guard let flag = arguments.firstIndex(of: "--cuadrao-receipt-file"), arguments.indices.contains(flag + 1) else { return nil }
        return URL(fileURLWithPath: arguments[flag + 1])
    }

    static func file() -> (data: Data, name: String, pdf: Bool) {
        if let url = chosenFile {
            // An unreadable file sends nothing usable, so the check fails instead of reading the drawn receipt.
            let data = (try? Data(contentsOf: url)) ?? Data()
            return (data, url.lastPathComponent, url.pathExtension.lowercased() == "pdf")
        }
        let lines = ["SUPERMERCADO LA SIRENA", "Av. 27 de Febrero, Santo Domingo", "Fecha: 10/10/2026", "",
                     "Arroz 1 lb            150.00", "Leche 1 L             100.50", "",
                     "SUBTOTAL              250.50", "TOTAL RD$             250.50", "", "Gracias por su compra"]
        let rect = CGRect(x: 0, y: 0, width: 600, height: 900)
        let image = UIGraphicsImageRenderer(size: rect.size).image { context in
            UIColor.white.setFill(); context.fill(rect)
            let font = UIFont.monospacedSystemFont(ofSize: 26, weight: .regular)
            for (index, line) in lines.enumerated() {
                (line as NSString).draw(at: CGPoint(x: 40, y: 60 + CGFloat(index) * 52),
                                        withAttributes: [.font: font, .foregroundColor: UIColor.black])
            }
        }
        return (image.jpegData(compressionQuality: 0.9) ?? Data(), "Recibo sintetico La Sirena.jpg", false)
    }
}

/// `--receipt-journey-harness`: the receipt journey alone, against the sample server and a synthetic session,
/// so its screens can be checked without signing in.
struct ReceiptJourneyHarness: View {
    @StateObject private var model = ReceiptJourneyModel(
        transport: SampleReceiptJourneyTransport(files: SampleSavedReceiptsTransport()),
        currentSession: { ReceiptJourneyHarness.session }, pause: { _ in try? await Task.sleep(for: ReceiptJourneyHarness.readingStep) },
        defaults: ReceiptJourneyHarness.defaults)
    @State private var result = ""
    @Environment(\.locale) private var locale
    nonisolated private static let session = SessionSnapshot(
        phase: .authenticated, profile: try? JSONDecoder().decode(SessionProfile.self, from: Data(#"{"id":"harness"}"#.utf8)), revision: 1)
    /// `--receipt-slow-reading` holds each poll long enough to see the reading state.
    nonisolated private static let readingStep: Duration =
        ProcessInfo.processInfo.arguments.contains("--receipt-slow-reading") ? .seconds(2) : .milliseconds(300)
    /// Starts each launch unanswered; `--receipt-reading-allowed` starts as if reading was already allowed.
    nonisolated(unsafe) private static let defaults: UserDefaults = {
        let defaults = UserDefaults(suiteName: "receipt-journey-harness")!
        defaults.removePersistentDomain(forName: "receipt-journey-harness")
        if ProcessInfo.processInfo.arguments.contains("--receipt-reading-allowed") { defaults.set(true, forKey: "cuadrao.receiptReading.harness") }
        return defaults
    }()
    private var spanish: Bool { locale.language.languageCode?.identifier == "es" }

    var body: some View {
        VStack(spacing: 24) {
            Button("Receipt") { model.begin([(SampleSavedReceiptsTransport.png("Recibo"), "Recibo.png", false)]) }
                .accessibilityIdentifier("harness.receipt")
            Button("Duplicate") { model.begin([(SampleSavedReceiptsTransport.png("Duplicado"), "Duplicado.png", false)]) }
                .accessibilityIdentifier("harness.duplicate")
            Button("Two receipts") {
                model.begin([(SampleSavedReceiptsTransport.png("Primero"), "Primero.png", false),
                             (SampleSavedReceiptsTransport.png("Segundo"), "Segundo.png", false)])
            }.accessibilityIdentifier("harness.two")
            Button("Unreadable") { model.begin([(SampleSavedReceiptsTransport.png("Ilegible"), "Ilegible.png", false)]) }
                .accessibilityIdentifier("harness.unreadable")
            Button("No date") { model.begin([(SampleSavedReceiptsTransport.png("Sin fecha"), "SinFecha.png", false)]) }
                .accessibilityIdentifier("harness.undated")
            Button("Offline") { model.begin([(SampleSavedReceiptsTransport.png("Sin conexión"), "SinConexion.png", false)]) }
                .accessibilityIdentifier("harness.offline")
            Text(result).accessibilityIdentifier("harness.result")
        }
        .onAppear {
            model.bind(Self.session)
            model.writeByHand = { result = "by hand " + $0.connectionID }
        }
        .onChange(of: model.phase) { _, phase in
            switch phase {
            case .recorded(let activity): result = "recorded " + (activity.amount ?? "")
            case .linked(let id): result = "linked " + id
            case .savedOnly: result = "saved only"
            default: break
            }
        }
        .receiptJourney(model, spanish: spanish) {}
    }
}
#endif
