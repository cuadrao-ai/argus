import Combine
import SwiftUI
import CuadraoBook

/// Whether the person is in the on-device book, and the one book model while they are. The choice is a plain
/// preference, not a financial record, so it lives outside the book and survives a book that cannot be written.
@MainActor
final class GuestModeController: ObservableObject {
    static let activeKey = "cuadrao.guest.active"
    /// Set the first time an account is signed in on this iPhone and never cleared: from then on the book is not offered as a way in.
    static let accountKey = "cuadrao.account.signedIn"

    @Published private(set) var active: Bool
    @Published private(set) var accountSignedInBefore: Bool
    @Published private(set) var model: GuestBookModel? {
        didSet { follow(model) }
    }
    /// The book's receipts, kept beside it on this iPhone.
    @Published private(set) var receipts: GuestReceiptStore?
    private let directory: URL
    /// Where the book lives, for the screen that moves it into an account.
    var bookDirectory: URL { directory }
    private var phaseObservation: AnyCancellable?

    init() {
        let directory = Self.bookDirectory()
        #if DEBUG
        if CuadraoGuestLaunch.resets {
            try? FileManager.default.removeItem(at: directory)
            UserDefaults.standard.removeObject(forKey: Self.activeKey)
            UserDefaults.standard.removeObject(forKey: Self.accountKey)
            GuestNotice.reset()
        }
        if CuadraoGuestLaunch.noticesSeen { GuestNotice.allCases.forEach { $0.markSeen() } }
        #endif
        self.directory = directory
        active = UserDefaults.standard.bool(forKey: Self.activeKey) && AgeConfirmationStore().confirmation != nil
        #if DEBUG
        if CuadraoGuestLaunch.accountSignedInBefore { UserDefaults.standard.set(true, forKey: Self.accountKey) }
        #endif
        accountSignedInBefore = UserDefaults.standard.bool(forKey: Self.accountKey)
        if active { open() }
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

    func noteAccountSignedIn() {
        guard !accountSignedInBefore else { return }
        accountSignedInBefore = true
        UserDefaults.standard.set(true, forKey: Self.accountKey)
    }

    /// Whether this iPhone still holds a book, even one the person has not opened in this launch.
    var hasStoredBook: Bool {
        (try? FileManager.default.contentsOfDirectory(atPath: directory.path))?.isEmpty == false
    }

    /// Opens the book, creating it on the first save. Nothing is sent anywhere.
    func enter() {
        guard AgeConfirmationStore().confirmation != nil else { return }
        if model == nil { open() }
        set(active: true)
    }

    /// Leaves the book on the device untouched and returns to the ordinary welcome.
    func leave() {
        set(active: false)
        model = nil
        receipts = nil
    }

    private func open() {
        model = GuestBookModel(store: BookStore(directory: directory))
        receipts = GuestReceiptStore(bookDirectory: directory)
    }

    /// Deletes the book from this iPhone, then leaves it. False when the files could not be removed.
    func deleteDataAndLeave() async -> Bool {
        let removed = await model?.deleteEverything() ?? true
        if removed { receipts?.forget(); GuestNotice.reset(); leave() }
        return removed
    }

    /// Deletes the book from this iPhone even when it is not open, as when an account is signed in. False when the
    /// files could not be removed.
    func discardStoredBook() async -> Bool {
        if model != nil { return await deleteDataAndLeave() }
        let store = BookStore(directory: directory)
        do { try await store.deleteEverything() } catch { return false }
        GuestReceiptStore(bookDirectory: directory).forget()
        GuestNotice.reset()
        leave()
        objectWillChange.send()
        return true
    }

    private func set(active next: Bool) {
        active = next
        UserDefaults.standard.set(next, forKey: Self.activeKey)
    }
}
