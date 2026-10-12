import Combine
import SwiftUI
import CuadraoBook

/// Whether the person is in the on-device book, and the one book model while they are. The choice is a plain
/// preference, not a financial record, so it lives outside the book and survives a book that cannot be written.
@MainActor
final class GuestModeController: ObservableObject {
    static let activeKey = "cuadrao.guest.active"

    @Published private(set) var active: Bool
    @Published private(set) var model: GuestBookModel? {
        didSet { follow(model) }
    }
    private let directory: URL
    private var phaseObservation: AnyCancellable?

    init() {
        let directory = Self.bookDirectory()
        #if DEBUG
        if CuadraoGuestLaunch.resets {
            try? FileManager.default.removeItem(at: directory)
            UserDefaults.standard.removeObject(forKey: Self.activeKey)
        }
        #endif
        self.directory = directory
        active = UserDefaults.standard.bool(forKey: Self.activeKey)
        if active { model = GuestBookModel(store: BookStore(directory: directory)) }
        follow(model)
    }

    /// The router needs to know when the book finishes opening, and a nested model does not reach it on its own.
    private func follow(_ model: GuestBookModel?) {
        phaseObservation = model?.$phase.removeDuplicates().sink { [weak self] _ in self?.objectWillChange.send() }
    }

    private static func bookDirectory() -> URL {
        #if DEBUG
        if let custom = CuadraoGuestLaunch.directory { return custom }
        #endif
        return (try? BookStore.defaultDirectory())
            ?? FileManager.default.temporaryDirectory.appendingPathComponent("CuadraoDeviceBook", isDirectory: true)
    }

    /// Opens the book, creating it on the first save. Nothing is sent anywhere.
    func enter() {
        if model == nil { model = GuestBookModel(store: BookStore(directory: directory)) }
        set(active: true)
    }

    /// Leaves the book on the device untouched and returns to the ordinary welcome.
    func leave() {
        set(active: false)
        model = nil
    }

    /// Deletes the book from this iPhone, then leaves it. False when the files could not be removed.
    func deleteDataAndLeave() async -> Bool {
        let removed = await model?.deleteEverything() ?? true
        if removed { leave() }
        return removed
    }

    private func set(active next: Bool) {
        active = next
        UserDefaults.standard.set(next, forKey: Self.activeKey)
    }
}
