import SwiftUI
import CuadraoBook

/// The book as the screens read it: the current `DeviceBook` plus whether it can be written. Every change is a
/// pure rule from the package applied here, then saved by the store; nothing in this class touches a network.
@MainActor
final class GuestBookModel: ObservableObject {
    enum Phase: Equatable {
        case loading, ready
        /// Written by a newer version of the app: shown read-only, never rewritten.
        case newerVersion(Int)
        case unreadable
    }

    @Published private(set) var phase: Phase = .loading
    @Published private(set) var book = DeviceBook.empty()
    /// True after a save failed (a full disk, for example); the book in memory is ahead of the file.
    @Published private(set) var saveFailed = false
    private let store: BookStore
    private var loading: Task<Void, Never>?

    init(store: BookStore) {
        self.store = store
        loading = Task { await load() }
    }

    private func load() async {
        switch await store.open() {
        case .fresh(let opened), .existing(let opened), .recovered(let opened):
            book = opened
            phase = .ready
        case .newerVersion(let version):
            phase = .newerVersion(version)
        case .unreadable:
            phase = .unreadable
        }
    }

    /// Applies one rule and saves the result. A rule that refuses leaves the book as it was and rethrows.
    @discardableResult
    func apply(_ rule: (DeviceBook) throws -> DeviceBook) throws -> DeviceBook {
        guard phase == .ready else { return book }
        let next = try rule(book)
        book = next
        save(next)
        return next
    }

    private func save(_ snapshot: DeviceBook) {
        Task {
            do {
                try await store.save(snapshot)
                saveFailed = false
            } catch {
                saveFailed = true
            }
        }
    }

    /// Removes the book and its backups from this iPhone. The model is empty and writable afterwards.
    func deleteEverything() async -> Bool {
        _ = await loading?.value
        do {
            try await store.deleteEverything()
            book = DeviceBook.empty()
            phase = .ready
            saveFailed = false
            return true
        } catch {
            return false
        }
    }
}
