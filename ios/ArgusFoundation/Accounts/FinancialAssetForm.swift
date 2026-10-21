import SwiftUI
import ArgusSession

struct AssetShareControl: View {
    @Binding var share: String
    @State private var choosing = false
    @State private var custom = false
    static func percent(_ bps: Int) -> String { String(bps / 100) + (bps % 100 == 0 ? "" : "." + String(format: "%02d", bps % 100)) }
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                if share == "100" || share == "100.00" { Text("assets.share.allSummary") }
                else { Text("assets.share.summary \(share)") }
                Spacer()
                Button("accounts.type.change") { choosing.toggle() }.frame(minHeight: 44).accessibilityIdentifier("assets.share.change")
            }
            if choosing {
                HStack(spacing: 16) {
                    Button("assets.share.all") { share = "100"; custom = false; choosing = false }.accessibilityIdentifier("assets.share.all")
                    Button("assets.share.half") { share = "50"; custom = false; choosing = false }.accessibilityIdentifier("assets.share.half")
                    Button("assets.share.other") { custom = true }.accessibilityIdentifier("assets.share.other")
                }.frame(minHeight: 44)
                if custom {
                    PercentField(title: NSLocalizedString("accounts.share", comment: ""), text: $share, bounds: .share,
                                 spanish: CuadraoCopy.isSpanish(), identifier: "assets.share.percent")
                }
            }
        }.font(ArgusStyle.body(13, relativeTo: .subheadline))
    }
}

struct FinancialAssetForm: View {
    @ObservedObject var model: FinancialAssetEditor
    @ObservedObject var accounts: AccountsModel
    @Environment(\.locale) private var locale
    @Environment(\.dismiss) private var dismiss
    @FocusState private var focused: String?
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 22) {
                    Text(verbatim: model.account.nickname ?? NSLocalizedString("accounts.type." + model.account.type, comment: ""))
                        .font(ArgusStyle.display(23))
                    if model.details {
                        AssetShareControl(share: $model.share).disabled(model.locked)
                        Text("accounts.share.help").font(ArgusStyle.body(12, relativeTo: .caption))
                        Picker("assets.debt", selection: $model.debtID) {
                            Text("assets.debt.none").tag(nil as UUID?)
                            ForEach(accounts.accounts.filter { $0.nature == "liability" }) { account in
                                Text(verbatim: (account.nickname ?? NSLocalizedString("accounts.type." + account.type, comment: "")) + " · " + account.currency).tag(Optional(account.id))
                            }
                        }.frame(minHeight: 48).disabled(model.locked).accessibilityIdentifier("assets.debt.picker")
                        Text("assets.debt.help").font(ArgusStyle.body(12, relativeTo: .caption)).foregroundStyle(ArgusStyle.secondary)
                    } else {
                        VStack(alignment: .leading, spacing: 16) {
                            field("assets.whole", text: $model.amount, id: "assets.amount").keyboardType(.decimalPad)
                            Text(verbatim: model.account.currency).foregroundStyle(ArgusStyle.secondary)
                            DatePicker("assets.date", selection: $model.date, in: ...Date(), displayedComponents: [.date, .hourAndMinute])
                                .environment(\.timeZone, TimeZone(identifier: model.timeZone) ?? .gmt).accessibilityIdentifier("assets.date")
                            Picker("accounts.zone", selection: $model.timeZone) {
                                ForEach(TimeZone.knownTimeZoneIdentifiers, id: \.self) { Text(verbatim: $0).tag($0) }
                            }.accessibilityIdentifier("assets.zone")
                            field("assets.basis", text: $model.basis, id: "assets.basis")
                            if model.selected != nil { field("accounts.reason", text: $model.reason, id: "assets.reason") }
                        }.disabled(model.locked)
                        if let preview = model.preview {
                            Text("loop.after").font(ArgusStyle.display(22))
                            AssetPositionView(account: preview.account)
                            if model.phase == .review { Button("loop.edit") { model.edit() }.accessibilityIdentifier("assets.edit") }
                        }
                    }
                    if let error = model.errorKey { Text(LocalizedStringKey(error)).accessibilityIdentifier("assets.error") }
                    if model.phase == .conflict { Text("accounts.review.required") }
                    if model.uncertain { Text("loop.retry.same") }
                    Button {
                        focused = nil
                        Task { await model.save(locale: locale); if model.phase == .saved { dismiss() } }
                    } label: {
                        Text(model.uncertain ? "accounts.retry" : model.details || model.phase == .review ? "accounts.save" : "loop.review")
                            .frame(maxWidth: .infinity)
                    }.buttonStyle(PillButtonStyle()).disabled(model.phase == .saving || model.phase == .conflict)
                        .accessibilityIdentifier("assets.save")
                }.padding(24)
            }.scrollDismissesKeyboard(.interactively).background(ArgusStyle.background)
                .navigationTitle(model.details ? "assets.details" : model.selected == nil ? "assets.update" : "assets.correct")
                .navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    CuadraoCancelToolbar(title: "accounts.cancel", disabled: model.phase == .saving, identifier: "assets.cancel") { dismiss() }
                }.interactiveDismissDisabled(model.phase == .saving)
        }
    }
    private func field(_ label: LocalizedStringKey, text: Binding<String>, id: String) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(label).font(ArgusStyle.body(14, relativeTo: .subheadline))
            TextField(label, text: text).focused($focused, equals: id).padding(14)
                .overlay(RoundedRectangle(cornerRadius: 14).stroke(ArgusStyle.line)).accessibilityIdentifier(id)
        }
    }
}
