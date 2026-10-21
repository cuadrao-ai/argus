import SwiftUI
import ArgusSession

struct FinancialGoalList: View {
    @ObservedObject var plan: FinancialPlanModel
    @ObservedObject var model: FinancialGoalModel
    let origin: FinancialGoalNavigation.Origin
    private var items: [FinancialGoalProgress] { (plan.projection?.goals ?? []).filter { !$0.goal.archived } }
    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            Text("plan.goals").font(ArgusStyle.display(23))
            if items.isEmpty { Text("goal.empty").foregroundStyle(ArgusStyle.secondary) }
            ForEach(items) { progress in
                Button { Task { await model.open(progress.id, origin: origin) } } label: {
                    VStack(alignment: .leading, spacing: 12) {
                        HStack { Text(verbatim: progress.goal.name); Spacer(); Image(systemName: "chevron.right").font(.system(size: 12)) }
                        FinancialGoalSummary(progress: progress, compact: true)
                    }.padding(.vertical, 14).contentShape(Rectangle())
                }.buttonStyle(.plain).accessibilityIdentifier("goal.row." + origin.rawValue + "." + progress.id.uuidString)
            }
        }
    }
}

struct FinancialGoalSummary: View {
    let progress: FinancialGoalProgress
    var compact = false
    @Environment(\.locale) private var locale
    private func amount(_ value: String?) -> String {
        value.map { PlanPresentation.money($0, currency: progress.goal.currency, digits: progress.goal.currencyFractionDigits, locale: locale) } ?? NSLocalizedString("goal.needsReview", comment: "")
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("goal.supported").foregroundStyle(ArgusStyle.secondary)
            Text(verbatim: amount(progress.supportedMinor)).font(ArgusStyle.display(compact ? 23 : 34)).monospacedDigit().accessibilityIdentifier("goal.supported")
            if let fraction = progress.meterFraction {
                GeometryReader { geometry in
                    ZStack(alignment: .leading) {
                        Capsule().fill(ArgusStyle.line)
                        Capsule().fill(ArgusStyle.teal).frame(width: geometry.size.width * fraction)
                    }
                }.frame(height: 4).accessibilityHidden(true)
            }
            Text(LocalizedStringKey("goal.state." + progress.state)).foregroundStyle(progress.state == "needs_review" ? ArgusStyle.negative : ArgusStyle.secondary).accessibilityIdentifier("goal.state")
            if compact {
                HStack(spacing: 4) { Text("goal.of"); Text(verbatim: amount(String(progress.goal.targetMinor))) }
                    .font(ArgusStyle.body(12, relativeTo: .caption)).foregroundStyle(ArgusStyle.secondary)
                PlanValueRow(title: "goal.remaining", value: amount(progress.remainingMinor))
            }
        }
    }
}

struct FinancialGoalPresenter: View {
    @ObservedObject var model: FinancialGoalModel
    @ObservedObject var loop: FinancialLoopModel
    @Binding var destination: AppDestination
    let search: FinancialSearchModel?
    var body: some View {
        ZStack {
            if model.navigation != nil {
                NavigationStack {
                    FinancialGoalDetail(model: model, loop: loop) {
                        if let origin = model.navigation?.origin {
                            switch origin { case .home: destination = .home; case .plan, .planOverview: destination = .plan; case .search: destination = .search }
                        }
                        model.close(); Task { await search?.refresh() }
                    }
                }.tint(WelcomePalette.pine).foregroundStyle(WelcomePalette.ink)
                    .accessibilityElement(children: .contain).accessibilityIdentifier("goal.detail")
            } else { Color.clear.allowsHitTesting(false) }
        }
        .background { FinancialGoalSheets(model: model, loop: loop, search: search) }
    }
}

struct FinancialGoalSheets: View {
    @ObservedObject var model: FinancialGoalModel
    @ObservedObject var loop: FinancialLoopModel
    let search: FinancialSearchModel?
    var body: some View {
        Color.clear.frame(width: 0, height: 0)
            .sheet(item: $model.draft, onDismiss: { Task { await search?.refresh() } }) { draft in
                ConnectedPlanEditor(loop: loop, seed: .goal(draft))
            }
            .sheet(item: $model.action) { action in
                if let detail = model.detail {
                    switch action {
                    case .allocation: FinancialGoalAllocationView(model: model, loop: loop, detail: detail)
                    case .link: FinancialGoalLinkView(model: model, loop: loop)
                    }
                }
            }
    }
}

struct FinancialGoalDetail: View {
    @ObservedObject var model: FinancialGoalModel
    @ObservedObject var loop: FinancialLoopModel
    var nativeNavigation = false
    let close: () -> Void
    @State private var archiving = false
    @State private var releasing: FinancialGoalContribution?
    @Environment(\.locale) private var locale
    private var spanish: Bool { CuadraoCopy.isSpanish() }
    var body: some View {
        Group {
            if !nativeNavigation, let id = model.navigation?.activityID {
                ScrollView { FinancialActivityDetailView(loop: loop, activityID: id) { loop.correct($0) }.padding(24) }
            } else {
                ScrollViewReader { reader in
                    CuadraoPlanDetailPage(scroll: nativeNavigation ? model.scrollContext : nil) {
                        if let progress = model.detail {
                            heading(progress)
                            if progress.state == "reached" {
                                PlanLandscape(look: .coast).frame(height: 135)
                            }
                            if let scenario = ConnectedPlanScenario.goal(progress, now: Date()) {
                                CuadraoPlanWhatIf(scenario: scenario, spanish: spanish, apply: applyMonthly(progress), showsDisclosure: true)
                            }
                            ForEach(progress.reasons, id: \.self) { Text(LocalizedStringKey("goal.reason." + $0)).foregroundStyle(ArgusStyle.negative) }
                            projection(progress)
                            Button { model.action = .allocation } label: {
                                Label("goal.allocate", systemImage: "plus.circle").frame(minHeight: 44)
                            }.accessibilityIdentifier("goal.allocate")
                            if progress.goal.destinationAccountId != nil {
                                Button("goal.record") { model.record() }.frame(minHeight: 44).accessibilityIdentifier("goal.record")
                                Button("goal.link") { Task { await model.loadCandidates() } }.frame(minHeight: 48).accessibilityIdentifier("goal.link")
                            }
                            facts(progress)
                            Text("goal.contributions").font(CuadraoTypography.section)
                            if progress.contributions.isEmpty { Text("goal.noContributions").foregroundStyle(ArgusStyle.secondary) }
                            ForEach(progress.contributions) { claim in
                                VStack(alignment: .leading, spacing: 8) {
                                    Button { model.activity(claim.activityId, preservingScrollPosition: nativeNavigation) } label: {
                                        HStack {
                                            Text(claim.activity?.note ?? NSLocalizedString("loop.kind.transfer", comment: ""))
                                            Spacer(); Text(verbatim: money(claim.currentPersonalMinor, progress))
                                            Image(systemName: "chevron.right")
                                        }.frame(minHeight: 48).contentShape(Rectangle())
                                    }.buttonStyle(.plain).accessibilityIdentifier("goal.activity." + claim.activityId.uuidString)
                                    Text(LocalizedStringKey("goal.contribution." + claim.status)).foregroundStyle(ArgusStyle.secondary)
                                    if claim.counting {
                                        Button("goal.stopCounting") { releasing = claim }.frame(minHeight: 44).accessibilityIdentifier("goal.release." + claim.id.uuidString)
                                    }
                                }.id(claim.activityId).financialScrollAnchor(claim.activityId.uuidString)
                            }
                            if progress.goal.archived {
                                Text("goal.archived")
                                PlanPrimaryButton(title: NSLocalizedString("goal.restore", comment: "")) { Task { await model.archive(false) } }
                                    .accessibilityIdentifier("goal.restore")
                            }
                        }
                        if model.loading { ProgressView("goal.loading") }
                        if let error = model.errorKey {
                            Text(LocalizedStringKey(error)).accessibilityIdentifier("goal.error")
                            Button("accounts.retry") { Task { await model.refreshIfOpen() } }
                        }
                        if loop.pendingConfirmation != nil { PlanPendingView(loop: loop) }
                    }.disabled(model.saving).task(id: model.detail?.contributions.map(\.activityId)) {
                        guard !nativeNavigation, let anchor = model.navigation?.anchor else { return }
                        await Task.yield(); guard !Task.isCancelled else { return }; reader.scrollTo(anchor, anchor: .top)
                    }
                }
            }
        }
        .background(WelcomePalette.background)
        .navigationDestination(isPresented: activityPresented) {
            if let id = model.navigation?.activityID {
                ScrollView {
                    FinancialActivityDetailView(loop: loop, activityID: id) { loop.correct($0) }.padding(24)
                }
                .background(WelcomePalette.background)
                .navigationTitle("loop.activity.title").navigationBarTitleDisplayMode(.inline)
                .toolbar(.visible, for: .navigationBar)
            }
        }
        .navigationTitle("").navigationBarTitleDisplayMode(.inline).toolbar(.visible, for: .navigationBar)
        .toolbar {
            if !nativeNavigation {
                ToolbarItem(placement: .topBarLeading) {
                    if model.navigation?.activityID != nil {
                        Button { model.activity(nil); Task { await model.refreshIfOpen() } } label: { Label("goal.back", systemImage: "chevron.left") }
                            .accessibilityIdentifier("goal.activity.back")
                    } else {
                        Button(action: close) { Image(systemName: "chevron.left").frame(width: 44, height: 44) }
                            .accessibilityLabel("action.close").accessibilityIdentifier("goal.close")
                    }
                }
            }
            ToolbarItem(placement: .topBarTrailing) {
                if model.navigation?.activityID == nil, let progress = model.detail, !progress.goal.archived {
                    CuadraoPlanDetailOptions(spanish: spanish) {
                        Button { model.edit() } label: { Label("goal.edit", systemImage: "pencil") }.accessibilityIdentifier("goal.edit")
                        Button { archiving = true } label: { Label("goal.archive", systemImage: "archivebox") }.accessibilityIdentifier("goal.archive")
                    }.disabled(model.saving)
                } else if !nativeNavigation, model.navigation?.activityID != nil {
                    Button(action: close) { Image(systemName: "xmark").frame(width: 44, height: 44) }
                        .accessibilityLabel("action.close").accessibilityIdentifier("goal.close")
                }
            }
        }
        .confirmationDialog("goal.archive", isPresented: $archiving, titleVisibility: .visible) {
            Button("goal.archive") { Task { await model.archive(true) } }.accessibilityIdentifier("goal.archive.confirm")
            Button("accounts.cancel", role: .cancel) { }
        } message: { Text("goal.archive.disclosure") }
        .confirmationDialog("goal.stopCounting", isPresented: Binding(get: { releasing != nil }, set: { if !$0 { releasing = nil } }), titleVisibility: .visible) {
            if let claim = releasing { Button("goal.stopCounting") { Task { await model.release(claim) } }.accessibilityIdentifier("goal.release.confirm") }
            Button("accounts.cancel", role: .cancel) { releasing = nil }
        } message: { Text("goal.release.disclosure") }
    }
    private var activityPresented: Binding<Bool> {
        let captured = model.navigation
        return Binding(get: { nativeNavigation && model.navigation?.activityID != nil }, set: { presented in
            guard nativeNavigation, !presented, let captured, let activityID = captured.activityID,
                  let current = model.navigation, current.goalID == captured.goalID,
                  current.origin == captured.origin, current.activityID == activityID else { return }
            model.activity(nil)
            Task { await model.refreshIfOpen() }
        })
    }
    private func heading(_ progress: FinancialGoalProgress) -> some View {
        CuadraoPlanDetailHeading(display: .init(
            name: progress.goal.name, space: NSLocalizedString("context.personal", comment: ""), look: .coast,
            amount: summaryAmount(progress.supportedMinor, progress),
            annotation: NSLocalizedString("goal.supported", comment: ""), amountIdentifier: "goal.supported")) {
            if let fraction = progress.meterFraction {
                GeometryReader { geometry in
                    Capsule().fill(WelcomePalette.pine.opacity(0.1))
                        .overlay(alignment: .leading) {
                            Capsule().fill(WelcomePalette.pine).frame(width: geometry.size.width * fraction)
                        }
                }.frame(height: 4).accessibilityHidden(true)
            }
            Text(LocalizedStringKey("goal.state." + progress.state)).font(.subheadline)
                .foregroundStyle(progress.state == "needs_review" ? ArgusStyle.negative : ArgusStyle.secondary)
                .accessibilityIdentifier("goal.state")
        }
    }
    private func projection(_ progress: FinancialGoalProgress) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("goal.plan").font(CuadraoTypography.section)
            PlanValueRow(title: "goal.planned", value: summaryAmount(progress.plannedMinor, progress))
            PlanValueRow(title: "goal.projected", value: summaryAmount(progress.projectedMinor, progress))
            Text(PlanPresentation.dateLabel(progress.projectionEndDate, locale: locale)).font(.subheadline).foregroundStyle(.secondary)
            Text("goal.plan.disclosure").font(.caption).foregroundStyle(.secondary)
        }
    }
    private func facts(_ progress: FinancialGoalProgress) -> some View {
        CuadraoPlanDetailFacts(spanish: spanish) {
            PlanValueRow(title: "goal.target", value: summaryAmount(String(progress.goal.targetMinor), progress))
            PlanValueRow(title: "goal.assigned", value: summaryAmount(progress.assignedMinor, progress)).accessibilityIdentifier("goal.assigned")
            PlanValueRow(title: "goal.remaining", value: summaryAmount(progress.remainingMinor, progress))
            if progress.supportedMinor == nil { PlanValueRow(title: "goal.partial", value: summaryAmount(progress.independentlyBackedMinor, progress)) }
            if let targetDate = progress.goal.targetDate { PlanValueRow(title: "goal.targetDate", value: PlanPresentation.dateLabel(targetDate, locale: locale)) }
            if let destination = progress.goal.destinationAccountId { PlanValueRow(title: "goal.destination", value: loop.accountName(destination)) }
            ForEach(progress.pools) { pool in
                VStack(alignment: .leading, spacing: 10) {
                    Text(loop.accountName(pool.accountId)).font(CuadraoTypography.section)
                    PlanValueRow(title: "goal.backing", value: money(pool.backingMinor, progress))
                    PlanValueRow(title: "goal.shortfall", value: money(pool.shortfallMinor, progress)).accessibilityIdentifier("goal.pool.shortfall." + pool.accountId.uuidString)
                    Text(pool.affectedGoalNames.joined(separator: " · ")).foregroundStyle(.secondary)
                    if let asOf = pool.asOf { Text(AccountPresentation.date(asOf, zone: loop.plan.projection?.selection.timeZone ?? "UTC", locale: locale)).font(.caption) }
                }
            }
        }
    }
    private func applyMonthly(_ progress: FinancialGoalProgress) -> ((Double) -> Void)? {
        guard progress.goal.contributionPlan?.schedule.cadence == .monthly, !progress.goal.archived, loop.pendingConfirmation == nil else { return nil }
        return { monthly in
            let draft = FinancialGoalDraft(goal: progress.goal)
            draft.amount = ConnectedPlanScenario.draftAmount(monthly, digits: progress.goal.currencyFractionDigits, locale: locale)
            Task { await model.save(draft, locale: locale) }
        }
    }
    private func money(_ minor: String?, _ progress: FinancialGoalProgress) -> String {
        minor.map { PlanPresentation.money($0, currency: progress.goal.currency, digits: progress.goal.currencyFractionDigits, locale: locale) } ?? NSLocalizedString("accounts.unknown", comment: "")
    }
    private func summaryAmount(_ minor: String?, _ progress: FinancialGoalProgress) -> String {
        minor.map { money($0, progress) } ?? NSLocalizedString("goal.needsReview", comment: "")
    }
}

private struct FinancialGoalOcclusion: ViewModifier {
    @ObservedObject var model: FinancialGoalModel
    func body(content: Content) -> some View { content.accessibilityHidden(model.navigation != nil).allowsHitTesting(model.navigation == nil) }
}
extension View {
    @ViewBuilder func financialGoalBackground(_ model: FinancialGoalModel?) -> some View {
        if let model { modifier(FinancialGoalOcclusion(model: model)) } else { self }
    }
}
