import ArgusSession
import CuadraoBook
import Foundation
import SwiftUI

/// The screen "Pasar tus datos a tu cuenta": reads the on-device book, says what would move, and moves it only when
/// the person asks. Nothing in the book is removed until the person discards it.
@MainActor
final class GuestClaimModel: ObservableObject {
    enum Phase: Equatable {
        case loading
        /// The book has nothing left to move.
        case nothingToMove
        case preview
        case running(done: Int, total: Int)
        case finished
        case stopped(GuestClaimStop)
        /// The book could not be read, so nothing is offered.
        case unreadable
        case discarded
    }

    struct Summary: Equatable {
        var accounts = 0
        var movements = 0
        var refused = 0
        var renamed = 0
        var stayingPlans = 0
    }

    @Published private(set) var phase = Phase.loading
    /// What is still to move: counts for the preview, and the words the finished screen repeats.
    @Published private(set) var remaining = Summary()
    @Published private(set) var moved = Summary()
    @Published var confirmingDiscard = false
    @Published private(set) var discarding = false
    @Published private(set) var discardFailed = false

    let directory: URL
    let spanish: Bool
    private let server: any GuestClaimServer
    private let discardBook: () async -> Bool
    private var plan = GuestClaimPlan.make(book: .empty(), existingNicknames: [])
    private var progress = GuestClaimProgress()
    private var owner: UUID?
    private let file: GuestClaimProgressFile

    init(directory: URL, server: any GuestClaimServer, spanish: Bool, discard: @escaping () async -> Bool) {
        self.directory = directory
        self.server = server
        self.spanish = spanish
        self.discardBook = discard
        file = GuestClaimProgressFile(directory: directory)
    }

    func load() async {
        phase = .loading
        let opened = await BookStore(directory: directory).open()
        let book: DeviceBook
        switch opened {
        case .fresh(let value), .existing(let value), .recovered(let value): book = value
        case .newerVersion, .unreadable: phase = .unreadable; return
        }
        guard let owner = await server.owner() else { phase = .stopped(.signedOut); return }
        self.owner = owner
        progress = file.load()
        let mine = progress.owner(owner)
        let existing: [FinancialAccount]
        do { existing = try await server.accounts() } catch { phase = .stopped(.unreachable); return }
        // Names this claim already put in the account are not "taken" by someone else.
        let ours = Set(mine.accounts.values)
        plan = GuestClaimPlan.make(book: book, existingNicknames: existing.filter { !ours.contains($0.id) }.compactMap(\.nickname),
                                   guestWord: CuadraoCopy.text("copy.guestClaimModel.2feae16dad", spanish: spanish))
        refresh()
        phase = remaining.accounts == 0 && remaining.movements == 0 ? (moved.accounts + moved.movements > 0 ? .finished : .nothingToMove) : .preview
    }

    func start() async {
        guard owner != nil, case .preview = phase else { return }
        let engine = GuestClaimEngine(server: server, save: { [file] progress in file.save(progress) },
                                      report: { [weak self] done, total in
            Task { @MainActor in
                // A late report must not undo the finished or stopped screen.
                if case .running = self?.phase { self?.phase = .running(done: done, total: total) }
            }
        })
        phase = .running(done: 0, total: plan.accounts.count + plan.movements.count)
        let (result, next) = await engine.run(plan: plan, progress: progress)
        progress = next
        refresh()
        phase = result.stop.map(Phase.stopped) ?? .finished
    }

    func retry() async { await load() }

    func askToDiscard() { confirmingDiscard = true }

    /// Deletes this iPhone's copy. Asked once, by the alert, before this runs.
    func discard() async {
        discarding = true; discardFailed = false
        let removed = await discardBook()
        discarding = false
        if removed { phase = .discarded } else { discardFailed = true }
    }

    private func refresh() {
        let mine = owner.map { progress.owner($0) } ?? GuestClaimProgress.Owner()
        let accountsLeft = plan.accounts.filter { mine.accounts[$0.id] == nil }
        let movementsLeft = plan.movements.filter { !mine.movements.contains($0.id) && !mine.refused.contains($0.id) }
        remaining = Summary(accounts: accountsLeft.count, movements: movementsLeft.count, refused: 0,
                            renamed: accountsLeft.filter(\.renamed).count, stayingPlans: plan.stayingPlans)
        moved = Summary(accounts: plan.accounts.filter { mine.accounts[$0.id] != nil }.count,
                        movements: plan.movements.filter { mine.movements.contains($0.id) }.count,
                        refused: plan.movements.filter { mine.refused.contains($0.id) }.count,
                        renamed: plan.accounts.filter { $0.renamed && mine.accounts[$0.id] != nil }.count,
                        stayingPlans: plan.stayingPlans)
    }
}

/// Every word on the screen, Spanish first. No em dash.
struct GuestClaimCopy {
    let spanish: Bool

    var title: String { CuadraoCopy.text("copy.guestClaimModel.fa23d40e14", spanish: spanish) }
    var previewIntro: String {
        CuadraoCopy.text("copy.guestClaimModel.ec059d5439", spanish: spanish)
    }
    func accounts(_ n: Int) -> String { (n == 1 ? CuadraoCopy.text("copy.guestClaimModel.7f1de1bd62", spanish: spanish) : CuadraoCopy.text("copy.guestClaimModel.0cbbaf6808", spanish: spanish, String(describing: n))) }
    func movements(_ n: Int) -> String { (n == 1 ? CuadraoCopy.text("copy.guestClaimModel.afbd153c48", spanish: spanish) : CuadraoCopy.text("copy.guestClaimModel.2ee0db831a", spanish: spanish, String(describing: n))) }
    func renamed(_ n: Int) -> String {
        (n == 1 ? CuadraoCopy.text("copy.guestClaimModel.9a5ebb7b90", spanish: spanish) : CuadraoCopy.text("copy.guestClaimModel.74877abbc2", spanish: spanish, String(describing: n)))
    }
    func staying(plans: Int) -> String {
        let receipts = CuadraoCopy.text("copy.guestClaimModel.db320c4b47", spanish: spanish)
        if plans == 0 { return CuadraoCopy.text("copy.guestClaimModel.f750983c27", spanish: spanish, String(describing: receipts)) }
        let list = (plans == 1 ? CuadraoCopy.text("copy.guestClaimModel.11f157d734", spanish: spanish) : CuadraoCopy.text("copy.guestClaimModel.0177dc1211", spanish: spanish, String(describing: plans)))
        return CuadraoCopy.text("copy.guestClaimModel.34dd3f2fc2", spanish: spanish, String(describing: list), String(describing: receipts))
    }
    var keepsCopy: String {
        CuadraoCopy.text("copy.guestClaimModel.1e586bba81", spanish: spanish)
    }
    var move: String { CuadraoCopy.text("copy.guestClaimModel.8a25da6687", spanish: spanish) }
    var discard: String { CuadraoCopy.text("copy.guestClaimModel.adac3a9868", spanish: spanish) }
    var later: String { CuadraoCopy.text("copy.guestClaimModel.12e8d67ee6", spanish: spanish) }
    var done: String { CuadraoCopy.text("copy.guestClaimModel.bd6b05a681", spanish: spanish) }
    var retry: String { CuadraoCopy.text("copy.connectedCuadraoAuth.ada77fc089", spanish: spanish) }
    var discardTitle: String { CuadraoCopy.text("copy.guestClaimModel.25d1aca8f1", spanish: spanish) }
    var discardMessage: String {
        CuadraoCopy.text("copy.guestClaimModel.61fc603c81", spanish: spanish)
    }
    var discardFailed: String { CuadraoCopy.text("copy.guestClaimModel.8552e7b3fa", spanish: spanish) }
    func running(_ done: Int, _ total: Int) -> String {
        CuadraoCopy.text("copy.guestClaimModel.f7f309ef76", spanish: spanish, String(describing: done), String(describing: total))
    }
    func finished(_ summary: GuestClaimModel.Summary) -> String {
        let parts = [summary.accounts > 0 ? accounts(summary.accounts) : nil, summary.movements > 0 ? movements(summary.movements) : nil].compactMap { $0 }
        let list = parts.joined(separator: CuadraoCopy.text("copy.guestClaimModel.531970a9ba", spanish: spanish))
        return CuadraoCopy.text("copy.guestClaimModel.09160bf6a4", spanish: spanish, String(describing: list))
    }
    func refused(_ n: Int) -> String {
        (n == 1 ? CuadraoCopy.text("copy.guestClaimModel.1c27f0db5f", spanish: spanish) : CuadraoCopy.text("copy.guestClaimModel.2d1ce0cd64", spanish: spanish, String(describing: n)))
    }
    var finishedKeeps: String {
        CuadraoCopy.text("copy.guestClaimModel.efbbce1627", spanish: spanish)
    }
    func stopped(_ reason: GuestClaimStop) -> String {
        switch reason {
        case .signedOut: return CuadraoCopy.text("copy.guestClaimModel.adf31b4054", spanish: spanish)
        case .accountRefused(let name):
            let which = name.map { " «\($0)»" } ?? ""
            return CuadraoCopy.text("copy.guestClaimModel.416df2f65e", spanish: spanish, String(describing: which))
        case .unreachable:
            return CuadraoCopy.text("copy.guestClaimModel.5f2330088e", spanish: spanish)
        }
    }
    var nothingToMove: String { CuadraoCopy.text("copy.guestClaimModel.23a236d04d", spanish: spanish) }
    var unreadable: String {
        CuadraoCopy.text("copy.guestClaimModel.6853986cc3", spanish: spanish)
    }
    var discarded: String { CuadraoCopy.text("copy.guestClaimModel.ff5d8c9362", spanish: spanish) }
}

extension GuestClaimModel: Identifiable {
    nonisolated var id: ObjectIdentifier { ObjectIdentifier(self) }
}
