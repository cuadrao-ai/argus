import SwiftUI
import ArgusSession

struct FinancialBudgetList: View {
    @ObservedObject var plan: FinancialPlanModel
    @ObservedObject var model: FinancialBudgetModel
    let origin: FinancialBudgetNavigation.Origin
    private var items: [FinancialBudgetProgress] { (plan.projection?.budgets ?? []).filter { !$0.budget.archived } }
    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            Text("plan.budgets").font(ArgusStyle.display(23))
            if items.isEmpty { Text("budget.empty").foregroundStyle(ArgusStyle.secondary) }
            ForEach(items) { progress in
                Button { Task { await model.open(progress.id, origin: origin) } } label: {
                    VStack(alignment: .leading, spacing: 12) {
                        HStack { Text(verbatim: progress.budget.name); Spacer(); Image(systemName: "chevron.right").font(.system(size: 12)) }
                        FinancialBudgetSummary(progress: progress, compact: true)
                    }.padding(.vertical, 14).contentShape(Rectangle())
                }.buttonStyle(.plain).accessibilityIdentifier("budget.row." + origin.rawValue + "." + progress.id.uuidString)
            }
        }
    }
}

struct FinancialBudgetSummary: View {
    let progress: FinancialBudgetProgress
    var compact = false
    @Environment(\.locale) private var locale
    private func amount(_ value: String) -> String {
        PlanPresentation.money(value, currency: progress.budget.currency, digits: progress.budget.currencyFractionDigits, locale: locale)
    }
    var body: some View {
        VStack(alignment: .leading, spacing: compact ? 8 : 16) {
            Text(verbatim: amount(progress.spentMinor)).font(ArgusStyle.display(compact ? 23 : 34)).monospacedDigit()
                .accessibilityIdentifier("budget.spent")
            HStack(spacing: 4) {
                Text("budget.of"); Text(verbatim: amount(String(progress.budget.limitMinor)))
            }.font(ArgusStyle.body(13, relativeTo: .subheadline)).foregroundStyle(ArgusStyle.secondary)
            GeometryReader { geometry in
                ZStack(alignment: .leading) {
                    Capsule().fill(ArgusStyle.line)
                    Capsule().fill(ArgusStyle.teal).frame(width: geometry.size.width * progress.meterFraction)
                }
            }.frame(height: 4).accessibilityHidden(true)
            HStack(spacing: 4) {
                Text(verbatim: amount(progress.isOverBudget ? progress.overBudgetMinor : progress.remainingMinor))
                Text(progress.isOverBudget ? "budget.over" : "budget.remaining")
            }.font(ArgusStyle.body(13, relativeTo: .subheadline)).foregroundStyle(progress.isOverBudget ? ArgusStyle.negative : ArgusStyle.secondary)
                .accessibilityElement(children: .combine).accessibilityIdentifier("budget.remaining")
        }
    }
}

struct FinancialBudgetPresenter: View {
    @ObservedObject var model: FinancialBudgetModel
    @ObservedObject var loop: FinancialLoopModel
    @Binding var destination: AppDestination
    let search: FinancialSearchModel?
    var body: some View {
        ZStack {
            if model.navigation != nil {
                NavigationStack {
                    FinancialBudgetDetailView(model: model, loop: loop) {
                        if let origin = model.navigation?.origin {
                            switch origin { case .home: destination = .home; case .plan, .planOverview: destination = .plan; case .search: destination = .search }
                        }
                        model.close()
                        Task { await search?.refresh() }
                    }
                }.tint(WelcomePalette.pine).foregroundStyle(WelcomePalette.ink)
                    .accessibilityElement(children: .contain).accessibilityIdentifier("budget.detail")
            } else { Color.clear.allowsHitTesting(false) }
        }
        .background { FinancialBudgetSheets(model: model, loop: loop, search: search) }
    }
}

struct FinancialBudgetSheets: View {
    @ObservedObject var model: FinancialBudgetModel
    @ObservedObject var loop: FinancialLoopModel
    let search: FinancialSearchModel?
    var body: some View {
        Color.clear.frame(width: 0, height: 0)
            .sheet(item: $model.draft, onDismiss: { Task { await search?.refresh() } }) { draft in
                ConnectedPlanEditor(loop: loop, seed: .budget(draft))
            }
    }
}

struct FinancialBudgetDetailView: View {
    @ObservedObject var model: FinancialBudgetModel
    @ObservedObject var loop: FinancialLoopModel
    var nativeNavigation = false
    let close: () -> Void
    @State private var removing = false
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
                            if progress.contributors.isEmpty {
                                VStack(alignment: .leading, spacing: 12) {
                                    PlanLandscape(look: .sunshine).frame(height: 100)
                                    Text(CuadraoCopy.text("copy.cuadraoPlanDetail.82ea69d62d", spanish: spanish))
                                        .font(.subheadline).foregroundStyle(.secondary)
                                }
                            }
                            if let scenario = ConnectedPlanScenario.budget(progress, now: Date()) {
                                CuadraoPlanWhatIf(scenario: scenario, spanish: spanish, apply: applyLimit(progress), showsDisclosure: true)
                            }
                            Text("budget.recordedOnly").font(.caption).foregroundStyle(.secondary)
                            CuadraoPlanDetailFacts(spanish: spanish) {
                                HStack(spacing: 4) {
                                    Text("budget.of"); Text(verbatim: amount(String(progress.budget.limitMinor), progress))
                                }
                                scope(progress)
                            }
                            Text("budget.contributors").font(CuadraoTypography.section)
                            if progress.contributors.isEmpty { Text("budget.noActivity").foregroundStyle(ArgusStyle.secondary) }
                            ForEach(progress.contributors, id: \.activityId) { item in
                                Button { model.activity(item.activityId, preservingScrollPosition: nativeNavigation) } label: { contributor(item) }
                                    .buttonStyle(.plain).id(item.activityId).accessibilityIdentifier("budget.activity." + item.activityId.uuidString)
                                    .financialScrollAnchor(item.activityId.uuidString)
                            }
                            if progress.budget.archived {
                                Text("budget.archived").foregroundStyle(ArgusStyle.secondary)
                                PlanPrimaryButton(title: NSLocalizedString("budget.restore", comment: "")) { Task { await model.archive(false) } }
                                    .accessibilityIdentifier("budget.restore")
                            }
                        }
                        if model.loading { ProgressView("accounts.loading") }
                        if let error = model.errorKey {
                            Text(LocalizedStringKey(error)).accessibilityIdentifier("budget.error")
                            Button("accounts.retry") { Task { await model.refreshIfOpen() } }.frame(minHeight: 44)
                        }
                        if loop.pendingConfirmation != nil { PlanPendingView(loop: loop) }
                    }.disabled(model.saving).task(id: model.detail?.contributors.map(\.activityId)) {
                        guard !nativeNavigation, let anchor = model.navigation?.anchor,
                              model.detail?.contributors.contains(where: { $0.activityId == anchor }) == true else { return }
                        await Task.yield()
                        guard !Task.isCancelled else { return }
                        reader.scrollTo(anchor, anchor: .top)
                    }
                }
            }
        }.background(WelcomePalette.background)
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
                        Button { model.activity(nil); Task { await model.refreshIfOpen() } } label: { Label("budget.back", systemImage: "chevron.left") }
                            .accessibilityIdentifier("budget.activity.back")
                    } else {
                        Button(action: close) { Image(systemName: "chevron.left").frame(width: 44, height: 44) }
                            .accessibilityLabel("action.close").accessibilityIdentifier("budget.close")
                    }
                }
            }
            ToolbarItem(placement: .topBarTrailing) {
                if model.navigation?.activityID == nil, let progress = model.detail, !progress.budget.archived {
                    CuadraoPlanDetailOptions(spanish: spanish) {
                        Button { Task { await model.edit() } } label: { Label("budget.edit", systemImage: "pencil") }.accessibilityIdentifier("budget.edit")
                        Button(role: .destructive) { removing = true } label: { Label("budget.remove", systemImage: "archivebox") }.accessibilityIdentifier("budget.remove")
                    }.disabled(model.saving)
                } else if !nativeNavigation, model.navigation?.activityID != nil {
                    Button(action: close) { Image(systemName: "xmark").frame(width: 44, height: 44) }
                        .accessibilityLabel("action.close").accessibilityIdentifier("budget.close")
                }
            }
        }
        .confirmationDialog("budget.remove.confirm", isPresented: $removing, titleVisibility: .visible) {
            Button("budget.remove", role: .destructive) { Task { await model.archive(true) } }.accessibilityIdentifier("budget.remove.confirm")
            Button("accounts.cancel", role: .cancel) { }
        } message: { Text("budget.remove.body") }
    }
    private var activityPresented: Binding<Bool> {
        let captured = model.navigation
        return Binding(get: { nativeNavigation && model.navigation?.activityID != nil }, set: { presented in
            guard nativeNavigation, !presented, let captured, let activityID = captured.activityID,
                  let current = model.navigation, current.budgetID == captured.budgetID,
                  current.origin == captured.origin, current.activityID == activityID else { return }
            model.activity(nil)
            Task { await model.refreshIfOpen() }
        })
    }
    private func heading(_ progress: FinancialBudgetProgress) -> some View {
        CuadraoPlanDetailHeading(display: .init(
            name: progress.budget.name, space: NSLocalizedString("context.personal", comment: ""), look: .sunshine,
            amount: amount(progress.spentMinor, progress), annotation: NSLocalizedString("loop.home.netSpending", comment: ""),
            amountIdentifier: "budget.spent")) {
            Text(verbatim: month(progress.budget.month)).font(.caption).foregroundStyle(.secondary)
            GeometryReader { geometry in
                Capsule().fill(WelcomePalette.sunshine.opacity(0.1))
                    .overlay(alignment: .leading) {
                        Capsule().fill(WelcomePalette.sunshine).frame(width: geometry.size.width * progress.meterFraction)
                    }
            }.frame(height: 4).accessibilityHidden(true)
            HStack(spacing: 4) {
                Text(verbatim: amount(progress.isOverBudget ? progress.overBudgetMinor : progress.remainingMinor, progress))
                Text(progress.isOverBudget ? "budget.over" : "budget.remaining")
            }.font(.subheadline).foregroundStyle(progress.isOverBudget ? ArgusStyle.negative : ArgusStyle.secondary)
                .accessibilityElement(children: .combine).accessibilityIdentifier("budget.remaining")
        }
    }
    private func applyLimit(_ progress: FinancialBudgetProgress) -> ((Double) -> Void)? {
        guard !progress.budget.archived, loop.pendingConfirmation == nil else { return nil }
        return { limit in
            let draft = FinancialBudgetDraft(budget: progress.budget)
            draft.limit = ConnectedPlanScenario.draftAmount(limit, digits: progress.budget.currencyFractionDigits, locale: locale)
            Task { await model.save(draft, locale: locale) }
        }
    }
    private func amount(_ value: String, _ progress: FinancialBudgetProgress) -> String {
        PlanPresentation.money(value, currency: progress.budget.currency, digits: progress.budget.currencyFractionDigits, locale: locale)
    }
    private func month(_ value: String) -> String {
        let formatter = DateFormatter(); formatter.locale = locale; formatter.timeZone = TimeZone(secondsFromGMT: 0)
        formatter.setLocalizedDateFormatFromTemplate("MMMM yyyy")
        return formatter.string(from: PlanPresentation.date(value + "-01"))
    }
    private func scope(_ progress: FinancialBudgetProgress) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(progress.budget.accountIds.map(loop.accountName).joined(separator: " · "))
            Text((progress.budget.categoryIds.map { NSLocalizedString("loop.category." + $0, comment: "") } +
                (progress.budget.includeUncategorized ? [NSLocalizedString("budget.uncategorized", comment: "")] : [])).joined(separator: " · "))
            Text(verbatim: progress.period.timeZone)
            Text(verbatim: AccountPresentation.date(progress.period.startAt, zone: progress.period.timeZone, locale: locale) + " → " +
                AccountPresentation.date(progress.period.endAtExclusive, zone: progress.period.timeZone, locale: locale))
            Text("budget.interval.hint")
        }.font(ArgusStyle.body(12, relativeTo: .caption)).foregroundStyle(ArgusStyle.secondary).accessibilityIdentifier("budget.scope")
    }
    private func contributor(_ item: FinancialActivityDetail) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(item.note ?? NSLocalizedString("loop.kind." + item.kind.rawValue, comment: ""))
                Spacer(minLength: 12)
                Text(verbatim: (item.kind == .refund || item.kind == .paymentReversal ? "−" : "") + item.currency + " " + AccountPresentation.amount(item.countedSpendingMinor.map { AccountPresentation.decimal($0, digits: item.currencyFractionDigits) } ?? item.amount, locale: locale)).monospacedDigit().fixedSize(horizontal: true, vertical: false).layoutPriority(1)
            }
            Text((item.legs.first.map { loop.accountName($0.accountId) } ?? "") + " · " + AccountPresentation.date(item.occurredAt, zone: item.timeZone, locale: locale))
                .font(ArgusStyle.body(11, relativeTo: .caption)).foregroundStyle(ArgusStyle.secondary)
        }.font(ArgusStyle.body(14)).padding(.vertical, 16).frame(maxWidth: .infinity, alignment: .leading)
            .contentShape(Rectangle()).overlay(alignment: .bottom) { Rectangle().fill(ArgusStyle.line).frame(height: 1) }
    }
}


private struct FinancialBudgetOcclusion: ViewModifier {
    @ObservedObject var model: FinancialBudgetModel
    func body(content: Content) -> some View {
        content.accessibilityHidden(model.navigation != nil).allowsHitTesting(model.navigation == nil)
    }
}

extension View {
    @ViewBuilder func financialBudgetBackground(_ model: FinancialBudgetModel?) -> some View {
        if let model { modifier(FinancialBudgetOcclusion(model: model)) } else { self }
    }
}
