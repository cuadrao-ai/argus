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
                            Button(CuadraoCopy.text("copy.cuadraoSearchPresentation.e3973e4b7c", spanish: spanish), action: clearFilters)
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
                        .navigationTitle(CuadraoCopy.text("copy.cuadraoSearchPresentation.7ace9eae19", spanish: spanish))
                        .navigationBarTitleDisplayMode(.inline)
                        .toolbar {
                            CuadraoDoneToolbar(title: CuadraoCopy.text("copy.guestClaimModel.bd6b05a681", spanish: spanish), identifier: accessibility.prefix + ".filters.done") { showingFilters = false }
                        }
                }.presentationDetents([.medium, .large]).presentationDragIndicator(.visible)
            }
    }

    private var searchField: some View {
        HStack(spacing: 10) {
            Image(systemName: "magnifyingglass").foregroundStyle(.secondary).accessibilityHidden(true)
            TextField(CuadraoCopy.text("copy.cuadraoNavigationBar.78ab8df08d", spanish: spanish), text: $query)
                .focused(focused).autocorrectionDisabled().textInputAutocapitalization(.never)
                .submitLabel(.search).onSubmit { recents.remember(query, key: recentsKey); focused.wrappedValue = false }
                .accessibilityIdentifier(accessibility.prefix + ".query")
            if !query.isEmpty {
                Button { recents.remember(query, key: recentsKey); query = "" } label: { Image(systemName: "xmark.circle.fill").frame(width: 44, height: 44) }
                    .foregroundStyle(.secondary).accessibilityLabel(CuadraoCopy.text("copy.cuadraoSearchPresentation.beb46c13ec", spanish: spanish))
                    .accessibilityIdentifier(accessibility.clearQuery)
            }
            if showsFilters {
                Button { focused.wrappedValue = false; showingFilters = true } label: {
                    HStack(spacing: 4) {
                        Image(systemName: "slider.horizontal.3")
                        if filterCount > 0 { Text(String(filterCount)).font(.caption) }
                    }.frame(minWidth: 44, minHeight: 48)
                }.accessibilityIdentifier(accessibility.prefix + ".filters")
                    .accessibilityLabel(CuadraoCopy.text("copy.cuadraoSearchPresentation.b0b89d58eb", spanish: spanish, String(describing: filterCount)))
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
            title: title ?? (browsing ? emptyTitle : (CuadraoCopy.text("copy.cuadraoSearchPresentation.2448aace19", spanish: spanish))),
            detail: detail ?? (browsing ? emptyDetail : (CuadraoCopy.text("copy.cuadraoSearchPresentation.3a1ec2c8d8", spanish: spanish))),
            actionTitle: action?.title, action: action?.run, identifier: accessibility.prefix + ".empty",
            actionIdentifier: action?.identifier)
    }

    /// One action, the most useful first: undo the filters that hide results, then clear the words, then widen the kind.
    private var action: (title: String, run: () -> Void, identifier: String)? {
        if filterCount > 0 {
            return (CuadraoCopy.text("copy.cuadraoSearchCanvas.18b5a4bccd", spanish: spanish), { clearFilters(); kind = .all }, accessibility.prefix + ".reset")
        }
        if !query.isEmpty { return (CuadraoCopy.text("copy.cuadraoSearchPresentation.beb46c13ec", spanish: spanish), { query = "" }, accessibility.clearEmptyQuery) }
        if kind != .all { return (CuadraoCopy.text("copy.cuadraoSearchPresentation.0682933fff", spanish: spanish), { kind = .all }, accessibility.prefix + ".everything") }
        return nil
    }

    private var emptyTitle: String {
        switch kind {
        case .all: CuadraoCopy.text("copy.cuadraoSearchPresentation.b4598cad75", spanish: spanish)
        case .accounts: CuadraoCopy.text("copy.cuadraoSearchPresentation.64573a908e", spanish: spanish)
        case .activity: CuadraoCopy.text("copy.cuadraoSearchPresentation.00e75bc450", spanish: spanish)
        case .plans: CuadraoCopy.text("copy.cuadraoSearchPresentation.f164d22475", spanish: spanish)
        case .chats: CuadraoCopy.text("copy.cuadraoSearchPresentation.455c019e92", spanish: spanish)
        case .files: CuadraoCopy.text("copy.cuadraoSearchPresentation.5a272703b6", spanish: spanish)
        case .memory: CuadraoCopy.text("copy.cuadraoSearchPresentation.cc77f67a4f", spanish: spanish)
        }
    }
    private var emptyDetail: String {
        switch kind {
        case .all:
            if CuadraoFirstRelease.hasAssistant {
                CuadraoCopy.text("copy.cuadraoSearchPresentation.075db4251c", spanish: spanish)
            } else {
                CuadraoCopy.text("copy.cuadraoSearchPresentation.c65b73f579", spanish: spanish)
            }
        case .accounts:
            if CuadraoFirstRelease.hasAssistant {
                CuadraoCopy.text("copy.cuadraoSearchPresentation.7a664219f1", spanish: spanish)
            } else {
                CuadraoCopy.text("copy.cuadraoSearchPresentation.91789e4b19", spanish: spanish)
            }
        case .activity: CuadraoCopy.text("copy.cuadraoSearchPresentation.5ec06a7c61", spanish: spanish)
        case .plans:
            if CuadraoFirstRelease.hasAssistant {
                CuadraoCopy.text("copy.cuadraoSearchPresentation.9811151c26", spanish: spanish)
            } else {
                CuadraoCopy.text("copy.cuadraoSearchPresentation.ac2d8b1306", spanish: spanish)
            }
        case .chats: CuadraoCopy.text("copy.cuadraoSearchPresentation.26de9009be", spanish: spanish)
        case .files: CuadraoCopy.text("copy.cuadraoSearchPresentation.e24f65cdc6", spanish: spanish)
        case .memory: CuadraoCopy.text("copy.cuadraoSearchPresentation.9d9301f776", spanish: spanish)
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
