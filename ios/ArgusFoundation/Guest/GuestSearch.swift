import SwiftUI
import ArgusSession
import CuadraoBook

/// Where a search result leads. The shell turns it into the right tab and screen.
enum GuestSearchTarget: Equatable {
    case account(UUID)
    case movement(UUID)
    case plan(UUID)
}

/// Search over the book, in the shared search layout. The words people can type are written here, in the device language;
/// the matching itself is the package's pure index.
struct GuestSearchTab: View {
    @ObservedObject var model: GuestBookModel
    let scroll: CuadraoNavigationScroll
    let active: Bool
    let open: (GuestSearchTarget) -> Void
    @State private var query = ""
    @State private var kind = CanvasSearchKind.all
    @State private var currency = ""
    @FocusState private var focused: Bool
    @Environment(\.locale) private var locale
    @Environment(\.guestReceipts) private var receipts

    private var spanish: Bool { locale.language.languageCode?.identifier == "es" }
    private var receiptHits: [GuestReceipt] {
        guard let receipts, kind == .all else { return [] }
        return GuestReceiptSearchRows.hits(receipts, book: book, query: query, spanish: spanish, locale: locale)
    }
    private var kinds: [CanvasSearchKind] { CanvasSearchKind.connected(hasAssistant: false) }
    private var book: DeviceBook { model.book }

    private var scope: SearchScope {
        switch kind {
        case .accounts: .accounts
        case .activity: .activity
        case .plans: .plans
        default: .all
        }
    }

    private func amountWords(_ minor: Int64, digits: Int) -> [String] {
        [MoneyFormatter.plain(minor, digits: digits), MoneyFormatter.grouped(minor, digits: digits),
         MoneyFormatter.grouped(minor, digits: digits, grouping: locale.groupingSeparator ?? ",", decimal: locale.decimalSeparator ?? ".")]
    }

    private var entries: [SearchEntry] {
        var found: [SearchEntry] = []
        for account in book.accounts {
            let balance = book.balance(of: account.id)
            found.append(SearchEntry(id: account.id, section: .accounts,
                text: [GuestAccountPresentation.title(account, spanish: spanish), GuestAccountPresentation.artwork(account.kind).title(spanish), account.currency]
                    + (balance.map { amountWords($0.minor, digits: $0.digits) } ?? [])
                    + (account.archived ? [spanish ? "archivada" : "archived"] : []),
                currency: account.currency))
        }
        for movement in book.liveMovements() {
            guard let account = book.account(movement.accountID) else { continue }
            found.append(SearchEntry(id: movement.id, section: .activity,
                text: [GuestMovementPresentation.title(movement, spanish: spanish), movement.note ?? "",
                       movement.category.map { GuestMovementPresentation.categoryTitle($0, spanish: spanish) } ?? "",
                       GuestMovementPresentation.kindTitle(movement.kind, spanish: spanish),
                       account.currency] + amountWords(movement.amountMinor, digits: account.digits),
                currency: account.currency))
        }
        for plan in book.plans {
            found.append(SearchEntry(id: plan.id, section: .plans,
                text: [plan.name, GuestPlanPresentation.kindTitle(plan.kind, spanish: spanish), plan.currency]
                    + amountWords(plan.targetMinor, digits: plan.digits) + (plan.archived ? [spanish ? "archivado" : "archived"] : []),
                currency: plan.currency))
        }
        return found
    }

    private var hits: [SearchEntry] { SearchIndex.filter(entries, query: query, scope: scope, currency: currency.isEmpty ? nil : currency) }
    private func hits(_ section: SearchSection) -> [SearchEntry] { hits.filter { $0.section == section } }
    private var filterCount: Int { currency.isEmpty ? 0 : 1 }

    var body: some View {
        NavigationStack {
            CuadraoSearchContent(query: $query, kind: $kind, kinds: kinds, spanish: spanish, filterCount: filterCount,
                                 filterSummary: currency, clearFilters: { currency = "" }, focused: $focused,
                                 accessibility: .connected) {
                if hits.isEmpty && receiptHits.isEmpty {
                    CuadraoSearchEmptyState(query: $query, kind: $kind, spanish: spanish, filterCount: filterCount,
                        clearFilters: { currency = "" }, title: emptyTitle, detail: emptyDetail, accessibility: .connected)
                        .padding(.top, 36)
                }
                accountRows
                activityRows
                planRows
                if let receipts, kind == .all { GuestReceiptSearchRows(store: receipts, model: model, query: query, spanish: spanish, open: { focused = false; open($0) }) }
            } filters: {
                Picker(spanish ? "Moneda" : "Currency", selection: $currency) {
                    Text(spanish ? "Todas" : "All").tag("")
                    ForEach(book.currencies, id: \.self) { Text($0).tag($0) }
                }.accessibilityIdentifier("search.currency")
                Section {
                    Button(spanish ? "Restablecer filtros" : "Reset filters") { currency = "" }
                } footer: {
                    Text(spanish ? "La moneda filtra cuentas, movimientos y planes." : "Currency filters accounts, activity and plans.")
                }
            }
        }
        .modifier(CuadraoNavigationScrollObserver(scroll: scroll, enabled: active))
        .toolbar(.hidden, for: .tabBar)
    }

    private var emptyTitle: String? {
        guard query.isEmpty, filterCount == 0, book.accounts.isEmpty, book.plans.isEmpty else { return nil }
        return spanish ? "Tu libro, aquí" : "Your book, here"
    }

    private var emptyDetail: String? {
        guard query.isEmpty, filterCount == 0 else { return nil }
        switch kind {
        case .accounts: return spanish ? "Añade una cuenta con el botón + para encontrarla aquí." : "Add an account with the + button to find it here."
        case .activity: return spanish ? "Los movimientos que registres aparecerán aquí." : "Activity you record will appear here."
        case .plans: return spanish ? "Crea una meta o un presupuesto con el botón + para encontrarlo aquí." : "Create a goal or a budget with the + button to find it here."
        default: return spanish ? "Busca cuentas, movimientos y planes de este iPhone." : "Search the accounts, activity and plans on this iPhone."
        }
    }

    @ViewBuilder private var accountRows: some View {
        let rows = hits(.accounts)
        if (kind == .all || kind == .accounts) && !rows.isEmpty {
            CuadraoSearchHeading(title: CanvasSearchKind.accounts.title(spanish), count: rows.count)
            ForEach(rows) { entry in
                if let account = book.account(entry.id) {
                    Button { focused = false; open(.account(account.id)) } label: {
                        CuadraoSearchResultRow(title: GuestAccountPresentation.title(account, spanish: spanish),
                            detail: [GuestAccountPresentation.artwork(account.kind).title(spanish), account.currency,
                                     account.archived ? (spanish ? "Archivada" : "Archived") : nil].compactMap { $0 }.joined(separator: " · "),
                            spanish: spanish, accountKind: GuestAccountPresentation.artwork(account.kind))
                    }.buttonStyle(.plain).accessibilityIdentifier("guest.search.account." + account.id.uuidString)
                    Divider().foregroundStyle(WelcomePalette.separator)
                }
            }
        }
    }

    @ViewBuilder private var activityRows: some View {
        let rows = hits(.activity)
        if (kind == .all || kind == .activity) && !rows.isEmpty {
            CuadraoSearchHeading(title: CanvasSearchKind.activity.title(spanish), count: rows.count)
            ForEach(rows) { entry in
                if let movement = book.movement(entry.id) {
                    let row = GuestMovementPresentation.row(movement, in: book, spanish: spanish, locale: locale)
                    Button { focused = false; open(.movement(movement.id)) } label: {
                        CuadraoSearchResultRow(title: row.title, detail: row.detail + " · " + row.amount, spanish: spanish, symbol: row.icon)
                    }.buttonStyle(.plain).accessibilityIdentifier("guest.search.movement." + movement.id.uuidString)
                    Divider().foregroundStyle(WelcomePalette.separator)
                }
            }
        }
    }

    @ViewBuilder private var planRows: some View {
        let rows = hits(.plans)
        if (kind == .all || kind == .plans) && !rows.isEmpty {
            CuadraoSearchHeading(title: CanvasSearchKind.plans.title(spanish), count: rows.count)
            ForEach(rows) { entry in
                if let plan = book.plan(entry.id) {
                    Button { focused = false; open(.plan(plan.id)) } label: {
                        CuadraoSearchResultRow(title: plan.name,
                            detail: [GuestPlanPresentation.kindTitle(plan.kind, spanish: spanish), plan.currency,
                                     plan.archived ? (spanish ? "Archivado" : "Archived") : nil].compactMap { $0 }.joined(separator: " · "),
                            spanish: spanish, symbol: GuestPlanPresentation.look(plan.look).symbol)
                    }.buttonStyle(.plain).accessibilityIdentifier("guest.search.plan." + plan.id.uuidString)
                    Divider()
                }
            }
        }
    }
}

/// Receipts kept on this iPhone that match the query: by name, saved date, or the movement they are attached to.
struct GuestReceiptSearchRows: View {
    @ObservedObject var store: GuestReceiptStore
    @ObservedObject var model: GuestBookModel
    let query: String
    let spanish: Bool
    let open: (GuestSearchTarget) -> Void
    @Environment(\.locale) private var locale
    @State private var viewing: ViewedReceipt?

    var body: some View {
        let hits = Self.hits(store, book: model.book, query: query, spanish: spanish, locale: locale)
        if !hits.isEmpty {
            CuadraoSearchHeading(title: spanish ? "Recibos" : "Receipts", count: hits.count)
            ForEach(hits) { receipt in
                Button { select(receipt) } label: {
                    CuadraoSearchResultRow(title: receipt.name, detail: detail(receipt), spanish: spanish, symbol: receipt.pdf ? "doc.text" : "photo")
                }.buttonStyle(.plain).accessibilityIdentifier("guest.search.receipt." + receipt.id.uuidString)
                Divider().foregroundStyle(WelcomePalette.separator)
            }
            .sheet(item: $viewing) { SavedReceiptViewer(receipt: $0, copy: SavedReceiptCopy(spanish: spanish)) }
        }
    }

    static func hits(_ store: GuestReceiptStore, book: DeviceBook, query: String, spanish: Bool, locale: Locale) -> [GuestReceipt] {
        store.matching(query) { receipt in
            guard let id = receipt.movementID, let movement = book.movement(id), !movement.deleted else { return "" }
            let row = GuestMovementPresentation.row(movement, in: book, spanish: spanish, locale: locale)
            return [row.title, row.detail, row.amount, GuestMovementPresentation.amount(movement, in: book, locale: locale)]
                .joined(separator: " ")
        }
    }

    private func detail(_ receipt: GuestReceipt) -> String {
        let day = receipt.createdAt.formatted(.dateTime.day().month(.abbreviated).year().locale(locale))
        guard let id = receipt.movementID, let movement = model.book.movement(id), !movement.deleted else { return day }
        return day + " · " + GuestMovementPresentation.title(movement, spanish: spanish)
    }

    /// An attached receipt opens its movement; an unattached one opens the file.
    private func select(_ receipt: GuestReceipt) {
        if let id = receipt.movementID, let movement = model.book.movement(id), !movement.deleted {
            open(.movement(id))
        } else if let data = store.data(receipt) {
            let stamp = ISO8601DateFormatter().string(from: receipt.createdAt)
            viewing = ViewedReceipt(document: SavedDocument(connectionID: receipt.id.uuidString, filename: receipt.name,
                mediaType: receipt.mediaType, sizeBytes: data.count, sourceAvailable: true, status: "saved",
                createdAt: stamp, updatedAt: stamp), data: data)
        }
    }
}
