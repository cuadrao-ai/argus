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
                    Picker(CuadraoCopy.text("copy.cuadraoUpdatesLayout.37ca23660d", spanish: spanish), selection: $unreadOnly) {
                        Text(CuadraoCopy.text("copy.cuadraoSearchCanvas.22417a3c9d", spanish: spanish)).tag(false)
                        Text(CuadraoCopy.text("copy.cuadraoUpdatesCanvas.d5af1fde0e", spanish: spanish)).tag(true)
                    }.pickerStyle(.segmented).accessibilityIdentifier("cuadrao.updates.filter")
                    CuadraoLastUpdated(date: refreshedAt, spanish: spanish)
                    if hasUnread {
                        Button(CuadraoCopy.text("copy.cuadraoUpdatesLayout.0b713d6ded", spanish: spanish), action: markAllRead)
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
        .navigationTitle(CuadraoCopy.text("copy.cuadraoHomePresentation.41483aed95", spanish: spanish)).navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarLeading) { preferences() }
            CuadraoDoneToolbar(title: CuadraoCopy.text("copy.guestClaimModel.bd6b05a681", spanish: spanish), identifier: "cuadrao.updates.done") { dismiss() }
        }
    }

    private func empty(_ state: CuadraoUpdatesEmptyState) -> some View {
        VStack(spacing: 16) {
            PlanLandscape(look: .bloom).frame(width: 130, height: 90).accessibilityHidden(true)
            Text(state == .read ? (CuadraoCopy.text("copy.cuadraoUpdatesLayout.6410f3340c", spanish: spanish))
                 : (CuadraoCopy.text("copy.cuadraoUpdatesLayout.8ac94c797f", spanish: spanish)))
                .font(CuadraoTypography.section)
            Text(detail(state)).font(.subheadline).foregroundStyle(.secondary).multilineTextAlignment(.center)
            if state == .read {
                Button(CuadraoCopy.text("copy.cuadraoUpdatesLayout.d46bea0977", spanish: spanish)) { unreadOnly = false }
                    .accessibilityIdentifier("cuadrao.updates.show-all")
            }
        }.frame(maxWidth: .infinity).padding(.vertical, 36).accessibilityIdentifier("cuadrao.updates.empty")
    }

    private func detail(_ state: CuadraoUpdatesEmptyState) -> String {
        switch state {
        case .empty:
            CuadraoCopy.text("copy.cuadraoUpdatesLayout.f3c62228e8", spanish: spanish)
        case .read:
            CuadraoCopy.text("copy.cuadraoUpdatesLayout.ceb0e3c1ef", spanish: spanish)
        case .unavailable:
            CuadraoCopy.text("copy.cuadraoUpdatesLayout.89aa1d8592", spanish: spanish)
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
                    .accessibilityLabel(CuadraoCopy.text("copy.cuadraoUpdatesCanvas.b0db1198af", spanish: spanish))
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
