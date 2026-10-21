import SwiftUI

struct CuadraoPlanCanvas: View {
    let store: CuadraoPlanPreview
    let accounts: CuadraoAccountsPreview
    let spanish: Bool
    var bottomSpace: CGFloat = 90
    @State private var path: [UUID] = []
    @State private var together = false
    let groups: CuadraoGroupPreview
    @State private var newGroup = false
    @State private var scope = "personal"
    @State private var selectedDay: Int?
    @State private var creation: PlanEditorRoute?
    @State private var resetConfirmation = false
    @State private var showEmpty = false

    private var forecast: CanvasForecast { CanvasForecast(household: scope == "household") }
    private var active: [CanvasPlan] { store.plans.filter { !$0.archived } }
    private var selectedPoint: CanvasForecastPoint? {
        guard let selectedDay else { return nil }
        return (forecast.actual + forecast.projection(daily: store.daily(for: scope)).dropFirst()).first { $0.day == selectedDay }
    }
    private var scopeName: String { PlanFormat.space(scope, accounts: accounts, spanish: spanish) }

    var body: some View {
        NavigationStack(path: $path) {
            CuadraoPlanPage(spanish: spanish, audience: $together, bottomSpace: bottomSpace) {
                header
            } content: {
                if together {
                    CuadraoGroupCollection(store: groups, spanish: spanish, bottomSpace: bottomSpace, create: { newGroup = true }, open: { path.append($0) })
                } else {
                    if store.hasForecast { forecastOverview } else { forecastColdStart }
                    plans
                }
            } footer: {
                PlanPreviewFootnote(spanish: spanish)
            }
            .toolbar(.hidden, for: .navigationBar).toolbar(.hidden, for: .tabBar)
            .navigationDestination(for: UUID.self) { id in
                if store.plan(id) != nil {
                    CuadraoPlanDetail(store: store, accounts: accounts, planID: id, spanish: spanish, bottomSpace: bottomSpace)
                } else {
                    CuadraoGroupDetail(store: groups, groupID: id, spanish: spanish, bottomSpace: bottomSpace)
                }
            }
            .sheet(item: $creation) { route in
                CuadraoPlanEditor(store: store, accounts: accounts, initial: route.plan, spanish: spanish) { id in
                    if store.plan(route.plan.id) != nil { path.append(id) }
                }
            }
            .sheet(isPresented: $newGroup) {
                CuadraoGroupEditor(store: groups, spanish: spanish, onSave: { path.append($0) })
            }
            .confirmationDialog(CuadraoCopy.text("copy.cuadraoPlanCanvas.36f15a9240", spanish: spanish), isPresented: $resetConfirmation, titleVisibility: .visible) {
                Button(CuadraoCopy.text("copy.cuadraoPlanCanvas.68284a152b", spanish: spanish), role: .destructive) {
                    store.resetExamples(spanish: spanish, empty: showEmpty); groups.resetExamples(spanish: spanish, empty: showEmpty)
                }
            } message: {
                Text(CuadraoCopy.text("copy.cuadraoPlanCanvas.8f62c0a225", spanish: spanish))
            }
        }.tint(WelcomePalette.pine)
    }

    private var header: some View {
        CuadraoPlanHeader(spanish: spanish,
            createTitle: together ? (CuadraoCopy.text("copy.cuadraoGroupEditor.a54bd5bc95", spanish: spanish)) : (CuadraoCopy.text("copy.cuadraoPlanCanvas.2131013203", spanish: spanish)),
            titleMenu: { AnyView(Group {
                Button(CuadraoCopy.text("copy.cuadraoPlanCanvas.6e527eb751", spanish: spanish)) { showEmpty = true; resetConfirmation = true }
                Button(CuadraoCopy.text("copy.cuadraoPlanCanvas.180afb9919", spanish: spanish)) { showEmpty = false; resetConfirmation = true }
            }) }) {
                if together { newGroup = true } else { creation = PlanEditorRoute(plan: newPlan) }
            }
    }

    private var forecastSpaces: [CanvasSpace] { accounts.visibleSpaces.filter { $0.kind == .personal || $0.kind == .household } }

    private var newPlan: CanvasPlan {
        CanvasPlan(name: "", spaceID: CanvasSpace.personalID)
    }

    private var forecastOverview: some View {
        CuadraoPlanForecastSection(period: CuadraoCopy.text("copy.cuadraoPlanCanvas.b011911464", spanish: spanish)) {
            if forecastSpaces.count > 1 {
                CuadraoChoiceMenu(title: CuadraoCopy.text("copy.cuadraoPlanCanvas.7431f80dd8", spanish: spanish),
                    selection: Binding(get: { scope }, set: { scope = $0; selectedDay = nil }),
                    values: forecastSpaces.map(\.id),
                    valueTitle: { PlanFormat.space($0, accounts: accounts, spanish: spanish) })
                    .accessibilityLabel(CuadraoCopy.text("copy.cuadraoPlanCanvas.1a736a33ab", spanish: spanish, String(describing: scopeName)))
                    .accessibilityIdentifier("plan-forecast-scope")
            } else { CuadraoChoiceLabel(title: scopeName, selectable: false) }
        } content: {
            CuadraoPlanForecastValue(
                title: selectedPoint.map { "\($0.day) oct. · \($0.day > CanvasForecast.today ? (CuadraoCopy.text("copy.cuadraoPlanCanvas.b05f3ed953", spanish: spanish)) : (CuadraoCopy.text("copy.cuadraoGroupDetail.a6323107e2", spanish: spanish)))" } ?? (store.dailyAssumptions[scope] == nil ? (CuadraoCopy.text("copy.cuadraoPlanCanvas.4531c8dc99", spanish: spanish)) : (CuadraoCopy.text("copy.cuadraoPlanCanvas.33873ef21c", spanish: spanish))),
                amount: PlanFormat.amount(selectedPoint?.balance ?? forecast.ending(daily: store.daily(for: scope))),
                identifier: "plan-month-ending")
            PlanForecastChart(forecast: forecast, daily: store.daily(for: scope), spanish: spanish, selectedDay: $selectedDay, compact: true)
        } explore: {
            CuadraoPlanExploreLink(spanish: spanish) {
                CuadraoForecastPlayground(store: store, scope: scope, scopeName: scopeName, spanish: spanish, bottomSpace: bottomSpace)
            }
        }
    }

    private var forecastColdStart: some View {
        CuadraoPlanColdStart(spanish: spanish,
            detail: CuadraoCopy.text("copy.cuadraoPlanCanvas.fdfec8bc75", spanish: spanish)) {
            Button(CuadraoCopy.text("copy.cuadraoPlanCanvas.3d0390b3b7", spanish: spanish)) {
                store.enableForecastExample()
            }
        }
    }

    private var plans: some View {
        CuadraoPlanCollection(spanish: spanish, isEmpty: active.isEmpty,
            create: { creation = .init(plan: newPlan) }) {
            CuadraoOrderedCollection(items: active, spanish: spanish,
                identifier: { "plan-row-\($0.kind.rawValue)-\($0.spaceID)" },
                open: { path.append($0.id) }, edit: { creation = .init(plan: $0) },
                archive: { store.archive($0.id, true) }, reorder: store.reorder) { plan in
                    PlanCard(plan: plan, space: PlanFormat.space(plan.spaceID, accounts: accounts, spanish: spanish), spanish: spanish)
                }
        } archives: {
            CuadraoPlanArchiveLink(spanish: spanish) {
                CuadraoArchivedPlans(store: store, accounts: accounts, spanish: spanish, bottomSpace: bottomSpace)
            }
        }
    }

}

private struct CuadraoArchivedPlans: View {
    let store: CuadraoPlanPreview
    let accounts: CuadraoAccountsPreview
    let spanish: Bool
    let bottomSpace: CGFloat
    var body: some View {
        List {
            if store.plans.filter(\.archived).isEmpty {
                ContentUnavailableView(CuadraoCopy.text("copy.cuadraoGroupCollection.e07523e83a", spanish: spanish), systemImage: "archivebox",
                    description: Text(CuadraoCopy.text("copy.cuadraoPlanCanvas.ebcdf81c28", spanish: spanish)))
                    .listRowSeparator(.hidden)
            }
            ForEach(store.plans.filter(\.archived)) { plan in
                HStack {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(plan.name)
                        Text(PlanFormat.space(plan.spaceID, accounts: accounts, spanish: spanish)).font(.caption).foregroundStyle(.secondary)
                    }
                    Spacer()
                    Button(CuadraoCopy.text("copy.cuadraoGroupCollection.1ae3bf9797", spanish: spanish)) { store.archive(plan.id, false) }.buttonStyle(.bordered)
                }
            }
        }.navigationTitle(CuadraoCopy.text("copy.cuadraoSpacesSheet.e95aacbabf", spanish: spanish)).navigationBarTitleDisplayMode(.inline)
            .toolbar(.visible, for: .navigationBar).safeAreaPadding(.bottom, bottomSpace)
    }
}

struct PlanEditorRoute: Identifiable {
    let plan: CanvasPlan
    var id: UUID { plan.id }
}
