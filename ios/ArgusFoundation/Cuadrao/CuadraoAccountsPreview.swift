import SwiftUI

// Local design fixtures only. The financial client remains the owner of real money.
enum CanvasAccountKind: String, CaseIterable, Identifiable {
    case cash, checking, savings, investment, card, loan, property, vehicle, asset
    var id: String { rawValue }
    var isDebt: Bool { self == .card || self == .loan }
    var isAsset: Bool { [.property, .vehicle, .asset].contains(self) }
    func title(_ es: Bool) -> String {
        switch self {
        case .cash: CuadraoCopy.text("copy.cuadraoAccountsPreview.e25a8f2245", spanish: es)
        case .checking: CuadraoCopy.text("copy.cuadraoAccountsPreview.d72be7f6b4", spanish: es)
        case .savings: CuadraoCopy.text("copy.cuadraoAccountsPreview.de934ee5cb", spanish: es)
        case .investment: CuadraoCopy.text("copy.cuadraoAccountsPreview.b1041af38f", spanish: es)
        case .card: CuadraoCopy.text("copy.cuadraoAccountsPreview.d6351846a6", spanish: es)
        case .loan: CuadraoCopy.text("copy.cuadraoAccountsPreview.5c2f55db09", spanish: es)
        case .property: CuadraoCopy.text("copy.cuadraoAccountsPreview.951ad7f8d3", spanish: es)
        case .vehicle: CuadraoCopy.text("copy.cuadraoAccountsPreview.50f7fb4624", spanish: es)
        case .asset: CuadraoCopy.text("copy.cuadraoAccountsPreview.fa6bcfad9e", spanish: es)
        }
    }
}

struct CanvasAccount: Identifiable {
    var id = UUID()
    var name: String
    var kind: CanvasAccountKind
    var currency = "DOP"
    var balance: Decimal?
    var share = 100
    var archived = false
    var spaceID = CanvasSpace.personalID
    var sharedWithHousehold = false
    func displayName(_ es: Bool) -> String { name.isEmpty ? kind.title(es) : name }
    func balanceLabel(_ es: Bool) -> String {
        kind.isDebt ? (CuadraoCopy.text("copy.cuadraoAccountsPreview.3bf64e270f", spanish: es)) : kind.isAsset
            ? (CuadraoCopy.text("copy.cuadraoAccountsPreview.d7a2d9accc", spanish: es)) : (CuadraoCopy.text("copy.cuadraoAccountsPreview.02e2073456", spanish: es))
    }
}

struct CanvasActivity: Identifiable {
    var id = UUID()
    let accountID: UUID
    let title: String
    let amount: Decimal
    let date: Date
    let income: Bool
    var category: CanvasExpenseCategory = .other
}

@Observable final class CuadraoAccountsPreview {
    var accounts: [CanvasAccount] = []
    var activity: [CanvasActivity] = []
    var balanceObservations: [CanvasBalanceObservation] = []
    var expenseCoverageStarts: [UUID: Date] = [:]
    func spendingCoverageStart(currency: String) -> Date? {
        let ids = scopedAccounts.filter { $0.currency == currency }.map(\.id)
        let starts = ids.compactMap { expenseCoverageStarts[$0] }
        guard !ids.isEmpty, starts.count == ids.count else { return nil }
        return starts.max()
    }
    var spaces: [CanvasSpace] = []
    var household: CanvasHouseholdState = .alone
    var selectedSpaceID = CanvasSpace.personalID
    init(populated: Bool, spanish: Bool) { reset(populated: populated, spanish: spanish) }
    var active: [CanvasAccount] { scopedAccounts.filter { !$0.archived } }
    var archived: [CanvasAccount] { scopedAccounts.filter(\.archived) }
    func account(_ id: UUID) -> CanvasAccount? { accounts.first { $0.id == id } }
    func replace(_ account: CanvasAccount) {
        if let i = accounts.firstIndex(where: { $0.id == account.id }) { accounts[i] = account }
        else { accounts.append(account) }
    }
    func archive(_ id: UUID, _ archived: Bool) {
        guard let i = accounts.firstIndex(where: { $0.id == id }) else { return }
        accounts[i].archived = archived
    }
    func reorder(_ ids: [UUID]) {
        guard Set(ids) == Set(active.map(\.id)) else { return }
        accounts = CuadraoCollectionOrder.applying(ids, to: accounts)
        UserDefaults.standard.set(accounts.map { $0.id.uuidString }, forKey: "cuadrao.design.account-order")
    }
    func move(from: IndexSet, to: Int) {
        var visible = active
        visible.move(fromOffsets: from, toOffset: to)
        reorder(visible.map(\.id))
    }
    func reset(populated: Bool, spanish: Bool) {
        household = populated ? .joined("Alex") : .alone
        selectedSpaceID = CanvasSpace.personalID
        spaces = [CanvasSpace(id: CanvasSpace.personalID, kind: .personal, name: "")]
        if populated { spaces.append(CanvasSpace(id: CanvasSpace.householdID, kind: .household, name: "")) }
        accounts = populated ? [
            CanvasAccount(name: CuadraoCopy.text("copy.cuadraoAccountsPreview.99e65d3ca4", spanish: spanish), kind: .checking, balance: 39400),
            CanvasAccount(name: "", kind: .cash, balance: 3020),
            CanvasAccount(name: CuadraoCopy.text("copy.cuadraoAccountsPreview.f28a70cb95", spanish: spanish), kind: .savings, balance: 68000)
        ] : []
        if populated {
            accounts.append(CanvasAccount(name: CuadraoCopy.text("copy.cuadraoAccountsPreview.24f397ad0e", spanish: spanish),
                kind: .checking, balance: 18500, spaceID: CanvasSpace.householdID, sharedWithHousehold: true))
            accounts.append(CanvasAccount(name: CuadraoCopy.text("copy.cuadraoAccountsPreview.9268d1bb03", spanish: spanish),
                kind: .savings, balance: 25000, spaceID: CanvasSpace.householdID, sharedWithHousehold: true))
        }
        // Stable local fixture identities allow a viewer's order to survive relaunch.
        for index in accounts.indices {
            accounts[index].id = UUID(uuidString: String(format: "00000000-0000-4000-8000-%012d", index + 1))!
        }
        let orderKey = "cuadrao.design.account-order"
        if ProcessInfo.processInfo.arguments.contains("--plan-reset") { UserDefaults.standard.removeObject(forKey: orderKey) }
        let saved = (UserDefaults.standard.stringArray(forKey: orderKey) ?? []).compactMap(UUID.init(uuidString:))
        let known = Set(accounts.map(\.id))
        let order = saved.filter { known.contains($0) } + accounts.map(\.id).filter { !saved.contains($0) }
        // Integration keeps first-use previews empty: sample history only joins populated previews.
        balanceObservations = populated ? CanvasBalanceHistory.examples(accounts: accounts, now: .now) : []
        activity = []
        expenseCoverageStarts = [:]
        if let first = accounts.first, let cash = accounts.last(where: { $0.kind == .cash }) {
            activity = [
                CanvasActivity(accountID: first.id, title: CuadraoCopy.text("copy.cuadraoAccountsPreview.266df955fc", spanish: spanish), amount: 650, date: .now, income: false, category: .food),
                CanvasActivity(accountID: cash.id, title: CuadraoCopy.text("copy.cuadraoAccountsPreview.f8d48c3c52", spanish: spanish), amount: 180, date: .now, income: false, category: .food)
            ]
        }
        if let shared = accounts.first(where: { $0.sharedWithHousehold }) {
            activity.append(CanvasActivity(accountID: shared.id, title: CuadraoCopy.text("copy.cuadraoAccountsPreview.34164df7c7", spanish: spanish),
                amount: 2450, date: .now, income: false, category: .groceries))
        }
        if populated {
            activity += CanvasSpendingHistory.examples(accounts: accounts, spanish: spanish, now: .now)
            // This preview explicitly owns a continuous recording window, including quiet days.
            let start = CanvasPreviewHistory.days(now: .now).first ?? .now
            expenseCoverageStarts = Dictionary(uniqueKeysWithValues: accounts.map { ($0.id, start) })
            if ProcessInfo.processInfo.arguments.contains("--insights-empty-month") {
                let month = Calendar.current.dateInterval(of: .month, for: Date.now)!
                activity.removeAll { $0.date >= month.start }
            }
            if ProcessInfo.processInfo.arguments.contains("--insights-first-use") {
                activity = []; expenseCoverageStarts = [:]; balanceObservations = []
            }
            if ProcessInfo.processInfo.arguments.contains("--insights-no-coverage") { expenseCoverageStarts = [:] }
            accounts = CuadraoCollectionOrder.applying(order, to: accounts)
        }
    }
}


struct CanvasAccountIcon: View {
    let kind: CanvasAccountKind
    var size: CGFloat = 23
    var body: some View {
        Image("CuadraoAccount-" + kind.rawValue)
            .resizable().scaledToFit().frame(width: size, height: size)
            .foregroundStyle(WelcomePalette.pine).accessibilityHidden(true)
    }
}

struct CanvasActionRow: View {
    let title: String
    let symbol: String
    let action: () -> Void
    var body: some View {
        Button(action: action) {
            HStack(spacing: 16) {
                Image(systemName: symbol).frame(width: 24).accessibilityHidden(true)
                Text(title).frame(maxWidth: .infinity, alignment: .leading)
            }.font(.body).padding(.vertical, 17).contentShape(Rectangle())
        }.buttonStyle(.plain)
    }
}

struct CanvasAccountRow: View {
    let account: CanvasAccount
    let spanish: Bool
    var body: some View {
        CanvasAccountRowContent(value: CanvasAccountRowValue(
            title: account.displayName(spanish),
            subtitle: account.kind.title(spanish) + (account.sharedWithHousehold ? (CuadraoCopy.text("copy.cuadraoAccountsPreview.6fdcb74b09", spanish: spanish)) : ""),
            artwork: account.kind,
            amount: account.balance.map { CanvasMoney.format($0, currency: account.currency) } ?? "—",
            amountCaption: account.currency + (account.kind.isDebt ? (CuadraoCopy.text("copy.connectedAccountPresentation.0a5b992f57", spanish: spanish)) : "")))
    }
}
