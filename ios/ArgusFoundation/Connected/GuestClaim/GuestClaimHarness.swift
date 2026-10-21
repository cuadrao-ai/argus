#if DEBUG
import CuadraoBook
import SwiftUI

/// Runs the claim screen against a stand-in server and a book written to a temporary folder, so the whole journey
/// can be driven with no account and no network. `--guest-claim-harness` opens it; the other arguments shape the server:
/// `--guest-claim-fail-after N` stops the server after N accounts, `--guest-claim-refuse-note TEXT` refuses a movement.
struct GuestClaimHarness: View {
    @StateObject private var model: GuestClaimModel
    @State private var closed = false
    @State private var seeded = false
    private let seed: () async -> Void

    init() {
        let arguments = ProcessInfo.processInfo.arguments
        func value(_ flag: String) -> String? {
            arguments.firstIndex(of: flag).flatMap { arguments.indices.contains($0 + 1) ? arguments[$0 + 1] : nil }
        }
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("guest-claim-harness-\(UUID().uuidString)", isDirectory: true)
        let moment = Date().addingTimeInterval(-86_400 * 3)
        let zone = TimeZone.current.identifier
        var book = DeviceBook.empty()
        let main = UUID(), card = UUID()
        book = (try? book.addingAccount(BookAccountDraft(kind: .checking, currency: "DOP", nickname: "Main", amountText: "1000"), id: main, now: moment, zone: zone)) ?? book
        book = (try? book.addingAccount(BookAccountDraft(kind: .creditCard, currency: "DOP", nickname: "Card", amountText: "250.50"), id: card, now: moment, zone: zone)) ?? book
        book = (try? book.addingAccount(BookAccountDraft(kind: .savings, currency: "USD", nickname: "Ahorros del año"), now: moment, zone: zone)) ?? book
        for (index, note) in ["Taxi", "Café", "Pay"].enumerated() {
            let draft = MovementDraft(kind: note == "Pay" ? .income : .expense, accountID: main, amountText: "\(20 + index)",
                                      occurredAt: moment.addingTimeInterval(Double(3_600 * (index + 1))), note: note, category: .transport)
            book = (try? book.recordingMovement(draft, now: moment.addingTimeInterval(86_400), zone: zone)) ?? book
        }
        book = (try? book.addingPlan(BookPlanDraft(kind: .budget, name: "Food", currency: "DOP", targetText: "300"), now: moment, zone: zone)) ?? book
        let store = BookStore(directory: directory)
        let seeded = book
        seed = { try? await store.save(seeded) }
        let script = SampleGuestClaimServer.Script(
            existingNames: ["Main", "Ahorros del año", "Efectivo"], failCreateAfter: value("--guest-claim-fail-after").flatMap(Int.init),
            refuseNotes: value("--guest-claim-refuse-note").map { [$0] } ?? [], delay: .milliseconds(350))
        let spanish = CuadraoCopy.isSpanish()
        _model = StateObject(wrappedValue: GuestClaimModel(
            directory: directory, server: SampleGuestClaimServer(script: script), spanish: spanish,
            discard: { (try? await BookStore(directory: directory).deleteEverything()) != nil }))
    }

    var body: some View {
        if closed {
            Text("closed").accessibilityIdentifier("guest.claim.harness.closed")
        } else if !seeded {
            ProgressView().task { await seed(); seeded = true }
        } else {
            GuestClaimSheet(model: model, close: { closed = true })
        }
    }
}
#endif
