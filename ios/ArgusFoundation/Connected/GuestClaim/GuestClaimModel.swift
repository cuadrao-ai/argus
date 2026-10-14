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
                                   guestWord: spanish ? "invitado" : "guest")
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

    var title: String { spanish ? "Pasar tus datos a tu cuenta" : "Move your data to your account" }
    var previewIntro: String {
        spanish ? "Esto es lo que va a pasar. No se mueve nada hasta que toques Pasar."
            : "This is what will happen. Nothing moves until you tap Move."
    }
    func accounts(_ n: Int) -> String { spanish ? (n == 1 ? "1 cuenta" : "\(n) cuentas") : (n == 1 ? "1 account" : "\(n) accounts") }
    func movements(_ n: Int) -> String { spanish ? (n == 1 ? "1 movimiento" : "\(n) movimientos") : (n == 1 ? "1 transaction" : "\(n) transactions") }
    func renamed(_ n: Int) -> String {
        spanish ? (n == 1 ? "1 cuenta ya tiene ese nombre en tu cuenta y llega como «Nombre (invitado)»."
                          : "\(n) cuentas ya tienen ese nombre en tu cuenta y llegan como «Nombre (invitado)».")
            : (n == 1 ? "1 account already has that name in your account and arrives as “Name (guest)”."
                      : "\(n) accounts already have that name in your account and arrive as “Name (guest)”.")
    }
    func staying(plans: Int) -> String {
        let receipts = spanish ? "los recibos guardados aquí" : "the receipts saved here"
        if plans == 0 { return spanish ? "Se quedan en este iPhone: \(receipts)." : "Staying on this iPhone: \(receipts)." }
        let list = spanish ? (plans == 1 ? "1 meta o presupuesto" : "\(plans) metas y presupuestos") : (plans == 1 ? "1 goal or budget" : "\(plans) goals and budgets")
        return spanish ? "Se quedan en este iPhone, por ahora: \(list) y \(receipts)."
            : "Staying on this iPhone for now: \(list) and \(receipts)."
    }
    var keepsCopy: String {
        spanish ? "Tu copia en este iPhone sigue aquí hasta que el servidor confirme cada cosa."
            : "Your copy on this iPhone stays until the server confirms each item."
    }
    var move: String { spanish ? "Pasar a mi cuenta" : "Move to my account" }
    var discard: String { spanish ? "Descartar" : "Discard" }
    var later: String { spanish ? "Ahora no" : "Not now" }
    var done: String { spanish ? "Listo" : "Done" }
    var retry: String { spanish ? "Reintentar" : "Try again" }
    var discardTitle: String { spanish ? "¿Descartar los datos de invitado?" : "Discard the guest data?" }
    var discardMessage: String {
        spanish ? "Se borran de este iPhone: cuentas, movimientos, metas, presupuestos y recibos. No se puede deshacer."
            : "These are deleted from this iPhone: accounts, transactions, goals, budgets and receipts. This can't be undone."
    }
    var discardFailed: String { spanish ? "No se pudieron borrar. Inténtalo de nuevo." : "They could not be deleted. Try again." }
    func running(_ done: Int, _ total: Int) -> String {
        spanish ? "Pasando tus datos: \(done) de \(total)" : "Moving your data: \(done) of \(total)"
    }
    func finished(_ summary: GuestClaimModel.Summary) -> String {
        let parts = [summary.accounts > 0 ? accounts(summary.accounts) : nil, summary.movements > 0 ? movements(summary.movements) : nil].compactMap { $0 }
        let list = parts.joined(separator: spanish ? " y " : " and ")
        return spanish ? "Pasamos \(list)." : "We moved \(list)."
    }
    func refused(_ n: Int) -> String {
        spanish ? (n == 1 ? "1 movimiento no se pudo pasar y sigue en este iPhone."
                          : "\(n) movimientos no se pudieron pasar y siguen en este iPhone.")
            : (n == 1 ? "1 transaction could not be moved and stays on this iPhone."
                      : "\(n) transactions could not be moved and stay on this iPhone.")
    }
    var finishedKeeps: String {
        spanish ? "Tu copia sigue en este iPhone. Puedes descartarla cuando quieras."
            : "Your copy is still on this iPhone. You can discard it whenever you like."
    }
    func stopped(_ reason: GuestClaimStop) -> String {
        switch reason {
        case .signedOut: return spanish ? "Tu sesión cambió. Inicia sesión y vuelve a intentarlo." : "Your session changed. Sign in and try again."
        case .accountRefused(let name):
            let which = name.map { " «\($0)»" } ?? ""
            return spanish ? "Tu cuenta no aceptó la cuenta\(which). Lo que ya pasó se queda. Tu copia sigue aquí."
                : "Your account did not accept the account\(which). What already moved stays. Your copy is still here."
        case .unreachable:
            return spanish ? "No pudimos terminar. Lo que ya pasó no se repite. Tu copia sigue aquí."
                : "We could not finish. What already moved is not repeated. Your copy is still here."
        }
    }
    var nothingToMove: String { spanish ? "No hay nada que pasar desde este iPhone." : "There is nothing to move from this iPhone." }
    var unreadable: String {
        spanish ? "No pudimos leer los datos de este iPhone. No se cambió nada." : "We could not read this iPhone's data. Nothing was changed."
    }
    var discarded: String { spanish ? "Descartaste los datos de invitado de este iPhone." : "You discarded the guest data on this iPhone." }
}

extension GuestClaimModel: Identifiable {
    nonisolated var id: ObjectIdentifier { ObjectIdentifier(self) }
}
