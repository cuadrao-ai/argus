import SwiftUI

enum CuadraoUpdatesEmptyState {
    case empty, read, unavailable
}

struct CuadraoUpdatesLayout<Rows: View, Preferences: View>: View {
    let spanish: Bool
    @Binding var unreadOnly: Bool
    let hasUnread: Bool
    let emptyState: CuadraoUpdatesEmptyState?
    let markAllRead: () -> Void
    /// Pull to refresh and the line under the controls; both stay off for hosts that do not load anything.
    var refresh: (() async -> Void)?
    var refreshedAt: Date?
    @ViewBuilder let rows: () -> Rows
    @ViewBuilder let preferences: () -> Preferences
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        List {
            if emptyState != .unavailable {
                Section {
                    Picker(spanish ? "Mostrar" : "Show", selection: $unreadOnly) {
                        Text(spanish ? "Todas" : "All").tag(false)
                        Text(spanish ? "Sin leer" : "Unread").tag(true)
                    }.pickerStyle(.segmented).accessibilityIdentifier("cuadrao.updates.filter")
                    CuadraoLastUpdated(date: refreshedAt, spanish: spanish)
                    if hasUnread {
                        Button(spanish ? "Marcar todas como leídas" : "Mark all as read", action: markAllRead)
                            .font(.subheadline).accessibilityIdentifier("cuadrao.updates.read-all")
                    }
                }.listRowBackground(Color.clear).listRowSeparator(.hidden)
            }
            if let emptyState {
                empty(emptyState).listRowBackground(Color.clear).listRowSeparator(.hidden)
            } else {
                rows()
            }
        }
        .listStyle(.plain).scrollContentBackground(.hidden).background(WelcomePalette.background)
        .modifier(CuadraoOptionalRefresh(action: refresh))
        .navigationTitle(spanish ? "Novedades" : "Updates").navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarLeading) { preferences() }
            CuadraoDoneToolbar(title: spanish ? "Listo" : "Done", identifier: "cuadrao.updates.done") { dismiss() }
        }
    }

    private func empty(_ state: CuadraoUpdatesEmptyState) -> some View {
        VStack(spacing: 16) {
            PlanLandscape(look: .bloom).frame(width: 130, height: 90).accessibilityHidden(true)
            Text(state == .read ? (spanish ? "Estás al día" : "You're all caught up")
                 : (spanish ? "Todo tranquilo por aquí" : "It's quiet here"))
                .font(CuadraoTypography.section)
            Text(detail(state)).font(.subheadline).foregroundStyle(.secondary).multilineTextAlignment(.center)
            if state == .read {
                Button(spanish ? "Ver todas" : "View all") { unreadOnly = false }
                    .accessibilityIdentifier("cuadrao.updates.show-all")
            }
        }.frame(maxWidth: .infinity).padding(.vertical, 36).accessibilityIdentifier("cuadrao.updates.empty")
    }

    private func detail(_ state: CuadraoUpdatesEmptyState) -> String {
        switch state {
        case .empty:
            spanish ? "Aquí podrás revisar tus cuentas y el progreso que registres en tus planes."
                : "Review your accounts and recorded plan progress here."
        case .read:
            spanish ? "Puedes volver a ver tus novedades en Todas." : "You can revisit your updates in All."
        case .unavailable:
            spanish ? "Las novedades aún no están conectadas en esta versión. Tus movimientos y planes siguen disponibles."
                : "Updates aren't connected in this version yet. Your transactions and plans are still available."
        }
    }
}

struct CuadraoUpdatesPreferencesLabel: View {
    var body: some View {
        Image(systemName: "slider.horizontal.3").frame(width: 44, height: 44)
    }
}

struct ConnectedCuadraoUpdates: View {
    let spanish: Bool
    let preferences: () -> Void
    @State private var unreadOnly = false

    var body: some View {
        NavigationStack {
            CuadraoUpdatesLayout(spanish: spanish, unreadOnly: $unreadOnly,
                hasUnread: false, emptyState: .unavailable, markAllRead: {}) {
                EmptyView()
            } preferences: {
                Button(action: preferences) { CuadraoUpdatesPreferencesLabel() }
                    .accessibilityLabel(spanish ? "Preferencias de notificaciones" : "Notification preferences")
                    .accessibilityIdentifier("cuadrao.updates.preferences")
            }
        }.tint(WelcomePalette.pine).foregroundStyle(WelcomePalette.ink)
    }
}

private struct CuadraoOptionalRefresh: ViewModifier {
    let action: (() async -> Void)?
    @ViewBuilder func body(content: Content) -> some View {
        if let action { content.refreshable { await action() } } else { content }
    }
}
