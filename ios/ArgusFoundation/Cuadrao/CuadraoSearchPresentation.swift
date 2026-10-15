import SwiftUI

enum CuadraoSearchAccessibility {
    case preview, connected, household

    var prefix: String {
        switch self {
        case .preview: "cuadrao.search"
        case .connected: "search"
        case .household: "household.search"
        }
    }
    var clearQuery: String { prefix + (self == .preview ? ".query.clear" : ".clear") }
    var clearEmptyQuery: String { prefix + (self == .preview ? ".clear" : ".empty.clear") }
    func kind(_ kind: CanvasSearchKind) -> String {
        guard self != .preview else { return prefix + ".kind.\(kind)" }
        switch kind {
        case .accounts: return prefix + ".filter.account"
        default: return prefix + ".filter.\(kind)"
        }
    }
}

struct CuadraoSearchContent<Results: View, Filters: View>: View {
    @Binding var query: String
    @Binding var kind: CanvasSearchKind
    let kinds: [CanvasSearchKind]
    let spanish: Bool
    let filterCount: Int
    let filterSummary: String
    let clearFilters: () -> Void
    let focused: FocusState<Bool>.Binding
    var accessibility = CuadraoSearchAccessibility.preview
    var showsFilters = true
    var loading = false
    var refresh: (@MainActor () async -> Void)?
    /// Scroll restoration measures every row's frame, so the connected host builds rows eagerly.
    var eagerRows = false
    /// Shown instead of the results while nothing is typed, no filter is on and the filter is All.
    var start: CuadraoSearchStart?
    /// Whose recent searches these are; a different key never sees them.
    var recentsKey = "preview"
    @ViewBuilder let results: () -> Results
    @ViewBuilder let filters: () -> Filters
    @State private var showingFilters = false
    @ObservedObject private var recents = CuadraoSearchRecents.shared

    private var showsStart: Bool {
        guard let start, query.isEmpty, kind == .all, filterCount == 0 else { return false }
        return !start.suggestions.isEmpty || !recents.items(for: recentsKey).isEmpty
    }

    var body: some View {
        ScrollView {
            Group {
                if showsStart, let start {
                    CuadraoSearchStartView(start: start, spanish: spanish, prefix: accessibility.prefix, recentsKey: recentsKey) { query = $0 }
                } else if eagerRows {
                    VStack(alignment: .leading, spacing: 0, content: results)
                } else {
                    LazyVStack(alignment: .leading, spacing: 0, content: results)
                }
            }.padding(.horizontal, 24).padding(.bottom, 24)
        }.coordinateSpace(name: "search.viewport")
            .modifier(CuadraoSearchRefresh(action: refresh))
            .scrollDismissesKeyboard(.interactively)
            .accessibilityIdentifier(accessibility.prefix + ".results")
            .onDisappear { recents.remember(query, key: recentsKey) }
            .overlay(alignment: .top) {
                if loading {
                    ProgressView("accounts.loading").padding(.vertical, 12)
                        .frame(maxWidth: .infinity).background(WelcomePalette.background)
                        .accessibilityIdentifier(accessibility.prefix + ".loading").allowsHitTesting(false)
                }
            }
            .cuadraoScrollBar(edge: .top) {
                VStack(alignment: .leading, spacing: 18) {
                    searchField
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 24) {
                            ForEach(kinds, id: \.self) { value in
                                Button { kind = value; focused.wrappedValue = false } label: {
                                    Text(value.title(spanish)).font(.subheadline)
                                        .foregroundStyle(kind == value ? Color.primary : .secondary)
                                        .frame(minHeight: 44)
                                        .overlay(alignment: .bottom) {
                                            Rectangle().fill(kind == value ? WelcomePalette.pine : .clear).frame(height: 2)
                                        }.contentShape(Rectangle())
                                }.buttonStyle(.plain)
                                    .accessibilityAddTraits(kind == value ? .isSelected : [])
                                    .accessibilityIdentifier(accessibility.kind(value))
                            }
                        }
                    }.scrollBounceBehavior(refresh == nil ? .automatic : .basedOnSize, axes: .horizontal)
                        .accessibilityIdentifier(accessibility.prefix + ".kinds")
                    if filterCount > 0 {
                        HStack {
                            Text(filterSummary).accessibilityIdentifier(accessibility.prefix + ".filter-summary")
                            Spacer()
                            Button(spanish ? "Quitar filtros" : "Clear filters", action: clearFilters)
                                .frame(minHeight: 44)
                        }.font(.caption).foregroundStyle(.secondary)
                    }
                }.padding(.horizontal, 24).padding(.top, 24).padding(.bottom, 18)
                    .background(WelcomePalette.background.opacity(0.92))
            }
            .cuadraoSoftScrollEdges()
            .background(WelcomePalette.background)
            .toolbar(.hidden, for: .navigationBar)
            .sheet(isPresented: $showingFilters) {
                NavigationStack {
                    Form(content: filters)
                        .navigationTitle(spanish ? "Filtros" : "Filters")
                        .navigationBarTitleDisplayMode(.inline)
                        .toolbar {
                            CuadraoDoneToolbar(title: spanish ? "Listo" : "Done", identifier: accessibility.prefix + ".filters.done") { showingFilters = false }
                        }
                }.presentationDetents([.medium, .large]).presentationDragIndicator(.visible)
            }
    }

    private var searchField: some View {
        HStack(spacing: 10) {
            Image(systemName: "magnifyingglass").foregroundStyle(.secondary).accessibilityHidden(true)
            TextField(spanish ? "Buscar" : "Search", text: $query)
                .focused(focused).autocorrectionDisabled().textInputAutocapitalization(.never)
                .submitLabel(.search).onSubmit { recents.remember(query, key: recentsKey); focused.wrappedValue = false }
                .accessibilityIdentifier(accessibility.prefix + ".query")
            if !query.isEmpty {
                Button { recents.remember(query, key: recentsKey); query = "" } label: { Image(systemName: "xmark.circle.fill").frame(width: 44, height: 44) }
                    .foregroundStyle(.secondary).accessibilityLabel(spanish ? "Borrar búsqueda" : "Clear search")
                    .accessibilityIdentifier(accessibility.clearQuery)
            }
            if showsFilters {
                Button { focused.wrappedValue = false; showingFilters = true } label: {
                    HStack(spacing: 4) {
                        Image(systemName: "slider.horizontal.3")
                        if filterCount > 0 { Text(String(filterCount)).font(.caption) }
                    }.frame(minWidth: 44, minHeight: 48)
                }.accessibilityIdentifier(accessibility.prefix + ".filters")
                    .accessibilityLabel(spanish ? "Filtros, \(filterCount) activos" : "Filters, \(filterCount) active")
            }
        }.overlay(alignment: .bottom) { Rectangle().fill(WelcomePalette.separator).frame(height: 1) }
    }
}

/// Pull to refresh belongs to the results alone; inherited by the kind rail it lets the rail drag vertically.
private struct CuadraoSearchRefresh: ViewModifier {
    let action: (@MainActor () async -> Void)?
    @ViewBuilder func body(content: Content) -> some View {
        if let action { content.refreshable { await action() } } else { content }
    }
}

struct CuadraoSearchEmptyState: View {
    @Binding var query: String
    @Binding var kind: CanvasSearchKind
    let spanish: Bool
    let filterCount: Int
    let clearFilters: () -> Void
    var title: String?
    var detail: String?
    var accessibility = CuadraoSearchAccessibility.preview

    private var browsing: Bool { query.isEmpty && filterCount == 0 }
    var body: some View {
        CuadraoEmptyView(
            title: title ?? (browsing ? emptyTitle : (spanish ? "Sin resultados" : "No results")),
            detail: detail ?? (browsing ? emptyDetail : (spanish ? "Prueba otro nombre o cambia los filtros." : "Try another name or change the filters.")),
            actionTitle: action?.title, action: action?.run, identifier: accessibility.prefix + ".empty",
            actionIdentifier: action?.identifier)
    }

    /// One action, the most useful first: undo the filters that hide results, then clear the words, then widen the kind.
    private var action: (title: String, run: () -> Void, identifier: String)? {
        if filterCount > 0 {
            return (spanish ? "Restablecer filtros" : "Reset filters", { clearFilters(); kind = .all }, accessibility.prefix + ".reset")
        }
        if !query.isEmpty { return (spanish ? "Borrar búsqueda" : "Clear search", { query = "" }, accessibility.clearEmptyQuery) }
        if kind != .all { return (spanish ? "Buscar en todo" : "Search everything", { kind = .all }, accessibility.prefix + ".everything") }
        return nil
    }

    private var emptyTitle: String {
        switch kind {
        case .all: spanish ? "Tu información, aquí" : "Your information, here"
        case .accounts: spanish ? "Sin cuentas todavía" : "No accounts yet"
        case .activity: spanish ? "Sin movimientos todavía" : "No activity yet"
        case .plans: spanish ? "Sin planes todavía" : "No plans yet"
        case .chats: spanish ? "Sin chats todavía" : "No chats yet"
        case .files: spanish ? "Sin archivos todavía" : "No files yet"
        case .memory: spanish ? "Sin recuerdos todavía" : "No memories yet"
        }
    }
    private var emptyDetail: String {
        switch kind {
        case .all:
            if CuadraoFirstRelease.hasAssistant {
                spanish ? "Busca cuentas, movimientos, planes y conversaciones." : "Search accounts, activity, plans and conversations."
            } else {
                spanish ? "Busca cuentas, movimientos y planes." : "Search accounts, activity and plans."
            }
        case .accounts:
            if CuadraoFirstRelease.hasAssistant {
                spanish ? "Añade una cuenta desde Inicio para encontrarla aquí." : "Add an account from Home to find it here."
            } else {
                spanish ? "Añade una cuenta con el botón + para encontrarla aquí." : "Add an account with the + button to find it here."
            }
        case .activity: spanish ? "Los movimientos que registres en tus cuentas aparecerán aquí." : "Activity recorded in your accounts will appear here."
        case .plans:
            if CuadraoFirstRelease.hasAssistant {
                spanish ? "Crea una meta, un presupuesto o un plan de deuda en Plan." : "Create a goal, budget or debt plan in Plan."
            } else {
                spanish ? "Crea una meta, un presupuesto o un plan de deuda con el botón +." : "Create a goal, budget or debt plan with the + button."
            }
        case .chats: spanish ? "Tus conversaciones guardadas aparecerán aquí." : "Your saved conversations will appear here."
        case .files: spanish ? "Los archivos disponibles aparecerán aquí." : "Available files will appear here."
        case .memory: spanish ? "El contexto que confirmes aparecerá aquí." : "Context you confirm will appear here."
        }
    }
}

extension CanvasExpenseCategory {
    static func fromRecordedCategory(_ category: String) -> Self? {
        switch category {
        case "dining": .food
        case "groceries": .groceries
        case "transport": .transport
        case "housing": .home
        case "other": .other
        default: nil
        }
    }
}

struct CuadraoSearchHeading: View {
    let title: String
    let count: Int
    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            Text(title).font(CuadraoTypography.section)
            Text(String(count)).font(.caption).foregroundStyle(.secondary)
        }.padding(.top, 20).padding(.bottom, 10).accessibilityAddTraits(.isHeader)
    }
}

struct CuadraoSearchResultRow: View {
    let title: String
    let detail: String
    let spanish: Bool
    var date: Date?
    var symbol: String?
    var accountKind: CanvasAccountKind?
    var category: CanvasExpenseCategory?

    var body: some View {
        HStack(spacing: 16) {
            if let accountKind { CanvasAccountIcon(kind: accountKind) }
            else if let category { CuadraoExpenseCategoryIcon(category: category) }
            else if let symbol {
                Image(systemName: symbol).font(.body).foregroundStyle(WelcomePalette.pine)
                    .frame(width: 42, height: 42).background(WelcomePalette.surface, in: RoundedRectangle(cornerRadius: 13)).accessibilityHidden(true)
            }
            VStack(alignment: .leading, spacing: 6) {
                Text(title).font(CuadraoTypography.action)
                Text(detail).font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            }
            Spacer(minLength: 8)
            if let date { CuadraoChatDate(date: date, spanish: spanish) }
            else { Image(systemName: "chevron.right").font(.caption).foregroundStyle(.tertiary).accessibilityHidden(true) }
        }.frame(minHeight: 62).padding(.vertical, 8).contentShape(Rectangle())
    }
}
