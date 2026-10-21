import SwiftUI

struct ReleaseUpdatesInbox: View {
    let state: ReleaseUpdatesState
    let spanish: Bool
    var permission: ReleasePushPermission = .unavailable
    var retry: () -> Void = {}
    var loadMore: () -> Void = {}
    var markRead: (String) -> Void = { _ in }
    var openSource: (ReleaseUpdateDestination) -> Void = { _ in }
    var requestPermission: () -> Void = {}
    var openSettings: () -> Void = {}

    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 24) {
                switch state {
                case .unavailable:
                    status(CuadraoCopy.text("copy.releaseUpdatesInbox.8af4e5288e", spanish: spanish),
                           detail: CuadraoCopy.text("copy.releaseUpdatesInbox.02b8b196b2", spanish: spanish))
                case .loading:
                    ProgressView(CuadraoCopy.text("copy.releaseUpdatesInbox.8f5392e9e0", spanish: spanish))
                        .frame(maxWidth: .infinity, minHeight: 160).accessibilityIdentifier("updates-loading")
                case .empty:
                    status(CuadraoCopy.text("copy.releaseUpdatesInbox.a03f03cc13", spanish: spanish),
                           detail: CuadraoCopy.text("copy.releaseUpdatesInbox.91cd103ec7", spanish: spanish))
                case .failure:
                    status(CuadraoCopy.text("copy.releaseUpdatesInbox.090b9bc016", spanish: spanish),
                           detail: CuadraoCopy.text("copy.releaseUpdatesInbox.a86774f422", spanish: spanish))
                    Button(CuadraoCopy.text("copy.releaseUpdatesInbox.8b1bd3a0b7", spanish: spanish), action: retry).frame(minHeight: 44)
                        .accessibilityIdentifier("updates-retry")
                case .loaded(let items, let more):
                    ForEach(items) { item in
                        NavigationLink {
                            detail(item)
                                .onAppear { if !item.isRead { markRead(item.id) } }
                        } label: { row(item) }
                        .buttonStyle(.plain).accessibilityIdentifier("updates-row-" + item.id)
                    }
                    switch more {
                    case .none: EmptyView()
                    case .loading: ProgressView(CuadraoCopy.text("copy.releaseUpdatesInbox.d52216127b", spanish: spanish))
                    case .available, .failure:
                        if more == .failure {
                            Text(CuadraoCopy.text("copy.releaseUpdatesInbox.78aaf61bcf", spanish: spanish))
                                .font(CuadraoTypography.supporting).foregroundStyle(.secondary)
                        }
                        Button(CuadraoCopy.text("copy.connectedCuadraoHome.b326f2fa6b", spanish: spanish), action: loadMore).frame(minHeight: 44)
                            .accessibilityIdentifier("updates-load-more")
                    }
                }
                if permission != .unavailable {
                    NavigationLink {
                        ReleaseNotificationPreferences(permission: permission, spanish: spanish,
                            requestPermission: requestPermission, openSettings: openSettings)
                    } label: {
                        Label(CuadraoCopy.text("copy.releaseNotificationPreferences.e66eecd5cf", spanish: spanish), systemImage: "bell")
                            .font(CuadraoTypography.supporting).frame(minHeight: 44)
                    }.accessibilityIdentifier("updates-notification-preferences")
                }
            }.padding(24)
        }.background(WelcomePalette.background).foregroundStyle(WelcomePalette.ink)
            .navigationTitle(CuadraoCopy.text("copy.cuadraoHomePresentation.41483aed95", spanish: spanish)).navigationBarTitleDisplayMode(.inline)
            .accessibilityIdentifier("release-updates-inbox")
    }

    private func status(_ title: String, detail: String) -> some View {
        VStack(alignment: .leading, spacing: 16) {
            CuadraoMark()
            Text(title).font(CuadraoTypography.section)
            Text(detail).font(CuadraoTypography.body).foregroundStyle(.secondary)
        }.frame(maxWidth: .infinity, alignment: .leading).padding(.vertical, 24)
    }

    private func sourceSafeDetail(_ item: ReleaseUpdateItem) -> String {
        switch item.source {
        case .available: item.kind.detail(spanish: spanish)
        case .unavailable:
            switch item.kind {
            case .ownerHistoryRemoved, .householdClosed: item.kind.detail(spanish: spanish)
            default: CuadraoCopy.text("copy.releaseUpdatesInbox.8c48f576c2", spanish: spanish)
            }
        }
    }

    private func row(_ item: ReleaseUpdateItem) -> some View {
        HStack(alignment: .top, spacing: 14) {
            Image(systemName: item.kind.symbol).font(.title3).foregroundStyle(WelcomePalette.pine)
                .frame(width: 42, height: 42).background(WelcomePalette.sage, in: RoundedRectangle(cornerRadius: 13))
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 7) {
                Text(item.kind.title(spanish: spanish)).font(.body.weight(item.isRead ? .regular : .semibold))
                Text(sourceSafeDetail(item)).font(CuadraoTypography.supporting).foregroundStyle(.secondary).lineLimit(3)
                Text(item.occurredAt.formatted(.dateTime.month(.abbreviated).day().year()
                    .locale(Locale(identifier: CuadraoCopy.text("copy.receiptJourneySheet.57139f7c9f", spanish: spanish)))))
                    .font(CuadraoTypography.caption).foregroundStyle(.secondary)
            }
            Spacer(minLength: 0)
            Circle().fill(item.isRead ? Color.clear : WelcomePalette.pine).frame(width: 7, height: 7).padding(.top, 7)
                .accessibilityHidden(true)
        }.padding(.vertical, 8).frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
            .contentShape(Rectangle())
            .accessibilityElement(children: .combine)
            .accessibilityValue(item.isRead ? (CuadraoCopy.text("copy.cuadraoUpdatesCanvas.381ac9313c", spanish: spanish)) : (CuadraoCopy.text("copy.cuadraoUpdatesCanvas.d5af1fde0e", spanish: spanish)))
    }

    private func detail(_ item: ReleaseUpdateItem) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                Text(item.kind.title(spanish: spanish)).font(CuadraoTypography.feature)
                Text(sourceSafeDetail(item)).font(CuadraoTypography.body)
                switch item.source {
                case .available(let destination):
                    Button(CuadraoCopy.text("copy.releaseUpdatesInbox.7230a9adb3", spanish: spanish)) { openSource(destination) }
                        .font(CuadraoTypography.action).frame(minHeight: 44).accessibilityIdentifier("update-open-source")
                case .unavailable:
                    Text(CuadraoCopy.text("copy.releaseUpdatesInbox.8c48f576c2", spanish: spanish))
                        .foregroundStyle(.secondary).accessibilityIdentifier("update-source-unavailable")
                }
            }.frame(maxWidth: .infinity, alignment: .leading).padding(24)
        }.background(WelcomePalette.background).navigationTitle(CuadraoCopy.text("copy.releaseUpdatesInbox.9ee06f13d3", spanish: spanish))
            .navigationBarTitleDisplayMode(.inline)
    }
}
