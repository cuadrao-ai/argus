import SwiftUI
import ArgusSession

struct AssetPositionView: View {
    let account: FinancialAccount
    @Environment(\.locale) private var locale
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("assets.whole").font(ArgusStyle.body(12, relativeTo: .caption)).foregroundStyle(ArgusStyle.secondary)
            if let estimate = account.asset?.currentEstimate {
                Text(verbatim: money(estimate.amount)).font(ArgusStyle.display(30)).monospacedDigit().accessibilityIdentifier("assets.whole.value")
                Text(verbatim: AccountPresentation.date(estimate.asOf, zone: estimate.timeZone, locale: locale)).accessibilityIdentifier("assets.date.value")
                Text(verbatim: estimate.timeZone).font(ArgusStyle.body(12, relativeTo: .caption))
                Text("assets.basis").font(ArgusStyle.body(12, relativeTo: .caption))
                if let basis = estimate.estimateBasis { Text(verbatim: basis).accessibilityIdentifier("assets.basis.value") }
                else { Text("assets.basis.unspecified") }
            } else { Text("accounts.unknown").accessibilityIdentifier("assets.unknown") }
            Text("assets.personal \(AssetShareControl.percent(account.ownershipShareBps))")
            if let value = account.asset?.personalPositionMinor {
                Text(verbatim: money(AccountPresentation.decimal(value, digits: account.currencyFractionDigits)))
                    .monospacedDigit().accessibilityIdentifier("assets.personal.value")
            } else { Text("accounts.unknown") }
            Text("assets.noncash").font(ArgusStyle.body(12, relativeTo: .caption)).foregroundStyle(ArgusStyle.secondary)
        }.fixedSize(horizontal: false, vertical: true)
    }
    private func money(_ amount: String) -> String { account.currency + " " + AccountPresentation.amount(amount, locale: locale) }
}

struct AssetDetailView: View {
    let account: FinancialAccount
    @ObservedObject var model: AccountsModel
    @ObservedObject var loop: FinancialLoopModel
    @State private var debt: FinancialAccount?
    @State private var debtError = false
    @Environment(\.locale) private var locale
    var body: some View {
        VStack(alignment: .leading, spacing: 22) {
            if let nickname = account.nickname { Text(verbatim: nickname).font(ArgusStyle.display()) }
            Text(LocalizedStringKey("accounts.type." + account.type)).foregroundStyle(ArgusStyle.secondary)
            AssetPositionView(account: account)
            if account.archived { Text("accounts.archived") }
            Button("assets.update") { loop.asset(account) }.buttonStyle(PillButtonStyle())
                .disabled(loop.pendingConfirmation != nil).accessibilityIdentifier("assets.update")
            Button("assets.details") { loop.asset(account, details: true) }.frame(minHeight: 44)
                .disabled(loop.pendingConfirmation != nil).accessibilityIdentifier("assets.details")
            if let linkedID = account.asset?.relatedDebtAccountId {
                Button {
                    Task {
                        await model.refresh(linkedID)
                        if model.errorKey == nil { debt = model.accounts.first { $0.id == linkedID }; debtError = debt == nil }
                        else { debtError = true }
                    }
                } label: {
                    HStack { Text("assets.debt"); Spacer(); Text(loop.accountName(linkedID)); Image(systemName: "chevron.right") }
                }.frame(minHeight: 48).accessibilityIdentifier("assets.debt.open")
                if debtError { Text("search.destination.unavailable") }
            }
            if let estimates = account.asset?.estimates, !estimates.isEmpty {
                DisclosureGroup {
                    ForEach(estimates.reversed()) { estimate in
                        VStack(alignment: .leading, spacing: 10) {
                            Text(verbatim: account.currency + " " + AccountPresentation.amount(estimate.amount, locale: locale)).monospacedDigit()
                            Text(verbatim: AccountPresentation.date(estimate.asOf, zone: estimate.timeZone, locale: locale))
                            if let basis = estimate.estimateBasis { Text(verbatim: basis) }
                            Button("assets.correct") { loop.asset(account, correcting: estimate) }
                                .frame(minHeight: 44).disabled(loop.pendingConfirmation != nil).accessibilityIdentifier("assets.correct." + estimate.id.uuidString)
                            if estimate.revisions.count > 1 {
                                ForEach(estimate.revisions, id: \.revision) { revision in
                                    VStack(alignment: .leading, spacing: 6) {
                                        Text("assets.revision \(revision.revision)")
                                        Text(verbatim: account.currency + " " + AccountPresentation.amount(revision.amount, locale: locale))
                                        Text(verbatim: AccountPresentation.date(revision.asOf, zone: revision.timeZone, locale: locale))
                                        if let basis = revision.estimateBasis { Text(verbatim: basis) }
                                        if let reason = revision.reason { Text(verbatim: reason) }
                                    }.font(ArgusStyle.body(12, relativeTo: .caption))
                                }
                            }
                        }.padding(.vertical, 12)
                    }
                } label: {
                    Text("assets.history").accessibilityIdentifier("assets.history")
                }
            }
            if let changes = account.asset?.changes, !changes.isEmpty {
                DisclosureGroup("assets.details.history") {
                    ForEach(changes, id: \.version) { change in
                        VStack(alignment: .leading, spacing: 6) {
                            Text(verbatim: AccountPresentation.date(change.recordedAt, zone: TimeZone.current.identifier, locale: locale))
                            Text("assets.share.changed \(AssetShareControl.percent(change.previousShareBps)) \(AssetShareControl.percent(change.ownershipShareBps))")
                            if change.previousDebtAccountId != change.relatedDebtAccountId {
                                if let old = change.previousDebtAccountId { Text("assets.debt.removed \(loop.accountName(old))") }
                                if let new = change.relatedDebtAccountId { Text("assets.debt.added \(loop.accountName(new))") }
                            }
                        }.font(ArgusStyle.body(12, relativeTo: .caption)).padding(.vertical, 8)
                    }
                }
            }
        }
        .sheet(item: $debt) { opened in
            NavigationStack {
                ScrollView {
                    VStack(alignment: .leading, spacing: 22) {
                        AccountDetailView(account: model.accounts.first { $0.id == opened.id } ?? opened, model: model, loop: loop)
                    }.padding(24)
                }.background(ArgusStyle.background)
                    .toolbar { CuadraoCancelToolbar(title: "assets.back", identifier: "assets.debt.back") { debt = nil }}
            }
        }
    }
}
