import SwiftUI
import ArgusSession

struct ConnectedHouseholdAccounts: View {
    @ObservedObject var model: HouseholdModel
    @Environment(\.locale) private var locale
    private var spanish: Bool { CuadraoCopy.isSpanish() }

    var body: some View {
        if let snapshot = model.snapshot {
            VStack(alignment: .leading, spacing: 12) {
                if !snapshot.accounts.isEmpty {
                    HStack {
                        Text(CuadraoCopy.text("copy.connectedCuadraoHome.8cce5d02a3", spanish: spanish)).font(CuadraoTypography.section)
                            .accessibilityAddTraits(.isHeader)
                        Spacer()
                        CuadraoSectionAddButton(title: NSLocalizedString("household.shareAccounts", comment: "")) {
                            model.showManagement = true
                        }.accessibilityIdentifier("household.shareAccounts")
                    }
                    VStack(spacing: 0) {
                        ForEach(snapshot.accounts.filter { !$0.account.archived }) { account in row(account) }
                    }
                    if snapshot.accounts.contains(where: { $0.account.archived }) {
                        DisclosureGroup(CuadraoCopy.text("copy.connectedHouseholdAccounts.fa75965c7e", spanish: spanish)) {
                            ForEach(snapshot.accounts.filter { $0.account.archived }) { account in row(account) }
                        }.font(CuadraoTypography.supporting)
                    }
                } else {
                    CuadraoChartState(title: CuadraoCopy.text("copy.cuadraoHomeEmptyState.c598130645", spanish: spanish),
                        detail: NSLocalizedString("household.consent", comment: ""))
                        .accessibilityIdentifier("household.empty")
                    RegistrationButton(title: NSLocalizedString("household.addAccount", comment: "")) { model.addAccount?() }
                        .accessibilityIdentifier("household.addAccount")
                    Text("household.addAccountNotice").font(.caption).foregroundStyle(.secondary)
                    Button("household.shareAccounts") { model.showManagement = true }
                        .font(.subheadline.weight(.medium)).frame(maxWidth: .infinity, minHeight: 44)
                        .accessibilityIdentifier("household.shareAccounts")
                }
            }
        }
    }

    private func row(_ item: HouseholdAccount) -> some View {
        Button { Task { await model.open(item.id) } } label: {
            CanvasAccountRowContent(value: .init(
                title: item.account.nickname ?? NSLocalizedString("accounts.type." + item.account.type, comment: ""),
                subtitle: item.ownerName + " · " + NSLocalizedString("household.permission." + item.permission, comment: ""),
                artwork: ConnectedAccountPresentation.artwork(item.account.type),
                amount: item.account.balance.amount.map { AccountPresentation.amount($0, locale: locale) }
                    ?? NSLocalizedString("household.unknown", comment: ""),
                amountCaption: item.account.currency,
                note: item.account.archived ? (CuadraoCopy.text("copy.connectedAccountPresentation.7268bbe2c2", spanish: spanish)) : nil))
                .overlay(alignment: .bottom) { Divider().padding(.leading, 54) }
        }.buttonStyle(.plain).accessibilityIdentifier("household.account." + item.id.uuidString)
    }
}

struct ConnectedHouseholdAccountDetail: View {
    @ObservedObject var model: HouseholdModel
    @Environment(\.locale) private var locale

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    Button("accounts.back") { model.back() }.frame(minHeight: 44)
                        .accessibilityIdentifier("household.back")
                    ConnectedHouseholdNotice(model: model)
                    if let detail = model.detail {
                        header(detail.account)
                        if detail.account.permission == "edit" && !detail.account.account.isOptionalAsset {
                            RegistrationButton(title: NSLocalizedString("household.recordActivity", comment: "")) {
                                model.beginActivity(detail.account)
                            }.accessibilityIdentifier("household.record")
                        }
                        Text("household.activity").font(CuadraoTypography.section)
                        ForEach(detail.activities) { item in
                            VStack(alignment: .leading, spacing: 8) {
                                if model.highlightActivityId == item.id {
                                    Text("household.selectedActivity").font(.caption).foregroundStyle(.secondary)
                                }
                                ConnectedHouseholdActivityRow(item: item)
                                HStack {
                                    Button("household.history") { Task { await model.loadHistory(item.id) } }
                                        .frame(minHeight: 44).accessibilityIdentifier("household.history." + item.id.uuidString)
                                    if item.canEdit {
                                        Button("household.correct") { model.beginActivity(detail.account, correction: item) }
                                            .frame(minHeight: 44).accessibilityIdentifier("household.correct." + item.id.uuidString)
                                    }
                                }.font(CuadraoTypography.supporting)
                            }.id(item.id)
                        }
                        ForEach(Array(model.history.enumerated()), id: \.offset) { _, item in
                            ConnectedHouseholdActivityRow(item: item)
                        }
                    }
                }.padding(24).padding(.bottom, 32).frame(maxWidth: .infinity, alignment: .leading)
            }.background(WelcomePalette.background).toolbar(.hidden, for: .navigationBar)
                .accessibilityIdentifier("household.detail")
                .onAppear { if let id = model.highlightActivityId { proxy.scrollTo(id, anchor: .top) } }
                .onChange(of: model.highlightActivityId) { _, id in if let id { proxy.scrollTo(id, anchor: .top) } }
        }
    }

    private func header(_ item: HouseholdAccount) -> some View {
        let account = item.account
        return VStack(alignment: .leading, spacing: 14) {
            CanvasAccountDetailHeader(value: .init(
                title: account.nickname ?? NSLocalizedString("accounts.type." + account.type, comment: ""),
                artwork: ConnectedAccountPresentation.artwork(account.type), balanceLabel: CuadraoCopy.text("copy.connectedHouseholdAccounts.02e2073456", spanish: CuadraoCopy.isSpanish()),
                currency: account.currency,
                amount: account.balance.amount.map { AccountPresentation.amount($0, locale: locale) }
                    ?? NSLocalizedString("household.unknown", comment: ""),
                freshness: item.ownerName + " · " + NSLocalizedString("household.permission." + item.permission, comment: ""),
                amountIdentifier: "household.detail.balance",
                amountAccessibilityLabel: account.currency + " " + (account.balance.amount.map {
                    AccountPresentation.amount($0, locale: locale)
                } ?? NSLocalizedString("household.unknown", comment: ""))))
            if account.ownershipShareBps != 10000 {
                Text("household.wholeValue").font(.footnote).foregroundStyle(.secondary)
                (Text(Decimal(account.ownershipShareBps) / 100, format: .number) + Text("%"))
                    .font(CuadraoTypography.rowAmount)
            }
        }
    }
}

struct ConnectedHouseholdActivityRow: View {
    let item: HouseholdActivity
    @Environment(\.locale) private var locale

    var body: some View {
        CanvasAccountActivityRowContent(value: .init(
            title: item.activity.note ?? NSLocalizedString("loop.kind." + item.activity.kind.rawValue, comment: ""),
            detail: (item.authorName.isEmpty ? NSLocalizedString("household.formerMember", comment: "") : item.authorName)
                + " · " + AccountPresentation.date(item.activity.occurredAt, zone: item.activity.timeZone, locale: locale),
            amount: item.activity.currency + " " + (item.activity.amount.map { AccountPresentation.amount($0, locale: locale) }
                ?? NSLocalizedString("household.unknown", comment: "")),
            symbol: "arrow.left.arrow.right",
            status: item.privateCounterpart ? NSLocalizedString("household.privateCounterpart", comment: "") : nil))
            .accessibilityIdentifier("household.activity." + item.id.uuidString)
    }
}
