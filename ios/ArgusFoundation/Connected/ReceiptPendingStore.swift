import Foundation

/// Receipts kept on this iPhone while there is no connection, one folder per account, with the person's answer about
/// reading. They are sent when the network returns and removed once the server has them. The folder is excluded from
/// backup, every file is protected while the phone is locked, and the folder is cleared when its account signs out.
struct ReceiptPendingStore {
    struct Entry: Codable, Equatable {
        let id: UUID
        let name: String
        let pdf: Bool
        let consent: Bool
        /// The server refused this file for good; it is skipped so the receipts behind it still go.
        var rejected: Bool?
    }

    let directory: URL

    init(directory: URL) { self.directory = directory }

    /// The account's folder under Application Support.
    init?(account: String, fileManager: FileManager = .default) {
        guard let base = fileManager.urls(for: .applicationSupportDirectory, in: .userDomainMask).first else { return nil }
        directory = base.appendingPathComponent("pending-receipts", isDirectory: true)
            .appendingPathComponent(account, isDirectory: true)
    }

    private var manifest: URL { directory.appendingPathComponent("pending.json") }

    var entries: [Entry] {
        guard let data = try? Data(contentsOf: manifest) else { return [] }
        return (try? JSONDecoder().decode([Entry].self, from: data)) ?? []
    }

    @discardableResult
    func keep(_ files: [(data: Data, name: String, pdf: Bool)], consent: Bool) throws -> [UUID] {
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        var folder = directory
        var values = URLResourceValues()
        values.isExcludedFromBackup = true
        try folder.setResourceValues(values)
        var all = entries
        var kept: [UUID] = []
        for file in files {
            let entry = Entry(id: UUID(), name: file.name, pdf: file.pdf, consent: consent)
            try file.data.write(to: url(entry), options: [.atomic, .completeFileProtection])
            all.append(entry)
            kept.append(entry.id)
        }
        try save(all)
        return kept
    }

    func remove(_ ids: [UUID]) { for entry in entries where ids.contains(entry.id) { remove(entry) } }

    /// The file's bytes. `nil` while it cannot be read (for example while the phone is locked); `missing` tells the two apart.
    func data(_ entry: Entry) -> Data? { try? Data(contentsOf: url(entry)) }
    func missing(_ entry: Entry) -> Bool { !FileManager.default.fileExists(atPath: url(entry).path) }

    func remove(_ entry: Entry) {
        try? FileManager.default.removeItem(at: url(entry))
        let rest = entries.filter { $0.id != entry.id }
        if rest.isEmpty { clear() } else { try? save(rest) }
    }

    func markRejected(_ entry: Entry) {
        try? save(entries.map { $0.id == entry.id ? Entry(id: $0.id, name: $0.name, pdf: $0.pdf, consent: $0.consent, rejected: true) : $0 })
    }

    /// Removes every kept receipt of this account from the iPhone.
    func clear() { try? FileManager.default.removeItem(at: directory) }

    private func save(_ all: [Entry]) throws {
        try JSONEncoder().encode(all).write(to: manifest, options: [.atomic, .completeFileProtection])
    }

    private func url(_ entry: Entry) -> URL { directory.appendingPathComponent(entry.id.uuidString) }
}
