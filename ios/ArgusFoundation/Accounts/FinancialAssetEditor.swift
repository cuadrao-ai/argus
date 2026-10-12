import SwiftUI
import ArgusSession

@MainActor
final class FinancialAssetEditor: ObservableObject, Identifiable {
    enum Phase { case editing, review, saving, uncertain, conflict, saved }
    let id = UUID()
    let account: FinancialAccount
    let selected: FinancialAssetEstimate?
    let details: Bool
    @Published var amount: String
    @Published var basis: String
    @Published var reason = ""
    @Published var date: Date
    @Published var timeZone: String
    @Published var share: String
    @Published var debtID: UUID?
    @Published private(set) var phase = Phase.editing
    @Published private(set) var preview: FinancialAssetPreview?
    @Published private(set) var errorKey: String?
    private let loop: FinancialLoopModel
    private var command: FinancialAssetEstimateCommand?
    private var detailsCommand: FinancialAssetDetailsCommand?
    private let key = UUID()

    init(account: FinancialAccount, correcting: FinancialAssetEstimate?, details: Bool, loop: FinancialLoopModel) {
        self.account = account; selected = correcting; self.details = details; self.loop = loop
        amount = correcting.map { AccountPresentation.amount($0.amount, locale: .current) } ?? ""
        basis = correcting?.estimateBasis ?? ""
        date = correcting.flatMap { AccountPresentation.parseDate($0.asOf) } ?? Date()
        timeZone = correcting?.timeZone ?? "America/Santo_Domingo"
        share = AssetShareControl.percent(account.ownershipShareBps)
        debtID = account.asset?.relatedDebtAccountId
    }

    var locked: Bool { phase != .editing }
    var uncertain: Bool { phase == .uncertain }
    func edit() { guard phase == .review else { return }; phase = .editing; preview = nil; command = nil }

    func save(locale: Locale) async {
        guard phase != .saving, phase != .conflict, phase != .saved else { return }
        errorKey = nil
        let wasReviewed = phase == .review || phase == .uncertain
        phase = .saving
        do {
            if details {
                if detailsCommand == nil {
                    detailsCommand = FinancialAssetDetailsCommand(expectedVersion: account.version,
                        ownershipShareBps: try AccountEntry.share(share), relatedDebtAccountId: debtID)
                }
                _ = try await loop.confirmAccount(detailsCommand!, accountID: account.id, suffix: "/asset-details", method: "PUT", key: key)
            } else if !wasReviewed {
                guard let value = try AccountEntry.amount(amount, locale: locale) else { throw AccountEntry.Failure.amount }
                var proposed = FinancialAssetEstimateCommand(expectedVersion: account.version, amount: value,
                    asOf: ISO8601DateFormatter().string(from: date), timeZone: timeZone,
                    estimateBasis: basis.isEmpty ? nil : basis, reason: selected == nil ? nil : reason,
                    recordId: selected?.recordId, expectedRevision: selected?.revision)
                let response = try await loop.previewAsset(account.id, command: proposed)
                proposed.previewToken = response.previewToken
                command = proposed; preview = response; phase = .review
                return
            } else {
                guard let command else { throw SessionFailure.invalidResponse }
                _ = try await loop.confirmAccount(command, accountID: account.id, suffix: "/asset-estimates", method: "POST", key: key)
            }
            phase = .saved
        } catch {
            errorKey = FinancialActivityEditor.message(error)
            if let failure = error as? AccountEntry.Failure { errorKey = failure == .share ? "accounts.error.share" : "accounts.error.amount_invalid" }
            if case SessionFailure.rejected(_, let code) = error {
                if code == "estimate_date_order" { errorKey = "assets.error.dateOrder" }
                if code == "liability_required" { errorKey = "assets.error.debt" }
            }
            if loop.pendingConfirmation != nil { phase = .uncertain }
            else if case SessionFailure.rejected(409, _) = error { phase = .conflict }
            else { phase = .editing; command = nil; detailsCommand = nil }
        }
    }
}
