import SwiftUI
import CuadraoBook

/// The Plan tab: the book's goals and budgets in the shared plan page, with a way to make one.
struct GuestPlanTab: View {
    @ObservedObject var model: GuestBookModel
    let scroll: CuadraoNavigationScroll
    let active: Bool
    @Binding var path: [UUID]
    @Binding var sheet: GuestSheet?
    let offerUndo: (GuestUndoOffer) -> Void
    @Environment(\.locale) private var locale

    private var spanish: Bool { CuadraoCopy.isSpanish() }
    private var hasAccounts: Bool { !model.book.activeAccounts.isEmpty }

    var body: some View {
        NavigationStack(path: $path) {
            CuadraoPlanPage(spanish: spanish) {
                CuadraoPlanHeader(spanish: spanish, createTitle: CuadraoCopy.text("copy.cuadraoPlanCanvas.2131013203", spanish: spanish), canCreate: hasAccounts,
                                  createIdentifier: "plan-create") { sheet = .plan(.create) }
            } content: {
                content
            } footer: {
                EmptyView()
            }
            .accessibilityIdentifier("guest.plan")
            .toolbar(.hidden, for: .navigationBar)
            .modifier(CuadraoNavigationScrollObserver(scroll: scroll, enabled: active && path.isEmpty && sheet == nil))
            .navigationDestination(for: UUID.self) { id in
                GuestPlanDetail(model: model, id: id, spanish: spanish, edit: { sheet = .plan(.edit(id)) },
                                contribute: { sheet = .contribution(id) }, archive: { archive(id) }, offerUndo: offerUndo)
            }
        }
    }

    @ViewBuilder private var content: some View {
        if !hasAccounts {
            Text(CuadraoCopy.text("copy.guestPlans.4677ecbf35", spanish: spanish))
                .font(.subheadline).foregroundStyle(.secondary).accessibilityIdentifier("guest.plan.needsAccount")
        }
        CuadraoPlanCollection(spanish: spanish, isEmpty: model.book.activePlans.isEmpty, canCreate: hasAccounts,
                              create: { sheet = .plan(.create) }) {
            CuadraoOrderedCollection(items: model.book.activePlans, spanish: spanish,
                identifier: { "guest.plan.row." + $0.id.uuidString },
                open: { path.append($0.id) }, edit: { sheet = .plan(.edit($0.id)) }, archive: { archive($0.id) },
                reorder: { ids in _ = try? model.apply { try $0.reorderingActivePlans(ids) } }) { plan in
                    GuestPlanCard(plan: plan, book: model.book, spanish: spanish)
                }
        } archives: {
            if !model.book.archivedPlans.isEmpty {
                CuadraoPlanArchiveLink(spanish: spanish) { GuestArchivedPlans(model: model, spanish: spanish) }
            }
        }
    }

    private func archive(_ id: UUID) {
        guard (try? model.apply { try $0.settingPlanArchived(id, true) }) != nil else { return }
        path = []
        offerUndo(GuestUndoOffer(text: CuadraoCopy.text("copy.guestPlans.674b256524", spanish: spanish), identifier: "guest.undo",
                                 restore: { _ = try? model.apply { try $0.settingPlanArchived(id, false) } }))
    }
}

struct GuestPlanCard: View {
    let plan: BookPlan
    let book: DeviceBook
    let spanish: Bool
    @Environment(\.locale) private var locale

    var body: some View {
        CuadraoPlanCard(display: GuestPlanPresentation.card(plan, in: book, spanish: spanish, locale: locale))
    }
}

/// One plan in full. A goal lists its contributions and takes new ones; a budget shows the month against its limit.
struct GuestPlanDetail: View {
    @ObservedObject var model: GuestBookModel
    let id: UUID
    let spanish: Bool
    let edit: () -> Void
    let contribute: () -> Void
    let archive: () -> Void
    let offerUndo: (GuestUndoOffer) -> Void
    @Environment(\.locale) private var locale

    var body: some View {
        if let plan = model.book.plan(id) {
            let book = model.book
            ScrollView {
                VStack(alignment: .leading, spacing: 22) {
                    heading(plan, book: book)
                    switch plan.kind {
                    case .goal: goal(plan, book: book)
                    case .budget: budget(plan, book: book)
                    }
                }.padding(24).padding(.bottom, 90)
            }
            .accessibilityIdentifier("guest.plan.detail")
            .background(WelcomePalette.background)
            .navigationTitle("").navigationBarTitleDisplayMode(.inline).toolbar(.visible, for: .navigationBar)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    CuadraoPlanDetailOptions(spanish: spanish) {
                        Button(action: edit) { Label(CuadraoCopy.text("copy.cuadraoPlanDetail.507c662ea3", spanish: spanish), systemImage: "pencil") }
                            .accessibilityIdentifier("guest.plan.edit")
                        Button(action: archive) { Label(CuadraoCopy.text("copy.connectedCuadraoHome.0960027352", spanish: spanish), systemImage: "archivebox") }
                            .accessibilityIdentifier("guest.plan.archive")
                    }
                }
            }
        } else {
            ContentUnavailableView(CuadraoCopy.text("copy.cuadraoPlanDetail.037615818c", spanish: spanish), systemImage: "square.stack")
        }
    }

    private func money(_ minor: Int64, _ plan: BookPlan) -> String {
        GuestPlanPresentation.amount(minor, currency: plan.currency, digits: plan.digits, locale: locale)
    }

    private func heading(_ plan: BookPlan, book: DeviceBook) -> some View {
        let saved = book.goalProgress(plan.id)?.savedMinor ?? book.budgetStatus(plan.id, now: .now)?.spentMinor ?? 0
        return CuadraoPlanDetailHeading(display: CuadraoPlanDetailDisplay(
            name: plan.name, space: CuadraoCopy.text("copy.guestAccountSheet.736ea2040f", spanish: spanish), look: GuestPlanPresentation.look(plan.look),
            amount: money(saved, plan),
            annotation: plan.kind == .goal ? (CuadraoCopy.text("copy.guestPlans.6f6cc5d5e6", spanish: spanish)) : (CuadraoCopy.text("copy.guestPlans.fc50bb6573", spanish: spanish)),
            amountIdentifier: "guest.plan.amount")) {
            if book.goalProgress(plan.id)?.reached == true {
                Label(CuadraoCopy.text("copy.cuadraoPlanDetail.59d3e81cdd", spanish: spanish),
                      systemImage: "checkmark.seal").font(.subheadline).foregroundStyle(GuestPlanPresentation.look(plan.look).color)
            }
        }
    }

    @ViewBuilder private func goal(_ plan: BookPlan, book: DeviceBook) -> some View {
        if let progress = book.goalProgress(plan.id) {
            VStack(alignment: .leading, spacing: 8) {
                ProgressView(value: NSDecimalNumber(decimal: progress.fraction).doubleValue)
                    .tint(GuestPlanPresentation.look(plan.look).color).accessibilityHidden(true)
                HStack {
                    Text(GuestPlanPresentation.percent(progress.fraction)).accessibilityIdentifier("guest.plan.percent")
                    Spacer()
                    Text((CuadraoCopy.text("copy.guestPlans.fdd65d7580", spanish: spanish)) + money(progress.remainingMinor, plan)).accessibilityIdentifier("guest.plan.remaining")
                }.font(.subheadline).foregroundStyle(.secondary)
            }
            RegistrationButton(title: CuadraoCopy.text("copy.guestPlanSheet.f243e37ce7", spanish: spanish), action: contribute)
                .accessibilityIdentifier("guest.plan.contribute")
            if !plan.archived { GuestWhatIf(model: model, plan: plan, spanish: spanish) }
            let live = plan.contributions.filter { !$0.deleted }.sorted { $0.occurredAt > $1.occurredAt }
            VStack(alignment: .leading, spacing: 12) {
                Text(CuadraoCopy.text("copy.cuadraoGroupDetail.4400cb3469", spanish: spanish)).font(CuadraoTypography.section).accessibilityAddTraits(.isHeader)
                if live.isEmpty {
                    Text(CuadraoCopy.text("copy.guestPlans.536371fb9e", spanish: spanish))
                        .font(.subheadline).foregroundStyle(.secondary).accessibilityIdentifier("guest.plan.noContributions")
                } else {
                    VStack(spacing: 0) {
                        ForEach(live) { item in
                            ConnectedSwipeRow(leading: [], trailing: [ConnectedSwipeAction(id: "guest.contribution.swipe.delete",
                                title: CuadraoCopy.text("copy.savedReceiptCopy.534547cf82", spanish: spanish), symbol: "trash", tint: .red) {
                                    guard (try? model.apply { try $0.settingContributionDeleted(item.id, in: plan.id, true) }) != nil else { return }
                                    offerUndo(GuestUndoOffer(text: CuadraoCopy.text("copy.guestPlans.b6a17abc5d", spanish: spanish), identifier: "guest.undo",
                                        restore: { _ = try? model.apply { try $0.settingContributionDeleted(item.id, in: plan.id, false) } }))
                                }]) {
                                CuadraoFeedRow(title: item.note ?? (CuadraoCopy.text("copy.guestPlans.5a1aad5aaa", spanish: spanish)), detail: date(item),
                                               amount: "+" + money(item.amountMinor, plan), icon: "arrow.down.left")
                                    .accessibilityElement(children: .combine)
                                    .accessibilityIdentifier("guest.contribution.row." + item.id.uuidString)
                            }
                        }
                    }.connectedSwipeContainer()
                }
            }
            facts(plan) {
                line(CuadraoCopy.text("copy.guestPlans.e778771fc8", spanish: spanish), money(plan.targetMinor, plan))
                line(CuadraoCopy.text("copy.guestPlanSheet.ba8a20d76b", spanish: spanish), money(plan.monthlyMinor ?? 0, plan))
            }
        }
    }

    @ViewBuilder private func budget(_ plan: BookPlan, book: DeviceBook) -> some View {
        if let status = book.budgetStatus(plan.id, now: .now) {
            VStack(alignment: .leading, spacing: 8) {
                ProgressView(value: NSDecimalNumber(decimal: status.fraction).doubleValue)
                    .tint(status.isOver ? WelcomePalette.owedNegative : GuestPlanPresentation.look(plan.look).color).accessibilityHidden(true)
                HStack {
                    Text(GuestPlanPresentation.percent(status.fraction)).accessibilityIdentifier("guest.plan.percent")
                    Spacer()
                    Text(status.isOver ? (CuadraoCopy.text("copy.guestPlans.7354d3f567", spanish: spanish)) + money(-status.remainingMinor, plan)
                         : (CuadraoCopy.text("copy.guestPlans.f4b2d561f4", spanish: spanish)) + money(status.remainingMinor, plan))
                        .accessibilityIdentifier("guest.plan.remaining")
                }.font(.subheadline).foregroundStyle(status.isOver ? WelcomePalette.owedNegative : .secondary)
            }
            if !plan.archived { GuestWhatIf(model: model, plan: plan, spanish: spanish) }
            Text((CuadraoCopy.text("copy.guestPlans.8307faabc7", spanish: spanish)) + status.month.start.formatted(.dateTime.month(.wide).year().locale(locale))
                 + (CuadraoCopy.text("copy.guestPlans.9d05466f46", spanish: spanish, String(describing: status.elapsedDays), String(describing: status.totalDays))))
                .font(.caption).foregroundStyle(.secondary).accessibilityIdentifier("guest.plan.month")
            facts(plan) {
                line(CuadraoCopy.text("copy.guestPlans.d1b440c179", spanish: spanish), money(plan.targetMinor, plan))
                line(CuadraoCopy.text("copy.connectedCuadraoHome.8cce5d02a3", spanish: spanish), plan.accountScope.isEmpty ? (CuadraoCopy.text("copy.guestPlanSheet.5e336ce4f5", spanish: spanish, String(describing: plan.currency)))
                     : plan.accountScope.map { GuestMovementPresentation.accountTitle($0, in: book, spanish: spanish) }.joined(separator: ", "))
                line(CuadraoCopy.text("copy.cuadraoSpendingHighlights.c530befaf7", spanish: spanish), plan.categoryScope.isEmpty ? (CuadraoCopy.text("copy.cuadraoSearchCanvas.22417a3c9d", spanish: spanish))
                     : plan.categoryScope.map { GuestMovementPresentation.categoryTitle($0, spanish: spanish) }.joined(separator: ", "))
            }
        }
    }

    private func facts<Content: View>(_ plan: BookPlan, @ViewBuilder content: @escaping () -> Content) -> some View {
        CuadraoPlanDetailFacts(spanish: spanish) {
            content()
            Text(CuadraoCopy.text("copy.guestPlans.f6219a6065", spanish: spanish))
                .font(.caption).foregroundStyle(.secondary)
        }
    }

    private func line(_ label: String, _ value: String) -> some View {
        LabeledContent(label) { Text(value).multilineTextAlignment(.trailing) }
    }

    private func date(_ contribution: Contribution) -> String {
        let formatter = DateFormatter()
        formatter.locale = locale
        formatter.timeZone = TimeZone(identifier: contribution.timeZone) ?? .current
        formatter.dateStyle = .medium
        formatter.timeStyle = .none
        return formatter.string(from: contribution.occurredAt)
    }
}

struct GuestArchivedPlans: View {
    @ObservedObject var model: GuestBookModel
    let spanish: Bool

    var body: some View {
        List {
            if model.book.archivedPlans.isEmpty {
                ContentUnavailableView(CuadraoCopy.text("copy.cuadraoGroupCollection.e07523e83a", spanish: spanish), systemImage: "archivebox",
                    description: Text(CuadraoCopy.text("copy.cuadraoPlanCanvas.ebcdf81c28", spanish: spanish)))
                    .listRowSeparator(.hidden)
            }
            ForEach(model.book.archivedPlans) { plan in
                HStack {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(plan.name)
                        Text(GuestPlanPresentation.kindTitle(plan.kind, spanish: spanish)).font(.caption).foregroundStyle(.secondary)
                    }
                    Spacer()
                    Button(CuadraoCopy.text("copy.cuadraoGroupCollection.1ae3bf9797", spanish: spanish)) { _ = try? model.apply { try $0.settingPlanArchived(plan.id, false) } }
                        .buttonStyle(.bordered).frame(minHeight: 44).accessibilityIdentifier("guest.plan.restore." + plan.id.uuidString)
                }
            }
        }.navigationTitle(CuadraoCopy.text("copy.cuadraoSpacesSheet.e95aacbabf", spanish: spanish)).navigationBarTitleDisplayMode(.inline)
            .toolbar(.visible, for: .navigationBar).safeAreaPadding(.bottom, 90)
            .accessibilityIdentifier("guest.plan.archived")
    }
}
