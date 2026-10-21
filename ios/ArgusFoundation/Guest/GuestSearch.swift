import SwiftUI
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

    private var spanish: Bool { CuadraoCopy.isSpanish() }
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
                    + (account.archived ? [CuadraoCopy.text("copy.guestSearch.2d40384a7e", spanish: spanish)] : []),
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
                    + amountWords(plan.targetMinor, digits: plan.digits) + (plan.archived ? [CuadraoCopy.text("copy.guestSearch.e620893a44", spanish: spanish)] : []),
                currency: plan.currency))
        }
        return found
    }

    private var hits: [SearchEntry] { SearchIndex.filter(entries, query: query, scope: scope, currency: currency.isEmpty ? nil : currency) }
    private func hits(_ section: SearchSection) -> [SearchEntry] { hits.filter { $0.section == section } }
    private var filterCount: Int { currency.isEmpty ? 0 : 1 }
    private var start: CuadraoSearchStart {
        CuadraoSearchStart(suggestions: CuadraoSearchStart.suggestions(
            frequent: book.liveMovements().filter { $0.kind == .expense }.compactMap { $0.category }
                .map { GuestMovementPresentation.categoryTitle($0, spanish: spanish) },
            names: book.accounts.filter { !$0.archived }.map { GuestAccountPresentation.title($0, spanish: spanish) }))
    }

    var body: some View {
        NavigationStack {
            CuadraoSearchContent(query: $query, kind: $kind, kinds: kinds, spanish: spanish, filterCount: filterCount,
                                 filterSummary: currency, clearFilters: { currency = "" }, focused: $focused,
                                 accessibility: .connected, start: start, recentsKey: "guest") {
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
                Picker(CuadraoCopy.text("copy.connectedTransactionSheet.9b96ad5816", spanish: spanish), selection: $currency) {
                    Text(CuadraoCopy.text("copy.cuadraoSearchCanvas.22417a3c9d", spanish: spanish)).tag("")
                    ForEach(book.currencies, id: \.self) { Text($0).tag($0) }
                }.accessibilityIdentifier("search.currency")
                Section {
                    Button(CuadraoCopy.text("copy.cuadraoSearchCanvas.18b5a4bccd", spanish: spanish)) { currency = "" }
                } footer: {
                    Text(CuadraoCopy.text("copy.guestSearch.aa9926cd49", spanish: spanish))
                }
            }
        }
        .modifier(CuadraoNavigationScrollObserver(scroll: scroll, enabled: active))
        .toolbar(.hidden, for: .tabBar)
    }

    private var emptyTitle: String? {
        guard query.isEmpty, filterCount == 0, book.accounts.isEmpty, book.plans.isEmpty else { return nil }
        return CuadraoCopy.text("copy.guestSearch.e9d48a4a8b", spanish: spanish)
    }

    private var emptyDetail: String? {
        guard query.isEmpty, filterCount == 0 else { return nil }
        switch kind {
        case .accounts: return CuadraoCopy.text("copy.cuadraoSearchPresentation.91789e4b19", spanish: spanish)
        case .activity: return CuadraoCopy.text("copy.guestSearch.7cb3f3028b", spanish: spanish)
        case .plans: return CuadraoCopy.text("copy.guestSearch.10ee3d11a4", spanish: spanish)
        default: return CuadraoCopy.text("copy.guestSearch.50c07ca878", spanish: spanish)
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
                                     account.archived ? (CuadraoCopy.text("copy.connectedAccountPresentation.7268bbe2c2", spanish: spanish)) : nil].compactMap { $0 }.joined(separator: " · "),
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
                                     plan.archived ? (CuadraoCopy.text("copy.cuadraoSearchCanvas.14cfd7be1d", spanish: spanish)) : nil].compactMap { $0 }.joined(separator: " · "),
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
            CuadraoSearchHeading(title: CuadraoCopy.text("copy.guestSearch.d2b818b2f8", spanish: spanish), count: hits.count)
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
            viewing = ViewedReceipt(id: receipt.id.uuidString, filename: receipt.name, mediaType: receipt.mediaType, data: data)
        }
    }
}
