#if DEBUG
import SwiftUI
import ArgusSession

/// Debug-only sample data for driving the saved-receipts screens without a server
/// (`--cuadrao-saved-receipts-sample`). It never ships: Release builds do not compile this file.
actor SampleSavedReceiptsTransport: SavedReceiptsTransport {
    private var documents: [SavedDocument] = []
    private var blobs: [String: Data] = [:]
    private var counter = 0

    init() {
        let first = Self.pdf("Supermercado.pdf"), second = Self.png("Farmacia.png")
        documents = [Self.document("sample-1", "Supermercado.pdf", "application/pdf", first.count),
                     Self.document("sample-2", "Farmacia.png", "image/png", second.count)]
        blobs = ["sample-1": first, "sample-2": second]
        counter = 2
    }

    func list(limit: Int, offset: Int, identity: SessionSnapshot) async throws -> SavedDocumentPage {
        try Self.page(documents)
    }

    func save(_ bytes: Data, mediaType: String, filename: String, identity: SessionSnapshot) async throws -> SavedDocumentCapture {
        if let existing = documents.first(where: { $0.filename == filename }) {
            return try Self.capture(existing.id, replayed: true)
        }
        counter += 1
        let id = "sample-\(counter)"
        documents.insert(Self.document(id, filename, mediaType, bytes.count), at: 0)
        blobs[id] = bytes
        return try Self.capture(id, replayed: false)
    }

    func source(_ id: String, identity: SessionSnapshot) async throws -> Data {
        guard let data = blobs[id] else { throw SessionFailure.rejected(status: 404, code: "financial_document_not_found") }
        return data
    }

    func delete(_ id: String, identity: SessionSnapshot) async throws {
        documents.removeAll { $0.id == id }
        blobs[id] = nil
    }

    /// What each + menu row saves in sample mode, instead of opening the camera, photos or files.
    static func files(for source: ReceiptSourceChoice) -> [(data: Data, name: String, pdf: Bool)] {
        switch source {
        case .scan: [(png("Escaneo"), "Escaneo.png", false)]
        case .photos: [(png("Foto"), "Foto.png", false)]
        case .file, .sample: [(pdf("Archivo"), "Archivo.pdf", true)]
        }
    }

    private static func document(_ id: String, _ name: String, _ type: String, _ size: Int) -> SavedDocument {
        SavedDocument(connectionID: id, filename: name, mediaType: type, sizeBytes: size, sourceAvailable: true,
                      status: "saved", createdAt: "2026-10-08T12:00:00Z", updatedAt: "2026-10-08T12:00:00Z")
    }

    private static func page(_ documents: [SavedDocument]) throws -> SavedDocumentPage {
        let items = documents.map { ["connection_id": $0.connectionID, "filename": $0.filename, "media_type": $0.mediaType,
            "size_bytes": $0.sizeBytes, "source_available": $0.sourceAvailable, "status": $0.status,
            "created_at": $0.createdAt, "updated_at": $0.updatedAt] as [String: Any] }
        return try JSONDecoder().decode(SavedDocumentPage.self, from: JSONSerialization.data(withJSONObject: ["items": items, "next_offset": NSNull()]))
    }

    private static func capture(_ id: String, replayed: Bool) throws -> SavedDocumentCapture {
        try JSONDecoder().decode(SavedDocumentCapture.self, from: JSONSerialization.data(withJSONObject:
            ["connection_id": id, "status": "saved", "replayed": replayed]))
    }

    private static func drawn(_ title: String) -> (UIImage, CGRect) {
        let rect = CGRect(x: 0, y: 0, width: 300, height: 420)
        let image = UIGraphicsImageRenderer(size: rect.size).image { context in
            UIColor.white.setFill(); context.fill(rect)
            let attributes: [NSAttributedString.Key: Any] = [.font: UIFont.systemFont(ofSize: 28, weight: .semibold), .foregroundColor: UIColor.black]
            (title as NSString).draw(at: CGPoint(x: 24, y: 24), withAttributes: attributes)
            UIColor.systemGreen.setFill(); context.fill(CGRect(x: 24, y: 90, width: 252, height: 8))
        }
        return (image, rect)
    }

    static func png(_ title: String) -> Data { drawn(title).0.pngData() ?? Data() }

    static func pdf(_ title: String) -> Data {
        let (image, rect) = drawn(title)
        return UIGraphicsPDFRenderer(bounds: rect).pdfData { context in
            context.beginPage()
            image.draw(in: rect)
        }
    }
}
#endif
