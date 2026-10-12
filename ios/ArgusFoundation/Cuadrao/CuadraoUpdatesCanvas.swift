import SwiftUI

enum CanvasUpdate: Hashable, Identifiable {
    case accountReview(UUID), planProgress(UUID)
    var id: Self { self }
    var identifier: String {
        switch self {
        case .accountReview(let id): "account-\(id)"
        case .planProgress(let id): "plan-\(id)"
        }
    }
    static func available(accounts: CuadraoAccountsPreview, plans: CuadraoPlanPreview) -> [Self] {
        let review = accounts.active.sorted { $0.balance == nil && $1.balance != nil }.prefix(1)
            .map { Self.accountReview($0.id) }
        let progress = plans.plans.filter {
            !$0.archived && $0.recorded > 0 && $0.spaceID == accounts.selectedSpaceID
        }.map { Self.planProgress($0.id) }
        return review + progress
    }
}

struct CuadraoUpdatesCanvas: View {
    let accounts: CuadraoAccountsPreview
    let plans: CuadraoPlanPreview
    let spanish: Bool
    @Binding var readIDs: Set<CanvasUpdate>
    @Binding var profile: CanvasProfileDraft
    @Environment(\.dismiss) private var dismiss
    @State private var unreadOnly = false
    @State private var path: [CanvasUpdate] = []
    @State private var accountSheet: CanvasAccountSheet?
    @State private var refreshedAt: Date?
    private var items: [CanvasUpdate] { CanvasUpdate.available(accounts: accounts, plans: plans) }
    private var visible: [CanvasUpdate] { items.filter { !unreadOnly || !readIDs.contains($0) } }
    private var unread: [CanvasUpdate] { items.filter { !readIDs.contains($0) } }

    var body: some View {
        NavigationStack(path: $path) {
            CuadraoUpdatesLayout(spanish: spanish, unreadOnly: $unreadOnly,
                hasUnread: !unread.isEmpty,
                emptyState: visible.isEmpty ? (items.isEmpty ? .empty : .read) : nil,
                markAllRead: { readIDs.formUnion(visible) },
                refresh: { try? await Task.sleep(for: .milliseconds(400)); refreshedAt = Date() }, refreshedAt: refreshedAt) {
                updateSection(spanish ? "Por revisar" : "To review", entries: visible.filter {
                    if case .accountReview = $0 { return true }; return false
                })
                updateSection(spanish ? "Tus planes" : "Your plans", entries: visible.filter {
                    if case .planProgress = $0 { return true }; return false
                })
            } preferences: {
                NavigationLink {
                    CuadraoProfilePage(route: .notifications, profile: $profile, spanish: spanish, includeExamples: false)
                } label: { CuadraoUpdatesPreferencesLabel() }
                    .accessibilityLabel(spanish ? "Preferencias de notificaciones" : "Notification preferences")
                    .accessibilityIdentifier("cuadrao.updates.preferences")
            }
            .navigationDestination(for: CanvasUpdate.self) { item in
                switch item {
                case .accountReview(let id):
                    if accounts.active.contains(where: { $0.id == id }) {
                        CuadraoAccountCanvas(data: accounts, accountID: id, spanish: spanish,
                            actions: { accountSheet = $0 }, record: { accountSheet = .record($0) })
                    } else { unavailable }
                case .planProgress(let id):
                    if let plan = plans.plan(id), !plan.archived, plan.spaceID == accounts.selectedSpaceID {
                        CuadraoPlanDetail(store: plans, accounts: accounts, planID: id, spanish: spanish, bottomSpace: 24)
                    } else { unavailable }
                }
            }
            .sheet(item: $accountSheet) { selection in
                CuadraoAccountModal(data: accounts, selection: selection, spanish: spanish,
                    show: { accountSheet = $0 }, archived: { _ in accountSheet = nil; path = [] })
            }
        }.tint(WelcomePalette.pine)
    }

    @ViewBuilder private func updateSection(_ title: String, entries: [CanvasUpdate]) -> some View {
        if !entries.isEmpty {
            Section {
                ForEach(entries) { item in
                    Button {
                        guard items.contains(item) else { return }
                        readIDs.insert(item); path.append(item)
                    } label: { row(item) }
                    .buttonStyle(.plain).listRowBackground(Color.clear)
                    .accessibilityIdentifier("cuadrao.updates.item.\(item.identifier)")
                    .accessibilityValue(readIDs.contains(item) ? (spanish ? "Leída" : "Read") : (spanish ? "Sin leer" : "Unread"))
                    .swipeActions(edge: .trailing) { readAction(item) }
                    .contextMenu { readAction(item) }
                    .accessibilityAction(named: Text(readTitle(item))) { toggleRead(item) }
                }
            } header: {
                Text(title).font(CuadraoTypography.section).foregroundStyle(WelcomePalette.ink).textCase(nil)
                    .padding(.top, 8).padding(.bottom, 4)
            }
        }
    }
    private func row(_ item: CanvasUpdate) -> some View {
        HStack(alignment: .top, spacing: 14) {
            switch item {
            case .accountReview(let id):
                if let account = accounts.account(id) {
                    CanvasAccountIcon(kind: account.kind)
                    VStack(alignment: .leading, spacing: 6) {
                        Text(account.displayName(spanish)).font(CuadraoTypography.action)
                        Text(account.balance == nil
                             ? (spanish ? "Esta cuenta aún no tiene balance. Puedes revisarla." : "This account has no balance yet. You can review it.")
                             : (spanish ? "Revisa el balance y los movimientos registrados." : "Review its recorded balance and activity."))
                            .font(.subheadline).foregroundStyle(.secondary)
                    }
                }
            case .planProgress(let id):
                if let plan = plans.plan(id) {
                    Image(systemName: plan.look.symbol).font(.title3).foregroundStyle(plan.look.color)
                        .frame(width: 42, height: 42).accessibilityHidden(true)
                    VStack(alignment: .leading, spacing: 6) {
                        Text(plan.name).font(CuadraoTypography.action)
                        Text(plan.kind.recordedTitle(spanish) + " · " + PlanFormat.amount(plan.recorded, currency: plan.currency))
                            .font(.subheadline).foregroundStyle(.secondary)
                    }
                }
            }
            Spacer(minLength: 0)
            Circle().fill(readIDs.contains(item) ? .clear : WelcomePalette.pine).frame(width: 7, height: 7)
                .padding(.top, 8).accessibilityHidden(true)
        }.fixedSize(horizontal: false, vertical: true).padding(.vertical, 10).contentShape(Rectangle())
    }
    private var unavailable: some View {
        ContentUnavailableView(spanish ? "Ya no está disponible" : "No longer available", systemImage: "tray")
            .toolbar(.visible, for: .navigationBar)
    }
    private func readTitle(_ item: CanvasUpdate) -> String {
        readIDs.contains(item) ? (spanish ? "Marcar como no leída" : "Mark unread") : (spanish ? "Marcar como leída" : "Mark read")
    }
    private func readAction(_ item: CanvasUpdate) -> some View {
        Button(readTitle(item), systemImage: readIDs.contains(item) ? "envelope.badge" : "envelope.open") { toggleRead(item) }
            .tint(WelcomePalette.pine)
    }
    private func toggleRead(_ item: CanvasUpdate) {
        if readIDs.contains(item) { readIDs.remove(item) } else { readIDs.insert(item) }
    }
}
