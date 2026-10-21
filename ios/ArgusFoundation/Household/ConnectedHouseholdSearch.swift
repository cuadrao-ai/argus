import SwiftUI
import ArgusSession

struct ConnectedHouseholdSearch: View {
    @ObservedObject var model: HouseholdModel
    @ObservedObject private var plan: HouseholdPlanModel
    @Environment(\.locale) private var locale
    @FocusState private var focused: Bool
    private var spanish: Bool { CuadraoCopy.isSpanish() }

    init(model: HouseholdModel) { self.model = model; plan = model.plan }

    var body: some View {
        ScrollViewReader { proxy in
            CuadraoSearchContent(query: $model.searchQuery, kind: .constant(.all), kinds: [.all],
                spanish: spanish, filterCount: 0, filterSummary: "", clearFilters: {}, focused: $focused,
                accessibility: .household, showsFilters: false, loading: model.searchState == .loading) {
                Text(model.household?.name ?? NSLocalizedString("household.title", comment: ""))
                    .font(CuadraoTypography.supporting).foregroundStyle(.secondary).padding(.vertical, 18)
                if model.searchState == .empty {
                    CuadraoSearchEmptyState(query: $model.searchQuery, kind: .constant(.all), spanish: spanish,
                        filterCount: 0, clearFilters: {},
                        title: NSLocalizedString("household.searchEmpty", comment: ""),
                        detail: NSLocalizedString("household.scopeNotice", comment: ""), accessibility: .household)
                }
                if model.searchState == .unavailable {
                    Text("household.loadError").foregroundStyle(.secondary)
                    Button("accounts.retry") { Task { await model.find(model.searchQuery) } }.frame(minHeight: 44)
                }
                ForEach(model.search) { item in
                    Button {
                        focused = false
                        Task { await model.openSearchHit(item) }
                    } label: {
                        CuadraoSearchResultRow(title: item.title, detail: title(item), spanish: spanish,
                            symbol: symbol(item))
                    }.buttonStyle(.plain).accessibilityIdentifier("household.search." + item.id.uuidString).id(item.id)
                    Divider().foregroundStyle(WelcomePalette.separator)
                }
                if model.nextCursor != nil {
                    Button("household.more") { Task { await model.find(model.searchQuery, more: true) } }
                        .frame(minHeight: 44).disabled(model.searchState == .loading)
                }
            } filters: { EmptyView() }
            .safeAreaPadding(.bottom, 80)
            .task(id: model.searchQuery) {
                do { try await Task.sleep(for: .milliseconds(250)) } catch { return }
                guard !Task.isCancelled else { return }
                await model.find(model.searchQuery)
            }
            .onChange(of: model.detail?.account.id) { _, id in
                if id == nil, let anchor = model.searchReturnAnchor { proxy.scrollTo(anchor, anchor: .top) }
            }
            .onChange(of: plan.openedRef) { _, ref in
                if ref == nil, let anchor = model.searchReturnAnchor { proxy.scrollTo(anchor, anchor: .top) }
            }
        }
    }

    private func title(_ item: HouseholdSearchHit) -> String {
        switch item.kind {
        case .account: CuadraoCopy.text("copy.connectedHouseholdSearch.f78ffef1d1", spanish: spanish)
        case .activity: NSLocalizedString("household.activity", comment: "")
        case .plan: NSLocalizedString("sharedPlan.title", comment: "")
        }
    }

    private func symbol(_ item: HouseholdSearchHit) -> String {
        switch item.kind {
        case .account: "square.stack"
        case .activity: "arrow.left.arrow.right"
        case .plan: "calendar"
        }
    }
}
