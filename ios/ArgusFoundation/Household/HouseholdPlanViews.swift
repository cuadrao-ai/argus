import SwiftUI
import ArgusSession

struct HouseholdPlanContent: View {
    @ObservedObject var model: HouseholdPlanModel
    var compact = false
    var origin = HouseholdPlanModel.Origin.plan
    var showsHeader = true
    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            if !compact {
                if showsHeader {
                    HStack {
                        Text("sharedPlan.title").font(CuadraoTypography.section)
                        Spacer()
                        if model.canStart {
                            CuadraoSectionAddButton(title: NSLocalizedString("sharedPlan.create", comment: "")) {
                                model.show(.create)
                            }.accessibilityIdentifier("sharedPlan.add")
                        }
                    }
                }
                Text("sharedPlan.privacy").font(.caption).foregroundStyle(.secondary)
                if model.canStart {
                    Button("sharedPlan.share") { model.show(.share) }
                        .font(CuadraoTypography.supporting).frame(minHeight: 44)
                        .accessibilityIdentifier("sharedPlan.share")
                }
            }
            if model.state == .idle || model.state == .loading { ProgressView("accounts.loading").accessibilityIdentifier("sharedPlan.loading") }
            if model.state == .unavailable {
                Text(LocalizedStringKey(model.errorKey ?? "household.loadError"))
                Button("accounts.retry") { Task { await model.refresh() } }.accessibilityIdentifier("sharedPlan.retry").frame(minHeight: 44)
            }
            if model.state == .ready {
                if model.plans.isEmpty {
                    Text("sharedPlan.empty").font(CuadraoTypography.section).foregroundStyle(.secondary)
                        .accessibilityIdentifier("sharedPlan.empty")
                    if model.canStart {
                        PlanPrimaryButton(title: NSLocalizedString("sharedPlan.create", comment: ""), symbol: "plus") {
                            model.show(.create)
                        }.accessibilityIdentifier("sharedPlan.empty.create")
                    }
                }
                ForEach(compact ? Array(model.plans.filter { !$0.archived }.prefix(4)) : model.plans) { plan in
                    Button { Task { await model.open(plan.ref, origin: origin) } } label: {
                        CuadraoPlanCard(display: ConnectedHouseholdPlanPresentation.card(plan))
                    }.buttonStyle(.plain).accessibilityIdentifier("sharedPlan.row." + plan.ref.kind.rawValue + "." + plan.id.uuidString)
                }
            }
        }
    }
}

struct HouseholdPlanSummary: View {
    let plan: HouseholdPlan
    var compact = false
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            switch plan.progress {
            case .budget(let c, let gross, let refunds, let spent, let over):
                value("sharedPlan.spent", spent)
                if !compact { value("sharedPlan.limit", plan.definition.amountMinor); value("sharedPlan.gross", gross); value("sharedPlan.refunds", refunds); value("sharedPlan.remaining", c.remainingMinor) }
                if over == true { Text("sharedPlan.overBudget").foregroundStyle(ArgusStyle.negative) }
            case .goal(let c, let planned, let projected):
                value("sharedPlan.actual", HouseholdPlanPresentation.backedSavings(c))
                if !compact { value("sharedPlan.target", plan.definition.amountMinor); value("sharedPlan.planned", planned); value("sharedPlan.projected", projected); value("sharedPlan.remaining", c.remainingMinor); Text("sharedPlan.plannedNotice").font(.footnote).foregroundStyle(ArgusStyle.secondary) }
            case .bill(let c):
                value("sharedPlan.paid", c.appliedMinor)
                if !compact { value("sharedPlan.agreed", plan.definition.amountMinor); value("sharedPlan.remaining", c.remainingMinor) }
            case .debt(let c):
                value("sharedPlan.balance", c.debtBalanceMinor)
                if !compact { value("sharedPlan.paid", c.appliedMinor); value("sharedPlan.agreed", plan.definition.amountMinor); value("sharedPlan.remaining", c.remainingMinor) }
            }
        }
    }
    private func value(_ key: LocalizedStringKey, _ minor: String?) -> some View {
        HStack { Text(key); Spacer(); Text(HouseholdPlanPresentation.money(minor, plan: plan)).font(CuadraoTypography.rowAmount) }
            .font(CuadraoTypography.supporting)
    }
}

struct HouseholdPlanDetailView: View {
    @ObservedObject var model: HouseholdPlanModel
    @Environment(\.locale) private var locale
    @State private var section = Section.overview
    @State private var confirmingArchive = false
    private enum Section: Hashable { case overview, contributions, people }
    private var spanish: Bool { CuadraoCopy.isSpanish() }

    var body: some View {
        VStack(alignment: .leading, spacing: 24) {
            Button("accounts.back") { model.back() }.frame(minHeight: 44).accessibilityIdentifier("sharedPlan.back")
            if model.detailLoading { ProgressView("accounts.loading") }
            if let error = model.errorKey {
                Text(LocalizedStringKey(error)).accessibilityIdentifier("sharedPlan.error")
                if !model.detailMissing, let ref = model.openedRef {
                    Button("accounts.retry") { Task { await model.open(ref, origin: model.origin) } }.frame(minHeight: 44)
                }
            }
            if let plan = model.detail {
                hero(plan)
                Picker(CuadraoCopy.text("copy.savedReceiptCopy.2b0aad47ef", spanish: spanish), selection: $section) {
                    Text(CuadraoCopy.text("copy.cuadraoGroupDetail.b7b5977d12", spanish: spanish)).tag(Section.overview)
                    Text("sharedPlan.contributions").tag(Section.contributions)
                    Text("household.people").tag(Section.people)
                }.pickerStyle(.segmented).accessibilityIdentifier("sharedPlan.sections")
                switch section {
                case .overview: overview(plan)
                case .contributions: contributions(plan)
                case .people: people(plan)
                }
            }
        }.onChange(of: model.openedRef) { _, _ in section = .overview }
    }

    private func hero(_ plan: HouseholdPlan) -> some View {
        let display = ConnectedHouseholdPlanPresentation.card(plan)
        return VStack(alignment: .leading, spacing: 16) {
            PlanGroupArtwork(look: display.look, progress: display.progress)
                .frame(height: 145).clipShape(RoundedRectangle(cornerRadius: 28))
                .overlay(alignment: .bottomLeading) {
                    Button { section = .people } label: {
                        PlanAvatarStack(members: ConnectedHouseholdPlanPresentation.members(plan)).padding(16)
                    }.buttonStyle(.plain).accessibilityLabel("household.people")
                        .accessibilityIdentifier("sharedPlan.people.open")
                }
            Text(plan.definition.common.name).font(CuadraoTypography.screen)
                .accessibilityIdentifier("sharedPlan.detail.name")
            Text(LocalizedStringKey("sharedPlan.kind." + plan.ref.kind.rawValue)).font(.caption).foregroundStyle(.secondary)
            if plan.archived {
                Text(plan.archiveReason == "owner_departed" ? "sharedPlan.ownerDeparted" : "sharedPlan.archivedNotice")
                    .font(.footnote).accessibilityIdentifier("sharedPlan.archiveNotice")
            }
            if plan.progress.common.state == .needsReview {
                Text("sharedPlan.state.needs_review").font(.footnote).accessibilityIdentifier("sharedPlan.reviewNotice")
            }
        }
    }

    @ViewBuilder private func overview(_ plan: HouseholdPlan) -> some View {
        HouseholdPlanSummary(plan: plan)
        if !plan.archived, let schedule = plan.definition.schedule {
            (Text(LocalizedStringKey("plan.repeat." + schedule.cadence.rawValue)) + Text(" · " + schedule.startDate))
                .font(CuadraoTypography.supporting).foregroundStyle(.secondary)
        }
        if case .budget(_, _, let month, let categories, let uncategorized, _) = plan.definition {
            Text(month)
            Text(categories.map { NSLocalizedString("loop.category." + $0, comment: "") }.joined(separator: ", "))
            if uncategorized { Text("budget.uncategorized") }
        }
        if plan.canEdit {
            Button("sharedPlan.edit") { model.show(.edit(plan)) }
                .accessibilityIdentifier("sharedPlan.edit").frame(minHeight: 44)
        }
        if !plan.archived {
            ForEach(plan.occurrences) { item in
                VStack(alignment: .leading, spacing: 6) {
                    CuadraoFeedRow(title: item.date,
                        detail: NSLocalizedString("sharedPlan.occurrence." + item.status.rawValue, comment: ""),
                        amount: HouseholdPlanPresentation.money(item.amountMinor, plan: plan), icon: "calendar")
                    HStack {
                        Text("sharedPlan.remaining")
                        Spacer()
                        Text(HouseholdPlanPresentation.money(item.remainingMinor, plan: plan)).font(CuadraoTypography.rowAmount)
                    }.font(.footnote).foregroundStyle(.secondary)
                }.accessibilityIdentifier("sharedPlan.occurrence." + item.id.uuidString)
            }
        }
        if plan.ref.kind == .goal {
            ForEach(plan.allocations, id: \.id) { allocation in
                HStack {
                    Text(allocation.person.displayName)
                    Spacer()
                    Text(HouseholdPlanPresentation.money(allocation.supportedMinor, plan: plan)).font(CuadraoTypography.rowAmount)
                }
            }
            if plan.canContribute {
                Button("sharedPlan.allocate") { model.show(.allocation(plan)) }
                    .frame(minHeight: 44).accessibilityIdentifier("sharedPlan.allocate")
            }
        }
        contributionActions(plan)
        Button("sharedPlan.history") { Task { await model.loadHistory(plan) } }
            .frame(minHeight: 44).accessibilityIdentifier("sharedPlan.history")
        ForEach(Array(model.history.enumerated()), id: \.offset) { _, previous in
            VStack(alignment: .leading, spacing: 6) {
                Text(previous.definition.common.name + " · " + String(previous.version))
                Text(previous.archived ? "sharedPlan.archived" : "sharedPlan.active").font(.footnote).foregroundStyle(.secondary)
            }.accessibilityIdentifier("sharedPlan.history." + String(previous.version))
        }
        if plan.canEdit || plan.canRestore {
            Button(plan.archived ? "sharedPlan.restore" : "sharedPlan.archive") {
                if plan.archived { Task { await model.archive(plan) } } else { confirmingArchive = true }
            }
            .frame(minHeight: 44).accessibilityIdentifier(plan.archived ? "sharedPlan.restore" : "sharedPlan.archive")
            .disabled(model.pending || model.busy)
            .confirmationDialog("sharedPlan.archive.confirm", isPresented: $confirmingArchive, titleVisibility: .visible) {
                Button("sharedPlan.archive") { Task { await model.archive(plan) } }
                    .accessibilityIdentifier("sharedPlan.archive.confirm")
                Button("accounts.cancel", role: .cancel) {}
            } message: { Text("sharedPlan.archive.body") }
        }
    }

    private func people(_ plan: HouseholdPlan) -> some View {
        VStack(alignment: .leading, spacing: 20) {
            HStack(spacing: 12) {
                PlanMemberAvatar(member: .init(id: plan.owner.id, name: plan.owner.displayName, symbol: "person.fill"))
                Text(plan.owner.displayName)
                Spacer()
                Text("sharedPlan.owner").font(.caption).foregroundStyle(.secondary)
            }
            ForEach(Array(plan.participants.enumerated()), id: \.element.id) { index, person in
                HStack(spacing: 12) {
                    PlanMemberAvatar(member: .init(id: person.id, name: person.displayName, symbol: "person.fill"), index: index + 1)
                    Text(person.displayName)
                    Spacer()
                    Text(LocalizedStringKey("sharedPlan.permission." + person.permission.rawValue))
                        .font(.caption).foregroundStyle(.secondary)
                }
            }
            ForEach(Array(plan.responsibilities.enumerated()), id: \.offset) { _, item in
                VStack(alignment: .leading, spacing: 6) {
                    HStack {
                        Text(item.person.displayName)
                        Spacer()
                        Text(item.amountMinor.map { HouseholdPlanPresentation.money($0, plan: plan) }
                            ?? NSLocalizedString("sharedPlan.unassigned", comment: "")).font(CuadraoTypography.rowAmount)
                    }
                    Text(HouseholdPlanPresentation.period(item, plan: plan)).font(.footnote).foregroundStyle(.secondary)
                }.accessibilityIdentifier("sharedPlan.responsibility.value." + item.person.id.uuidString)
            }
            Text("sharedPlan.responsibilityNotice").font(.footnote).foregroundStyle(.secondary)
            if plan.canEdit || plan.canManagePeople {
                Button("household.people") { model.show(.people(plan)) }
                    .accessibilityIdentifier("sharedPlan.people").frame(minHeight: 44)
            }
            Text("sharedPlan.privacy").font(.caption).foregroundStyle(.secondary)
        }
    }

    @ViewBuilder private func contributionActions(_ plan: HouseholdPlan) -> some View {
        if plan.canContribute {
            PlanPrimaryButton(title: NSLocalizedString("sharedPlan.record", comment: ""), symbol: "plus") {
                model.show(.record(plan, nil))
            }.accessibilityIdentifier("sharedPlan.record")
            Button("sharedPlan.link") { model.show(.link(plan)) }
                .frame(minHeight: 44).accessibilityIdentifier("sharedPlan.link")
        }
    }

    @ViewBuilder private func contributions(_ plan: HouseholdPlan) -> some View {
        contributionActions(plan)
        ForEach(plan.contributions) { item in
            VStack(alignment: .leading, spacing: 8) {
                CuadraoFeedRow(title: item.person.displayName,
                    detail: item.date + " · " + NSLocalizedString("sharedPlan.purpose." + item.purpose.rawValue, comment: "")
                        + " · " + NSLocalizedString("sharedPlan.claim." + item.status.rawValue, comment: ""),
                    amount: HouseholdPlanPresentation.money(item.amountMinor, currency: item.currency, digits: item.currencyFractionDigits),
                    icon: "arrow.left.arrow.right")
                if item.original != nil {
                    Button("sharedPlan.original") { Task { await model.openOriginal(item) } }
                        .accessibilityIdentifier("sharedPlan.original." + item.id.uuidString).frame(minHeight: 44)
                }
                if plan.canContribute {
                    HStack {
                        if item.canCorrect {
                            Button("household.correct") { model.show(.record(plan, item)) }
                                .accessibilityIdentifier("sharedPlan.correct." + item.id.uuidString).frame(minHeight: 44)
                        }
                        if item.canRelease {
                            Button("sharedPlan.release") { Task { await model.release(item, plan: plan) } }
                                .accessibilityIdentifier("sharedPlan.release." + item.id.uuidString).frame(minHeight: 44)
                        }
                    }.disabled(model.pending || model.busy)
                }
            }
        }
    }
}

enum HouseholdPlanPresentation {
    static func backedSavings(_ progress: HouseholdPlanCommonProgress) -> String? { progress.appliedMinor }
    static func money(_ minor: String?, plan: HouseholdPlan) -> String { money(minor, currency: plan.definition.common.currency, digits: plan.definition.common.currencyFractionDigits) }
    static func money(_ minor: String?, currency: String, digits: Int) -> String {
        guard let minor else { return currency + " " + NSLocalizedString("household.unknown", comment: "") }
        return currency + " " + AccountPresentation.amount(AccountPresentation.decimal(minor, digits: digits), locale: .current)
    }
    static func decimal(_ minor: String, digits: Int) -> String { AccountPresentation.decimal(minor, digits: digits) }
    static func period(_ item: HouseholdPlanResponsibility, plan: HouseholdPlan) -> String {
        if let period = item.period { return period }
        if let date = item.agreedDate { return date }
        if let id = item.occurrenceId { return plan.occurrences.first { $0.id == id }?.date ?? NSLocalizedString("sharedPlan.previousOccurrence", comment: "") }
        return NSLocalizedString("sharedPlan.schedule", comment: "")
    }
}
