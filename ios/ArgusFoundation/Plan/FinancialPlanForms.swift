import SwiftUI
import ArgusSession

struct FinancialExpectationForm: View {
    @ObservedObject var model: FinancialPlanModel
    @ObservedObject var draft: FinancialExpectationDraft
    @ObservedObject var loop: FinancialLoopModel
    @Environment(\.dismiss) private var dismiss
    @Environment(\.locale) private var locale
    @FocusState private var focused: Bool
    private var accounts: [FinancialAccount] {
        (model.projection?.accounts ?? []).filter { !$0.archived && ["cash", "checking", "savings"].contains($0.type) && $0.currency == draft.currency }
    }
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 22) {
                    Group {
                    Picker("plan.kind", selection: $draft.kind) {
                        ForEach(FinancialExpectationKind.allCases, id: \.self) { kind in
                            Text(LocalizedStringKey("plan.kind." + kind.rawValue)).tag(kind)
                        }
                    }.disabled(draft.existing != nil).accessibilityIdentifier("plan.expectation.kind")
                    if draft.seededFromActivity {
                        Text("plan.fromActivity.hint").font(ArgusStyle.body(13, relativeTo: .subheadline)).foregroundStyle(ArgusStyle.secondary)
                            .accessibilityIdentifier("plan.expectation.fromActivity")
                    }
                    field("plan.name", identifier: "plan.expectation.name", text: $draft.title)
                    if draft.existing == nil {
                        Picker("accounts.currency", selection: $draft.currency) {
                            ForEach(PlanCurrency.supported, id: \.self) {
                                Text(verbatim: $0).tag($0)
                            }
                        }.accessibilityIdentifier("plan.expectation.currency")
                    }
                    VStack(alignment: .leading, spacing: 8) {
                        Text("loop.amount")
                        HStack(alignment: .firstTextBaseline, spacing: 12) {
                            Text(verbatim: draft.currency).font(CuadraoTypography.supporting).foregroundStyle(.secondary)
                            TextField("0.00", text: $draft.amount).keyboardType(.decimalPad).focused($focused)
                                .font(CuadraoTypography.amount).monospacedDigit().accessibilityIdentifier("plan.expectation.amount")
                        }.padding(18).background(WelcomePalette.surface, in: RoundedRectangle(cornerRadius: 20))
                    }
                    Picker("loop.activity.account", selection: $draft.accountId) {
                        Text("plan.account.unassigned").tag(nil as UUID?)
                        ForEach(accounts) { account in
                            Text(account.nickname ?? NSLocalizedString("accounts.type." + account.type, comment: "")).tag(Optional(account.id))
                        }
                    }.accessibilityIdentifier("plan.expectation.account")
                    Text("plan.account.hint").font(ArgusStyle.body(12, relativeTo: .caption)).foregroundStyle(ArgusStyle.secondary)
                    DatePicker("plan.date", selection: $draft.date, displayedComponents: .date)
                        .accessibilityIdentifier("plan.expectation.date")
                    Picker("plan.repeat", selection: $draft.cadence) {
                        ForEach(FinancialPlanSchedule.Cadence.allCases, id: \.self) { cadence in
                            Text(LocalizedStringKey("plan.repeat." + cadence.rawValue)).tag(cadence)
                        }
                    }.accessibilityIdentifier("plan.expectation.recurrence")
                    if draft.cadence == .monthly || draft.cadence == .twiceMonthly {
                        monthDay("plan.monthDay", selection: $draft.firstMonthDay, identifier: "plan.expectation.monthDay")
                        if draft.cadence == .twiceMonthly {
                            monthDay("plan.secondMonthDay", selection: $draft.secondMonthDay, identifier: "plan.expectation.secondMonthDay")
                        }
                        Text("plan.monthEnd.hint").font(ArgusStyle.body(12, relativeTo: .caption)).foregroundStyle(ArgusStyle.secondary)
                    }
                    if draft.cadence != .once {
                        Toggle("plan.hasEnd", isOn: $draft.hasEnd)
                        if draft.hasEnd { DatePicker("plan.endDate", selection: $draft.end, in: draft.date..., displayedComponents: .date) }
                    }
                    if draft.structuralChange, let existing = draft.existing {
                        DatePicker("plan.effectiveDate", selection: $draft.effectiveDate,
                                   in: PlanPresentation.date(existing.earliestEffectiveDate)..., displayedComponents: .date)
                            .accessibilityIdentifier("plan.expectation.effectiveDate")
                        Text("plan.cutover.hint").font(ArgusStyle.body(12, relativeTo: .caption)).foregroundStyle(ArgusStyle.secondary)
                    }
                    Text("plan.expectation.disclosure").font(ArgusStyle.body(13, relativeTo: .subheadline)).foregroundStyle(ArgusStyle.secondary)
                    }.disabled(model.saving || loop.pendingConfirmation != nil)
                    if let error = model.errorKey { Text(LocalizedStringKey(error)).foregroundStyle(ArgusStyle.secondary).accessibilityIdentifier("plan.error") }
                    if loop.pendingConfirmation != nil {
                        PlanPendingView(loop: loop)
                    } else {
                        PlanPrimaryButton(title: NSLocalizedString("plan.saveExpectation", comment: "")) { focused = false; Task { await model.save(locale: locale) } }
                            .disabled(!draft.ready || model.saving)
                            .accessibilityIdentifier("plan.expectation.save")
                    }
                    if model.saving { ProgressView("accounts.loading") }
                }.padding(24).font(CuadraoTypography.body)
            }.background(WelcomePalette.background).foregroundStyle(WelcomePalette.ink).tint(WelcomePalette.pine)
                .scrollDismissesKeyboard(.interactively)
                .environment(\.timeZone, TimeZone(secondsFromGMT: 0)!)
                .navigationTitle(draft.existing == nil ? "plan.add.title" : "plan.editExpectation.title")
                .navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    CuadraoCancelToolbar(title: "accounts.cancel", disabled: model.saving) { dismiss() }
                }
                .interactiveDismissDisabled(model.saving)
                .onChange(of: draft.currency) { _, _ in draft.accountId = nil }
                .onChange(of: draft.cadence) { _, cadence in
                    if cadence == .monthly { draft.firstMonthDay = PlanPresentation.monthDay(PlanPresentation.day(draft.date)) }
                }
        }
    }
    private func field(_ title: LocalizedStringKey, identifier: String, text: Binding<String>) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title)
            TextField(title, text: text).focused($focused).padding(14)
                .overlay(RoundedRectangle(cornerRadius: 14).stroke(ArgusStyle.line)).accessibilityIdentifier(identifier)
        }
    }
    private func monthDay(_ title: LocalizedStringKey, selection: Binding<Int>, identifier: String) -> some View {
        Picker(title, selection: selection) {
            ForEach(1...31, id: \.self) { day in
                if day == 31 { Text("plan.lastDay").tag(day) }
                else { Text(verbatim: String(day)).tag(day) }
            }
        }.accessibilityIdentifier(identifier)
    }
}

struct FinancialPlanSelectionView: View {
    @ObservedObject var model: FinancialPlanModel
    @ObservedObject var loop: FinancialLoopModel
    let projection: FinancialPlanProjection
    @State private var ids: Set<UUID>
    @State private var zone: String
    @Environment(\.dismiss) private var dismiss
    init(model: FinancialPlanModel, loop: FinancialLoopModel, projection: FinancialPlanProjection) {
        self.model = model; self.loop = loop; self.projection = projection
        _ids = State(initialValue: Set(projection.selection.accountIds)); _zone = State(initialValue: projection.selection.timeZone)
    }
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    Text("plan.selection.hint").foregroundStyle(ArgusStyle.secondary)
                    ForEach(projection.accounts.filter {
                        projection.selection.accountIds.contains($0.id) || (!$0.archived && ["cash", "checking", "savings"].contains($0.type))
                    }) { account in
                        Toggle(isOn: Binding(get: { ids.contains(account.id) }, set: { included in
                            if included { ids.insert(account.id) } else { ids.remove(account.id) }
                        })) {
                            VStack(alignment: .leading, spacing: 6) {
                                AccountRow(account: account)
                                if account.archived { Text("accounts.archived").font(ArgusStyle.body(12, relativeTo: .caption)) }
                                if !["cash", "checking", "savings"].contains(account.type) {
                                    Text("plan.selection.unavailable").font(ArgusStyle.body(12, relativeTo: .caption))
                                }
                            }
                        }.accessibilityIdentifier("plan.selection." + account.id.uuidString)
                            .disabled(!["cash", "checking", "savings"].contains(account.type) && !ids.contains(account.id))
                    }
                    Picker("plan.timeZone", selection: $zone) {
                        ForEach(Array(Set([projection.selection.timeZone, TimeZone.current.identifier, "America/Santo_Domingo"])).sorted(), id: \.self) {
                            Text(verbatim: $0).tag($0)
                        }
                    }
                    Text("plan.timeZone.hint").font(ArgusStyle.body(12, relativeTo: .caption)).foregroundStyle(ArgusStyle.secondary)
                    if let error = model.errorKey { Text(LocalizedStringKey(error)).foregroundStyle(ArgusStyle.secondary) }
                    if loop.pendingConfirmation != nil { PlanPendingView(loop: loop) }
                    else {
                        Button("plan.selection.confirm") { Task { if await model.selectAccounts(ids, timeZone: zone) { dismiss() } } }
                            .buttonStyle(PillButtonStyle()).disabled(model.saving).accessibilityIdentifier("plan.selection.save")
                    }
                }.padding(24)
            }.background(WelcomePalette.background).foregroundStyle(WelcomePalette.ink).tint(WelcomePalette.pine)
                .navigationTitle("plan.includedAccounts").navigationBarTitleDisplayMode(.inline)
                .toolbar { CuadraoCancelToolbar(title: "accounts.cancel", disabled: model.saving) { dismiss() }}
                .interactiveDismissDisabled(model.saving)
        }
    }
}

struct FinancialOccurrenceView: View {
    @ObservedObject var model: FinancialPlanModel
    @ObservedObject var loop: FinancialLoopModel
    let occurrence: FinancialPlanOccurrence
    @State private var linking = false
    @State private var candidate: FinancialActivityDetail?
    @Environment(\.locale) private var locale
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    FinancialOccurrenceRow(occurrence: occurrence)
                    if let accountId = occurrence.accountId,
                       let account = model.projection?.accounts.first(where: { $0.id == accountId }) {
                        PlanValueRow(title: "loop.activity.account", value: account.nickname ?? NSLocalizedString("accounts.type." + account.type, comment: ""))
                    }
                    if model.loadingDetails { ProgressView("accounts.loading") }
                    if let activity = model.linkedActivity {
                        activityReview(activity)
                        Button("plan.viewActivity.title") { model.correctLinked() }
                            .buttonStyle(PillButtonStyle()).disabled(loop.pendingConfirmation != nil).accessibilityIdentifier("plan.viewActivity")
                    }
                    if occurrence.activityId == nil {
                        PlanPrimaryButton(title: NSLocalizedString(occurrence.kind == .income ? "plan.recordIncome" : "plan.recordBill", comment: "")) { model.record(occurrence) }
                            .disabled(occurrence.status == .needsReview || occurrence.exclusionReason == "account_changed" || occurrence.accountId == nil || loop.pendingConfirmation != nil)
                            .accessibilityIdentifier("plan.record")
                    }
                    Button("plan.link.title") { linking = true; Task { await model.loadCandidates(occurrence) } }
                        .frame(minHeight: 44).disabled(loop.pendingConfirmation != nil || occurrence.accountId == nil).accessibilityIdentifier("plan.link")
                    if linking {
                        Text("plan.link.hint").font(ArgusStyle.body(13, relativeTo: .subheadline)).foregroundStyle(ArgusStyle.secondary)
                        if model.candidates.isEmpty && !model.loadingDetails && model.errorKey == nil { Text("plan.link.empty").foregroundStyle(ArgusStyle.secondary) }
                        ForEach(model.candidates) { activity in
                            Button { candidate = activity } label: {
                                VStack(alignment: .leading, spacing: 6) {
                                    Text(activity.note ?? NSLocalizedString("loop.kind." + activity.kind.rawValue, comment: ""))
                                    Text(verbatim: activity.currency + " " + AccountPresentation.amount(activity.amount, locale: locale))
                                    Text(verbatim: AccountPresentation.date(activity.occurredAt, zone: activity.timeZone, locale: locale))
                                }.frame(maxWidth: .infinity, alignment: .leading).padding(.vertical, 12).contentShape(Rectangle())
                            }.buttonStyle(.plain).accessibilityIdentifier("plan.candidate." + activity.activityId.uuidString)
                        }
                        if let candidate {
                            activityReview(candidate)
                            Text("plan.link.confirmHint").font(ArgusStyle.body(13, relativeTo: .subheadline))
                            PlanPrimaryButton(title: NSLocalizedString("plan.link.confirmTitle", comment: "")) { Task { _ = await model.link(candidate, to: occurrence) } }
                                .disabled(model.saving || loop.pendingConfirmation != nil)
                                .accessibilityIdentifier("plan.link.confirm")
                        }
                    }
                    if let expectation = model.projection?.expectations.first(where: { $0.id == occurrence.expectationId }) {
                        Button("plan.editExpectation.title") {
                            model.editFromOccurrence(expectation)
                        }.frame(minHeight: 44).disabled(loop.pendingConfirmation != nil).accessibilityIdentifier("plan.editExpectation")
                    }
                    if let error = model.errorKey { Text(LocalizedStringKey(error)).foregroundStyle(ArgusStyle.secondary) }
                    if loop.pendingConfirmation != nil { PlanPendingView(loop: loop) }
                }.padding(24)
            }.background(WelcomePalette.background).foregroundStyle(WelcomePalette.ink).tint(WelcomePalette.pine)
                .navigationTitle(occurrence.title).navigationBarTitleDisplayMode(.inline)
                .toolbar { CuadraoCancelToolbar(title: "action.close", disabled: model.saving) { model.selectedOccurrence = nil }}
                .interactiveDismissDisabled(model.saving)
        }
    }
    private func activityReview(_ activity: FinancialActivityDetail) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("plan.recordedActivity").font(CuadraoTypography.section)
            Text(LocalizedStringKey("loop.kind." + activity.kind.rawValue))
            Text(verbatim: activity.currency + " " + AccountPresentation.amount(activity.amount, locale: locale)).monospacedDigit()
            Text(verbatim: AccountPresentation.date(activity.occurredAt, zone: activity.timeZone, locale: locale))
            if let note = activity.note { Text(note) }
            ForEach(activity.legs) { leg in
                if let account = model.projection?.accounts.first(where: { $0.id == leg.accountId }) {
                    Text(account.nickname ?? NSLocalizedString("accounts.type." + account.type, comment: ""))
                }
            }
        }.font(ArgusStyle.body(14, relativeTo: .subheadline)).padding(16)
            .frame(maxWidth: .infinity, alignment: .leading).overlay(RoundedRectangle(cornerRadius: 14).stroke(ArgusStyle.line))
    }
}
