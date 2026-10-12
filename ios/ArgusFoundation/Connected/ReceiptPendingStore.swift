import Foundation

/// Receipts kept on this iPhone while there is no connection, one folder per account, with the person's answer about
/// reading. They are sent when the network returns and removed once the server has them.
struct ReceiptPendingStore {
    struct Entry: Codable, Equatable {
        let id: UUID
        let name: String
        let pdf: Bool
        let consent: Bool
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

    func keep(_ files: [(data: Data, name: String, pdf: Bool)], consent: Bool) throws {
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        var all = entries
        for file in files {
            let entry = Entry(id: UUID(), name: file.name, pdf: file.pdf, consent: consent)
            try file.data.write(to: url(entry), options: [.atomic, .completeFileProtection])
            all.append(entry)
        }
        try JSONEncoder().encode(all).write(to: manifest, options: .atomic)
    }

    func data(_ entry: Entry) -> Data? { try? Data(contentsOf: url(entry)) }

    func remove(_ entry: Entry) {
        try? FileManager.default.removeItem(at: url(entry))
        let rest = entries.filter { $0.id != entry.id }
        if rest.isEmpty { try? FileManager.default.removeItem(at: directory) }
        else { try? JSONEncoder().encode(rest).write(to: manifest, options: .atomic) }
    }

    private func url(_ entry: Entry) -> URL { directory.appendingPathComponent(entry.id.uuidString) }
}
