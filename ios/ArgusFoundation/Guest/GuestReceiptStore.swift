import Foundation
import Combine

/// A receipt kept on this iPhone for the on-device book. It is never sent anywhere and no model reads it.
struct GuestReceipt: Codable, Identifiable, Equatable {
    let id: UUID
    let name: String
    let pdf: Bool
    let createdAt: Date
    /// The movement the person attached it to by hand, if any.
    var movementID: UUID?
    var filename: String { id.uuidString + (pdf ? ".pdf" : ".jpg") }
    var mediaType: String { pdf ? "application/pdf" : "image/jpeg" }
}

/// The book's receipts: files and a small index in a `receipts` folder inside the book's directory, so deleting the
/// book deletes them too. The book file itself is not changed, so its saved format stays the same.
@MainActor
final class GuestReceiptStore: ObservableObject {
    @Published private(set) var receipts: [GuestReceipt] = []
    @Published private(set) var loadFailed = false
    let directory: URL
    private var indexURL: URL { directory.appendingPathComponent("receipts.json") }

    init(bookDirectory: URL) {
        directory = bookDirectory.appendingPathComponent("receipts", isDirectory: true)
        guard FileManager.default.fileExists(atPath: indexURL.path) else { return }
        do { receipts = try JSONDecoder().decode([GuestReceipt].self, from: Data(contentsOf: indexURL)) }
        catch { loadFailed = true }
    }

    /// Keeps each file on this iPhone. Files arrive newest last and are listed newest first.
    @discardableResult
    func save(_ files: [(data: Data, name: String, pdf: Bool)], now: Date = .now) throws -> [GuestReceipt] {
        guard !loadFailed else { throw CocoaError(.fileReadCorruptFile) }
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        var added: [GuestReceipt] = []
        do {
            for file in files where !file.data.isEmpty {
                let receipt = GuestReceipt(id: UUID(), name: file.name, pdf: file.pdf, createdAt: now)
                try file.data.write(to: url(receipt), options: .atomic)
                added.append(receipt)
            }
            try persist(added.reversed() + receipts)
        } catch {
            for receipt in added { try? FileManager.default.removeItem(at: url(receipt)) }
            throw error
        }
        return added
    }

    /// Attaches a receipt to a movement by hand, or detaches it with nil. A movement holds one receipt; attaching
    /// another releases the first, which stays saved.
    func attach(_ id: UUID, to movementID: UUID?) throws {
        guard receipts.contains(where: { $0.id == id }) else { return }
        try persist(receipts.map { receipt in
            var next = receipt
            if receipt.id == id { next.movementID = movementID }
            else if let movementID, receipt.movementID == movementID { next.movementID = nil }
            return next
        })
    }

    func delete(_ id: UUID) throws {
        guard let receipt = receipts.first(where: { $0.id == id }) else { return }
        try persist(receipts.filter { $0.id != id })
        try? FileManager.default.removeItem(at: url(receipt))
    }

    func receipt(for movementID: UUID) -> GuestReceipt? { receipts.first { $0.movementID == movementID } }

    /// Receipts not attached to a movement that still exists.
    func unattached(liveMovements: Set<UUID>) -> [GuestReceipt] {
        receipts.filter { $0.movementID.map { !liveMovements.contains($0) } ?? true }
    }

    func data(_ receipt: GuestReceipt) -> Data? { try? Data(contentsOf: url(receipt)) }

    /// After the book's directory was deleted, forget what was listed.
    func forget() { receipts = [] }

    private func url(_ receipt: GuestReceipt) -> URL { directory.appendingPathComponent(receipt.filename) }

    private func persist(_ values: [GuestReceipt]) throws {
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        try JSONEncoder().encode(values).write(to: indexURL, options: .atomic)
        receipts = values
    }
}
