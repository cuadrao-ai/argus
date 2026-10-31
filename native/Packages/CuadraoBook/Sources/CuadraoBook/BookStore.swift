import Foundation

public enum BookStoreError: Error, Equatable, Sendable {
    /// The file belongs to a newer version of the app, or could not be read; nothing may overwrite it.
    case readOnly
}

/// One forward step of the file format, from the version it is keyed by to the next. Pure: bytes in, bytes out.
public typealias BookMigration = @Sendable (Data) throws -> Data

public enum BookMigrations {
    /// Steps keyed by the version they upgrade from. Empty while the format is at version 1.
    public static let all: [Int: BookMigration] = [:]
}

/// The single writer of the device book's file. Every read and write goes through this actor.
///
/// Layout, inside one directory: `book.json` is the book; `book.json.bak` is the last good copy, kept
/// by replacing it only with a file that still decodes; `book.json.v{n}.bak` is the file as it was before
/// a migration from version n. Writes replace atomically. File timestamps are never read.
public actor BookStore {
    public enum Opened: Equatable, Sendable {
        case fresh(DeviceBook)
        case existing(DeviceBook)
        /// The book file was unreadable and the last good copy was restored.
        case recovered(DeviceBook)
        /// Written by a newer version of the app. Read-only; nothing is changed.
        case newerVersion(Int)
        /// Neither the book nor its copy could be read. Read-only until deleted.
        case unreadable
    }

    public static let fileName = "book.json"

    private enum Parsed {
        case book(DeviceBook, bytes: Data)
        case newer(Int)
        case broken
    }

    private let directory: URL
    private let schemaVersion: Int
    private let migrations: [Int: BookMigration]
    private var readOnly = false
    private var newestRevision = -1

    public init(directory: URL, schemaVersion: Int = DeviceBook.currentSchemaVersion,
                migrations: [Int: BookMigration] = BookMigrations.all) {
        self.directory = directory
        self.schemaVersion = schemaVersion
        self.migrations = migrations
    }

    /// `Application Support/CuadraoDeviceBook`, which iOS includes in device backups.
    public static func defaultDirectory() throws -> URL {
        try FileManager.default.url(for: .applicationSupportDirectory, in: .userDomainMask, appropriateFor: nil, create: true)
            .appendingPathComponent("CuadraoDeviceBook", isDirectory: true)
    }

    private var main: URL { directory.appendingPathComponent(Self.fileName) }
    private var backup: URL { directory.appendingPathComponent(Self.fileName + ".bak") }

    public func open() -> Opened {
        let backupData = try? Data(contentsOf: backup)
        guard let data = try? Data(contentsOf: main) else {
            if let backupData, case .book(let book, let bytes) = parse(backupData, keepOriginals: false) {
                try? write(bytes, to: main)
                newestRevision = book.revision
                return .recovered(book)
            }
            return .fresh(DeviceBook(schemaVersion: schemaVersion))
        }
        switch parse(data, keepOriginals: true) {
        case .book(let book, let bytes):
            if bytes != data { try? write(bytes, to: main) }
            newestRevision = book.revision
            return .existing(book)
        case .newer(let version):
            readOnly = true
            return .newerVersion(version)
        case .broken:
            if let backupData, case .book(let book, let bytes) = parse(backupData, keepOriginals: false) {
                try? write(bytes, to: main)
                newestRevision = book.revision
                return .recovered(book)
            }
            readOnly = true
            return .unreadable
        }
    }

    /// Replaces the book file atomically after keeping the previous good file as the backup. A save older than
    /// the newest one written is dropped, so overlapping saves from the app cannot land out of order.
    public func save(_ book: DeviceBook) throws {
        guard !readOnly else { throw BookStoreError.readOnly }
        guard book.revision >= newestRevision else { return }
        var snapshot = book
        snapshot.schemaVersion = schemaVersion
        let data = try Self.encoder.encode(snapshot)
        try createDirectory()
        if let current = try? Data(contentsOf: main), case .book = parse(current, keepOriginals: false) {
            try write(current, to: backup)
        }
        try write(data, to: main)
        newestRevision = book.revision
    }

    /// Removes the book, its backups and the directory, and lets the store start a new book.
    public func deleteEverything() throws {
        if FileManager.default.fileExists(atPath: directory.path) {
            try FileManager.default.removeItem(at: directory)
        }
        readOnly = false
        newestRevision = -1
    }

    // MARK: Reading

    private func parse(_ data: Data, keepOriginals: Bool) -> Parsed {
        guard let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let version = object["schemaVersion"] as? Int else { return .broken }
        if version > schemaVersion { return .newer(version) }
        var bytes = data
        var step = version
        while step < schemaVersion {
            guard let migrate = migrations[step] else { return .broken }
            if keepOriginals { try? keepOriginal(bytes, version: step) }
            guard let next = try? migrate(bytes) else { return .broken }
            bytes = next
            step += 1
        }
        guard let book = try? Self.decoder.decode(DeviceBook.self, from: bytes), book.schemaVersion == schemaVersion else { return .broken }
        return .book(book, bytes: version == schemaVersion ? data : bytes)
    }

    private func keepOriginal(_ bytes: Data, version: Int) throws {
        let copy = directory.appendingPathComponent("\(Self.fileName).v\(version).bak")
        guard !FileManager.default.fileExists(atPath: copy.path) else { return }
        try createDirectory()
        try write(bytes, to: copy)
    }

    // MARK: Writing

    private func createDirectory() throws {
        #if os(iOS)
        let attributes: [FileAttributeKey: Any] = [.protectionKey: FileProtectionType.completeUntilFirstUserAuthentication]
        #else
        let attributes: [FileAttributeKey: Any]? = nil
        #endif
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true, attributes: attributes)
    }

    private func write(_ data: Data, to url: URL) throws {
        #if os(iOS)
        try data.write(to: url, options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
        #else
        try data.write(to: url, options: [.atomic])
        #endif
    }

    private static let encoder: JSONEncoder = {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        encoder.dateEncodingStrategy = .iso8601
        return encoder
    }()

    private static let decoder: JSONDecoder = {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        return decoder
    }()
}
