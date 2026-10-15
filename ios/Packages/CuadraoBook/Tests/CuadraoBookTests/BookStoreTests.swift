import Foundation
import Testing
@testable import CuadraoBook

/// A fresh directory per test, removed afterwards.
private final class Sandbox {
    let directory: URL
    init() {
        directory = FileManager.default.temporaryDirectory.appendingPathComponent("book-" + UUID().uuidString, isDirectory: true)
    }
    deinit { try? FileManager.default.removeItem(at: directory) }
    func url(_ name: String) -> URL { directory.appendingPathComponent(name) }
    func exists(_ name: String) -> Bool { FileManager.default.fileExists(atPath: url(name).path) }
    func bytes(_ name: String) throws -> Data { try Data(contentsOf: url(name)) }
    func put(_ text: String, as name: String) throws {
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        try Data(text.utf8).write(to: url(name))
    }
}

@Suite("Book store")
struct BookStoreTests {
    @Test func aMissingFileOpensAFreshBookAndWritesNothing() async {
        let box = Sandbox()
        let opened = await BookStore(directory: box.directory).open()
        #expect(opened == .fresh(DeviceBook.empty()))
        #expect(!box.exists("book.json"))
        #expect(!box.exists(""), "not even the folder until the first save")
    }

    @Test func aSavedBookComesBackExactly() async throws {
        let box = Sandbox()
        let store = BookStore(directory: box.directory)
        _ = await store.open()
        let book = try DeviceBook.empty().settingPrimaryCurrency("jpy")
        try await store.save(book)
        let reopened = await BookStore(directory: box.directory).open()
        #expect(reopened == .existing(book))
        #expect(book.settings.primaryCurrency == "JPY")
    }

    @Test func eachSaveKeepsThePreviousGoodFileAsTheBackup() async throws {
        let box = Sandbox()
        let store = BookStore(directory: box.directory)
        _ = await store.open()
        let first = try DeviceBook.empty().settingPrimaryCurrency("DOP")
        let second = try first.settingPrimaryCurrency("USD")
        try await store.save(first)
        #expect(!box.exists("book.json.bak"), "nothing to back up before a second write")
        let firstBytes = try box.bytes("book.json")
        try await store.save(second)
        #expect(try box.bytes("book.json.bak") == firstBytes)
        #expect(try box.bytes("book.json") != firstBytes)
    }

    @Test func aBrokenBookFileIsRestoredFromTheLastGoodCopy() async throws {
        let box = Sandbox()
        let store = BookStore(directory: box.directory)
        _ = await store.open()
        let first = try DeviceBook.empty().settingPrimaryCurrency("DOP")
        try await store.save(first)
        try await store.save(try first.settingPrimaryCurrency("USD"))
        try box.put("{ not json", as: "book.json")
        let reopened = await BookStore(directory: box.directory).open()
        #expect(reopened == .recovered(first))
        let again = await BookStore(directory: box.directory).open()
        #expect(again == .existing(first), "the restored file is the book now")
    }

    @Test func aFileBrokenAfterOpeningNeverReplacesTheLastGoodBackup() async throws {
        let box = Sandbox()
        let store = BookStore(directory: box.directory)
        _ = await store.open()
        let first = try DeviceBook.empty().settingPrimaryCurrency("DOP")
        let second = try first.settingPrimaryCurrency("USD")
        let third = try second.settingPrimaryCurrency("EUR")
        try await store.save(first)
        try await store.save(second)
        let goodBackup = try box.bytes("book.json.bak")
        try box.put("garbage", as: "book.json")
        try await store.save(third)
        #expect(try box.bytes("book.json.bak") == goodBackup, "garbage is never copied over the last good file")
        #expect(await BookStore(directory: box.directory).open() == .existing(third))
    }

    @Test func whenNothingIsReadableTheStoreRefusesToOverwrite() async throws {
        let box = Sandbox()
        try box.put("nope", as: "book.json")
        try box.put("also nope", as: "book.json.bak")
        let store = BookStore(directory: box.directory)
        #expect(await store.open() == .unreadable)
        await #expect(throws: BookStoreError.readOnly) { try await store.save(DeviceBook.empty()) }
        #expect(try box.bytes("book.json") == Data("nope".utf8))
    }

    @Test func aNewerBookOpensReadOnlyAndIsLeftAlone() async throws {
        let box = Sandbox()
        let future = #"{"schemaVersion":99,"revision":4,"settings":{},"somethingNew":[1,2,3]}"#
        try box.put(future, as: "book.json")
        let store = BookStore(directory: box.directory)
        #expect(await store.open() == .newerVersion(99))
        await #expect(throws: BookStoreError.readOnly) { try await store.save(DeviceBook.empty()) }
        #expect(try box.bytes("book.json") == Data(future.utf8))
        #expect(!box.exists("book.json.bak"))
    }

    @Test func anOlderBookIsMigratedForwardAfterKeepingItsOriginal() async throws {
        let box = Sandbox()
        let original = #"{"schemaVersion":0,"currency":"dop"}"#
        try box.put(original, as: "book.json")
        let step: BookMigration = { data in
            let object = try #require(try JSONSerialization.jsonObject(with: data) as? [String: Any])
            return try JSONSerialization.data(withJSONObject: [
                "schemaVersion": 1, "revision": 0, "settings": ["primaryCurrency": (object["currency"] as? String ?? "").uppercased()]
            ])
        }
        let store = BookStore(directory: box.directory, schemaVersion: 1, migrations: [0: step])
        let opened = await store.open()
        guard case .existing(let book) = opened else { Issue.record("expected a migrated book, got \(opened)"); return }
        #expect(book.settings.primaryCurrency == "DOP")
        #expect(try box.bytes("book.json.v0.bak") == Data(original.utf8))
        let again = await BookStore(directory: box.directory, schemaVersion: 1, migrations: [0: step]).open()
        #expect(again == .existing(book), "the migrated file is what is on disk now")
    }

    @Test func aMigrationThatFailsLeavesTheOriginalAlone() async throws {
        let box = Sandbox()
        let original = #"{"schemaVersion":0}"#
        try box.put(original, as: "book.json")
        struct Failure: Error {}
        let store = BookStore(directory: box.directory, schemaVersion: 1, migrations: [0: { _ in throw Failure() }])
        #expect(await store.open() == .unreadable)
        #expect(try box.bytes("book.json") == Data(original.utf8))
    }

    @Test func aMissingMigrationStepIsUnreadableNotGuessed() async throws {
        let box = Sandbox()
        try box.put(#"{"schemaVersion":0}"#, as: "book.json")
        #expect(await BookStore(directory: box.directory, schemaVersion: 1, migrations: [:]).open() == .unreadable)
    }

    @Test func deletingRemovesTheBookTheBackupsAndTheFolder() async throws {
        let box = Sandbox()
        let store = BookStore(directory: box.directory)
        _ = await store.open()
        let book = try DeviceBook.empty().settingPrimaryCurrency("DOP")
        try await store.save(book)
        try await store.save(try book.settingPrimaryCurrency("USD"))
        try box.put("{}", as: "book.json.v0.bak")
        try await store.deleteEverything()
        #expect(!box.exists(""))
        #expect(await store.open() == .fresh(DeviceBook.empty()))
        try await store.save(DeviceBook.empty())
        #expect(box.exists("book.json"), "a new book can start after a delete")
    }

    @Test func deletingAnUnreadableBookLetsTheStoreWriteAgain() async throws {
        let box = Sandbox()
        try box.put("nope", as: "book.json")
        let store = BookStore(directory: box.directory)
        #expect(await store.open() == .unreadable)
        try await store.deleteEverything()
        try await store.save(DeviceBook.empty())
        #expect(await BookStore(directory: box.directory).open() == .existing(DeviceBook.empty()))
    }

    @Test func aStaleSaveCannotOverwriteANewerOne() async throws {
        let box = Sandbox()
        let store = BookStore(directory: box.directory)
        _ = await store.open()
        let older = try DeviceBook.empty().settingPrimaryCurrency("DOP")
        let newer = try older.settingPrimaryCurrency("USD")
        try await store.save(newer)
        try await store.save(older)
        #expect(await BookStore(directory: box.directory).open() == .existing(newer))
    }

    @Test func theBookIsLeftInDeviceBackups() async throws {
        let box = Sandbox()
        let store = BookStore(directory: box.directory)
        _ = await store.open()
        try await store.save(DeviceBook.empty())
        let values = try box.directory.resourceValues(forKeys: [.isExcludedFromBackupKey])
        #expect(values.isExcludedFromBackup != true)
    }

    @Test func theWrittenFileIsPlainSortedJSONWithTheSchemaVersion() async throws {
        let box = Sandbox()
        let store = BookStore(directory: box.directory)
        _ = await store.open()
        try await store.save(try DeviceBook.empty().settingPrimaryCurrency("DOP"))
        let text = try #require(String(data: box.bytes("book.json"), encoding: .utf8))
        #expect(text == #"{"accounts":[],"movements":[],"plans":[],"revision":1,"schemaVersion":1,"settings":{"primaryCurrency":"DOP"}}"#)
    }

    @Test func primaryCurrencyAcceptsOnlyTheServersSet() throws {
        #expect(throws: BookRuleError.currencyUnsupported) { try DeviceBook.empty().settingPrimaryCurrency("XXX") }
        #expect(try DeviceBook.empty().settingPrimaryCurrency(nil).settings.primaryCurrency == nil)
        #expect(try DeviceBook.empty().settingPrimaryCurrency(" usd ").settings.primaryCurrency == "USD")
    }
}
