import SwiftUI
import ArgusSession

struct AccountForm: View {
    @ObservedObject var model: AccountsModel
    @Environment(\.locale) private var locale
    @State private var choosingType = true
    @State private var otherAssets = false
    @FocusState private var focusedField: String?
    private let primaryTypes = ["cash", "checking", "savings", "investment", "credit_card", "other_debt"]
    private var locked: Bool { model.busy || model.createIsFrozen || model.openingIsReviewed }

    var body: some View {
        NavigationStack {
            ScrollView {
                if let draft = model.draft {
                    VStack(alignment: .leading, spacing: 24) {
                        if draft.mode == .create {
                            Text("accounts.setup.hint").foregroundStyle(ArgusStyle.secondary)
                        }
                        if draft.mode != .opening {
                            typeControl(draft)
                            field("accounts.nickname", text: binding(\.nickname), identifier: "accounts.nickname")
                        }
                        if draft.mode != .metadata {
                            amountControl(draft)
                        } else {
                            currencyControl
                        }
                        if draft.mode == .create && ["property", "vehicle", "other_asset"].contains(draft.type) {
                            AssetShareControl(share: binding(\.share)).disabled(locked)
                        }
                        if draft.mode != .create {
                            savedDetails(draft)
                        }
                        if let preview = model.openingPreview { openingReview(preview) }
                        if let error = model.errorKey {
                            Text(LocalizedStringKey(error)).fixedSize(horizontal: false, vertical: true)
                                .accessibilityIdentifier("accounts.form.error")
                        }
                        if model.needsReview {
                            Text("accounts.review.required")
                            if let latest = model.latest {
                                AccountSummary(account: latest)
                                Button("accounts.review.latest") { model.editLatest() }
                                    .buttonStyle(PillButtonStyle(primary: false)).accessibilityIdentifier("accounts.review.latest")
                            } else {
                                Text("accounts.review.unavailable")
                            }
                        } else {
                            if model.createIsFrozen {
                                Text("accounts.create.retry").font(ArgusStyle.body(12, relativeTo: .caption))
                            }
                            Button { focusedField = nil; Task { await model.save(locale: locale) } } label: {
                                Text(model.createIsFrozen || model.openingUncertain ? "accounts.retry" : draft.mode == .create ? "accounts.add" : draft.mode == .opening && !model.openingIsReviewed ? "loop.review" : "accounts.save")
                                    .frame(maxWidth: .infinity)
                            }
                            .buttonStyle(PillButtonStyle()).disabled(model.busy)
                            .accessibilityIdentifier("accounts.save")
                        }
                        if model.openingUncertain { Text("loop.retry.same") }
                        if model.busy { ProgressView("accounts.saving") }
                    }.padding(24)
                }
            }
            .scrollDismissesKeyboard(.interactively)
            .background(ArgusStyle.background)
            .navigationTitle(Text(model.draft?.mode == .create ? "accounts.add" : "accounts.form.title"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                CuadraoCancelToolbar(title: NSLocalizedString("accounts.cancel", comment: ""),
                                     disabled: model.busy || model.openingUncertain,
                                     identifier: "accounts.cancel") { model.discard() }
            }
            .interactiveDismissDisabled()
        }
    }

    private func openingReview(_ preview: OpeningPreview) -> some View {
        VStack(alignment: .leading, spacing: 18) {
            if preview.ready {
                HStack {
                    Text("loop.after"); Spacer()
                    if let amount = preview.after?.amount {
                        Text(verbatim: (model.draft?.currency ?? "") + " " + AccountPresentation.amount(amount, locale: locale)).monospacedDigit()
                    } else { Text("accounts.unknown") }
                }
                if !model.openingUncertain { Button("loop.edit") { model.editOpening() }.accessibilityIdentifier("loop.edit") }
            } else { Text("loop.opening.coverage").font(ArgusStyle.display(22)) }
            ForEach(preview.activities, id: \.activityId) { activity in
                VStack(alignment: .leading, spacing: 8) {
                    if let note = activity.note, !note.isEmpty { Text(verbatim: note) }
                    Text(verbatim: (model.draft?.currency ?? "") + " " + AccountPresentation.amount(activity.amount, locale: locale))
                    if !model.openingUncertain {
                        HStack {
                            Button("loop.coverage.yes") { Task { await model.answerOpening(activity.activityId, included: true, locale: locale) } }
                                .buttonStyle(PillButtonStyle(primary: activity.included == true)).accessibilityIdentifier(activity.included == nil ? "opening.coverage.yes" : "opening.coverage.change.yes")
                            Button("loop.coverage.no") { Task { await model.answerOpening(activity.activityId, included: false, locale: locale) } }
                                .buttonStyle(PillButtonStyle(primary: activity.included == false)).accessibilityIdentifier(activity.included == nil ? "opening.coverage.no" : "opening.coverage.change.no")
                        }.disabled(model.busy)
                    } else { Text(activity.included == true ? "loop.coverage.included" : "loop.coverage.excluded") }
                }
            }
        }
    }

    private func amountControl(_ draft: AccountDraft) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text(draft.base?.nature == "liability" || ["credit_card", "other_debt"].contains(draft.type)
                     ? "accounts.amount.owed" : ["property", "vehicle", "other_asset"].contains(draft.type) ? "assets.whole" : "accounts.amount")
                    .font(ArgusStyle.body(14, relativeTo: .subheadline))
                Spacer()
                if draft.mode == .create { currencyControl }
                else { Text(verbatim: draft.currency).foregroundStyle(ArgusStyle.secondary) }
            }
            HStack(spacing: 8) {
                TextField("accounts.amount.placeholder", text: binding(\.amount))
                    .keyboardType(.decimalPad).focused($focusedField, equals: "accounts.amount").monospacedDigit()
                    .accessibilityIdentifier("accounts.amount")
                Button {
                    guard !locked else { return }
                    let value = model.draft?.amount ?? ""
                    model.changedOpeningInput()
                    model.draft?.amount = value.hasPrefix("-") ? String(value.dropFirst()) : "-" + value
                } label: {
                    Image(systemName: "plus.forwardslash.minus").frame(width: 44, height: 44)
                }
                .accessibilityLabel("accounts.amount.sign")
                .accessibilityIdentifier("accounts.amount.sign")
            }
            .padding(.leading, 14).frame(minHeight: 52)
            .overlay(RoundedRectangle(cornerRadius: 14).stroke(ArgusStyle.line))
            .disabled(locked)
            Text(draft.mode == .opening && draft.base?.opening != nil ? "accounts.amount.unchanged" : "accounts.amount.optional")
                .font(ArgusStyle.body(12, relativeTo: .caption)).foregroundStyle(ArgusStyle.secondary)
        }
    }

    private var currencyControl: some View {
        Menu {
            Picker("accounts.currency", selection: binding(\.currency)) {
                ForEach(PlanCurrency.supported, id: \.self) { code in
                    Text(verbatim: code).tag(code)
                }
            }
        } label: {
            HStack(spacing: 6) {
                Text(verbatim: model.draft?.currency ?? "")
                Image(systemName: "chevron.down").font(.system(size: 10))
            }
            .font(ArgusStyle.body(13, relativeTo: .caption)).padding(.horizontal, 14)
            .frame(minHeight: 44).background(ArgusStyle.surface, in: Capsule())
        }
        .disabled(locked).accessibilityLabel("accounts.currency").accessibilityIdentifier("accounts.currency")
    }

    @ViewBuilder private func typeControl(_ draft: AccountDraft) -> some View {
        if draft.mode == .create && choosingType {
            VStack(alignment: .leading, spacing: 10) {
                Text("accounts.type").font(ArgusStyle.body(12, relativeTo: .caption)).foregroundStyle(ArgusStyle.secondary)
                LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 8), count: 3), spacing: 8) {
                    ForEach(primaryTypes, id: \.self) { type in typeButton(type) }
                }
                DisclosureGroup(isExpanded: $otherAssets) {
                    ForEach(["property", "vehicle", "other_asset"], id: \.self) { type in typeButton(type) }
                } label: {
                    Text("accounts.otherAssets").accessibilityIdentifier("accounts.otherAssets")
                }.font(ArgusStyle.body(13, relativeTo: .caption)).padding(.top, 4)
            }.disabled(locked)
        } else if draft.mode == .create {
            HStack(spacing: 12) {
                Image(systemName: AccountPresentation.symbol(draft.type)).frame(width: 24)
                Text(LocalizedStringKey("accounts.type." + draft.type))
                Spacer()
                Button("accounts.type.change") { choosingType = true }.frame(minHeight: 44)
                    .accessibilityIdentifier("accounts.type.change")
            }.disabled(locked)
        } else {
            Picker("accounts.type", selection: binding(\.type)) {
                ForEach(primaryTypes + ["property", "vehicle", "other_asset"], id: \.self) { type in
                    Text(LocalizedStringKey("accounts.type." + type)).tag(type)
                }
            }.frame(minHeight: 48).disabled(locked).accessibilityIdentifier("accounts.type")
        }
    }

    private func typeButton(_ type: String) -> some View {
        Button {
            guard !locked else { return }
            model.draft?.type = type; choosingType = false
        } label: {
            VStack(spacing: 8) {
                Image(systemName: AccountPresentation.symbol(type)).font(.system(size: 21))
                Text(LocalizedStringKey("accounts.type." + type)).font(ArgusStyle.body(11, relativeTo: .caption))
                    .multilineTextAlignment(.center)
            }
            .frame(maxWidth: .infinity).frame(minHeight: 72)
            .overlay(RoundedRectangle(cornerRadius: 14).stroke(ArgusStyle.line))
            .contentShape(RoundedRectangle(cornerRadius: 14))
        }.buttonStyle(.plain).accessibilityIdentifier("accounts.type." + type)
    }

    @ViewBuilder private func savedDetails(_ draft: AccountDraft) -> some View {
        if draft.mode == .metadata && draft.base?.isOptionalAsset != true {
            DisclosureGroup("accounts.ownership") {
                field("accounts.share", text: binding(\.share), identifier: "accounts.share").keyboardType(.decimalPad)
                Text("accounts.share.help").font(ArgusStyle.body(12, relativeTo: .caption))
            }.disabled(locked)
        } else if draft.mode == .opening {
            DisclosureGroup("accounts.date.details") {
                DatePicker("accounts.date", selection: dateBinding, in: ...Date(), displayedComponents: [.date, .hourAndMinute])
                    .environment(\.timeZone, TimeZone(identifier: draft.timeZone) ?? .gmt)
                    .accessibilityIdentifier("accounts.date")
                Picker("accounts.zone", selection: binding(\.timeZone)) {
                    ForEach(TimeZone.knownTimeZoneIdentifiers, id: \.self) { zone in Text(verbatim: zone).tag(zone) }
                }.frame(minHeight: 48).accessibilityIdentifier("accounts.zone")
            }.disabled(locked)
            if draft.base?.opening != nil {
                field("accounts.reason", text: binding(\.reason), identifier: "accounts.reason")
            }
        }
    }

    private var dateBinding: Binding<Date> {
        Binding(get: { AccountPresentation.parseDate(model.draft?.asOf ?? "") ?? Date() }, set: { date in
            guard !locked else { return }
            let formatter = ISO8601DateFormatter()
            formatter.timeZone = TimeZone(identifier: model.draft?.timeZone ?? "") ?? .gmt
            model.changedOpeningInput()
            model.draft?.asOf = formatter.string(from: date)
        })
    }

    private func binding(_ path: WritableKeyPath<AccountDraft, String>) -> Binding<String> {
        Binding(get: { model.draft?[keyPath: path] ?? "" }, set: { value in
            guard !locked else { return }
            model.changedOpeningInput()
            model.draft?[keyPath: path] = value
        })
    }
    private func field(_ key: LocalizedStringKey, text: Binding<String>, identifier: String) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(key).font(ArgusStyle.body(14, relativeTo: .subheadline))
            TextField(key, text: text).focused($focusedField, equals: identifier).padding(.horizontal, 14).frame(minHeight: 52)
                .overlay(RoundedRectangle(cornerRadius: 14).stroke(ArgusStyle.line))
                .accessibilityIdentifier(identifier)
        }.disabled(locked)
    }
}
