import SwiftUI
import ArgusSession

struct HouseholdPlanActionSheet: View {
    @ObservedObject var model: HouseholdPlanModel
    let plan: HouseholdPlan
    var allocating = false
    @Environment(\.locale) private var locale
    @Environment(\.dismiss) private var dismiss
    @FocusState private var focused: Bool
    @State private var options: HouseholdPlanOptions?
    @State private var candidates: [FinancialActivityDetail] = []
    @State private var activityId: UUID?
    @State private var accountId: UUID?
    @State private var amount = ""
    @State private var purpose = HouseholdContributionPurpose.spending
    @State private var occurrenceId: UUID?
    @State private var treatment = "add"
    @State private var loading = false
    @State private var error: String?
    private var candidate: FinancialActivityDetail? { candidates.first { $0.id == activityId } }
    private var accounts: [FinancialAccount] { options?.money.accounts.filter { options?.ownedAccountIds.contains($0.id) == true && $0.currency == plan.definition.common.currency && ["cash", "checking", "savings"].contains($0.type) } ?? [] }
    var body: some View {
        NavigationStack {
            Form {
                if let options {
                    Section {
                        Text(allocating ? "sharedPlan.allocationNotice" : "sharedPlan.linkNotice").font(.footnote)
                        if allocating {
                            Picker("household.account", selection: $accountId) { Text("household.choose").tag(UUID?.none); ForEach(accounts) { Text($0.nickname ?? NSLocalizedString("accounts.type." + $0.type, comment: "")).tag(Optional($0.id)) } }.accessibilityIdentifier("sharedPlan.allocation.account")
                            TextField("household.amount", text: $amount).keyboardType(.decimalPad).focused($focused).accessibilityIdentifier("sharedPlan.allocation.amount")
                            Text("sharedPlan.allocationRelease").font(.footnote)
                        } else {
                            Picker("sharedPlan.purpose", selection: $purpose) { ForEach(options.purposes[plan.ref.kind.rawValue] ?? [], id: \.self) { Text(LocalizedStringKey("sharedPlan.purpose." + $0.rawValue)).tag($0) } }.accessibilityIdentifier("sharedPlan.contribution.purpose")
                            Picker("sharedPlan.occurrence", selection: $occurrenceId) {
                                Text("sharedPlan.noOccurrence").tag(UUID?.none); ForEach(plan.occurrences) { Text($0.date).tag(Optional($0.id)) }
                            }.accessibilityIdentifier("sharedPlan.contribution.occurrence")
                            Picker("sharedPlan.activity", selection: $activityId) {
                                Text("household.choose").tag(UUID?.none)
                                ForEach(candidates) { item in Text(item.currency + " " + AccountPresentation.amount(item.amount, locale: locale) + " · " + String(item.occurredAt.prefix(10)) + " · " + (item.note ?? NSLocalizedString("loop.kind." + item.kind.rawValue, comment: ""))).tag(Optional(item.id)) }
                            }.accessibilityIdentifier("sharedPlan.link.activity")
                            if candidates.isEmpty { Text("sharedPlan.noCandidates").accessibilityIdentifier("sharedPlan.link.empty") }
                            if plan.ref.kind == .goal {
                                Picker("goal.link.treatment", selection: $treatment) { Text("goal.link.add").tag("add"); Text("goal.link.included").tag("included") }.accessibilityIdentifier("sharedPlan.link.treatment")
                            }
                        }
                    }
                    if let error { Text(LocalizedStringKey(error)).accessibilityIdentifier("sharedPlan.form.error") }
                    Button(allocating ? "sharedPlan.confirmAllocation" : "sharedPlan.confirmLink") { focused = false; Task { await save() } }
                        .disabled(loading || model.pending || model.busy || (allocating ? accountId == nil || amount.isEmpty : candidate == nil)).accessibilityIdentifier("sharedPlan.confirm")
                } else if loading { ProgressView("accounts.loading") }
                else if let error { Text(LocalizedStringKey(error)); Button("accounts.retry") { Task { await load() } } }
            }
            .navigationTitle(allocating ? "sharedPlan.allocate" : "sharedPlan.link")
            .scrollDismissesKeyboard(.interactively)
            .toolbar {
                CuadraoCancelToolbar(title: "accounts.cancel") { dismiss() }
            }
            .task { await load() }
        }
    }
    private func load() async {
        loading = true; defer { loading = false }
        do {
            options = try await model.options()
            if !allocating { candidates = try await model.candidates(plan); if let first = options?.purposes[plan.ref.kind.rawValue]?.first { purpose = first } }
            error = nil
        } catch { self.error = HouseholdPlanModel.message(error) }
    }
    private func save() async {
        guard let identity = model.identity, model.isCurrent(plan, identity), let options else { error = "sharedPlan.changed"; return }
        if allocating {
            guard let accountId, let account = accounts.first(where: { $0.id == accountId }) else { error = "sharedPlan.changed"; return }
            do {
                let value = try AccountEntry.amount(amount, locale: locale) ?? ""
                await model.submit(HouseholdPlanAllocationCommand(scope: model.scope(plan), accountId: accountId, amount: value, expectedAccountVersions: [accountId.uuidString: account.version]), action: .allocation(plan.ref))
            } catch { self.error = "household.reviewError" }
        } else {
            guard let candidate else { return }
            var versions: [String: Int] = [:]
            for leg in candidate.legs {
                guard let account = options.money.accounts.first(where: { $0.id == leg.accountId }) else { error = "sharedPlan.changed"; return }
                versions[account.id.uuidString] = account.version
            }
            await model.submit(HouseholdContributionLinkCommand(scope: model.scope(plan), activityId: candidate.id, activityRevision: candidate.revision, expectedAccountVersions: versions, purpose: purpose, occurrenceId: occurrenceId, treatment: treatment), action: .link(plan.ref))
        }
    }
}

struct HouseholdPlanPresenter: View {
    @ObservedObject var model: HouseholdPlanModel
    var body: some View {
        Color.clear.sheet(item: $model.sheet) { sheet in
            Group { switch sheet {
            case .create: HouseholdPlanDefinitionEditor(model: model)
            case .share: HouseholdPlanDefinitionEditor(model: model, sharing: true)
            case .edit(let plan): HouseholdPlanDefinitionEditor(model: model, editing: plan)
            case .people(let plan): HouseholdPlanPeopleEditor(model: model, plan: plan)
            case .record(let plan, let contribution): HouseholdContributionEditorView(model: model, plan: plan, correcting: contribution)
            case .link(let plan): HouseholdPlanActionSheet(model: model, plan: plan)
            case .allocation(let plan): HouseholdPlanActionSheet(model: model, plan: plan, allocating: true)
            case .original(let plan, let contribution): HouseholdPlanOriginalView(model: model, plan: plan, contribution: contribution)
            } }.tint(WelcomePalette.pine).foregroundStyle(ArgusStyle.ink)
        }
    }
}

private struct HouseholdPlanOriginalView: View {
    @ObservedObject var model: HouseholdPlanModel
    let plan: HouseholdPlan
    let contribution: HouseholdPlanContribution
    @State private var activity: FinancialActivityDetail?
    @State private var account: HouseholdAccountDetail?
    @State private var error: String?
    @Environment(\.dismiss) private var dismiss
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    if let activity {
                        Text(LocalizedStringKey("loop.kind." + activity.kind.rawValue)).font(ArgusStyle.display(25))
                        Text(activity.currency + " " + AccountPresentation.amount(activity.amount, locale: .current)).font(ArgusStyle.display(28))
                        Text(activity.occurredAt)
                        if let note = activity.note { Text(note) }
                    } else if let account {
                        Text(account.account.account.nickname ?? NSLocalizedString("household.account", comment: "")).font(ArgusStyle.display(25))
                        ForEach(account.activities.filter { $0.id == contribution.original?.activityId }) { item in
                            Text(item.activity.currency + " " + (item.activity.amount ?? NSLocalizedString("household.unknown", comment: "")))
                            Text(item.activity.occurredAt)
                        }
                    } else if error == nil { ProgressView("accounts.loading") }
                    if let error { Text(LocalizedStringKey(error)); Button("accounts.retry") { Task { await load() } } }
                    if contribution.canCorrect, plan.canContribute, activity?.originalAmountAvailable == true || account != nil {
                        Button("household.correct") { model.sheet = .record(plan, contribution) }.buttonStyle(PillButtonStyle()).accessibilityIdentifier("sharedPlan.original.correct")
                    }
                }.padding(24)
            }.navigationTitle("sharedPlan.original")
                .toolbar { CuadraoCancelToolbar(title: "accounts.back", identifier: "sharedPlan.original.back") { dismiss() }}
                .task { await load() }
        }
    }
    private func load() async {
        guard let original = contribution.original, let identity = model.identity, model.isCurrent(plan, identity), let controller = model.controller else { return }
        do {
            if let householdId = original.householdId {
                let value = try await controller.householdResponse(HouseholdAccountDetail.self, path: "/" + householdId.uuidString + "/accounts/" + original.accountId.uuidString, expectedIdentity: identity)
                guard model.isCurrent(plan, identity) else { return }; account = value
            } else {
                let value = try await controller.financialActivityDetail(original.activityId, expectedIdentity: identity)
                guard model.isCurrent(plan, identity) else { return }; activity = value
            }
            error = nil
        } catch { if model.isCurrent(plan, identity) { self.error = "search.destination.unavailable" } }
    }
}
