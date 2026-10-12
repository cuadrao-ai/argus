import SwiftUI
import CuadraoBook

/// The Plan tab: the book's goals and budgets in the shared plan page, with a way to make one.
struct GuestPlanTab: View {
    @ObservedObject var model: GuestBookModel
    let scroll: CuadraoNavigationScroll
    let active: Bool
    @Binding var path: [UUID]
    @Binding var sheet: GuestSheet?
    @State private var archivedID: UUID?
    @Environment(\.locale) private var locale

    private var spanish: Bool { locale.language.languageCode?.identifier == "es" }
    private var hasAccounts: Bool { !model.book.activeAccounts.isEmpty }

    var body: some View {
        NavigationStack(path: $path) {
            CuadraoPlanPage(spanish: spanish) {
                CuadraoPlanHeader(spanish: spanish, createTitle: spanish ? "Crear plan" : "Create plan", canCreate: hasAccounts,
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
                                contribute: { sheet = .contribution(id) }, archive: { archive(id) })
            }
        }
        .overlay(alignment: .bottom) {
            if let archivedID, path.isEmpty, model.book.plan(archivedID)?.archived == true {
                GuestUndoToast(message: spanish ? "Plan archivado" : "Plan archived", spanish: spanish,
                               undo: { restore(archivedID) }, close: { self.archivedID = nil })
            }
        }
    }

    @ViewBuilder private var content: some View {
        if !hasAccounts {
            Text(spanish ? "Añade una cuenta con el botón + para crear tu primer plan." : "Add an account with the + button to make your first plan.")
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
        archivedID = id
    }

    private func restore(_ id: UUID) {
        _ = try? model.apply { try $0.settingPlanArchived(id, false) }
        archivedID = nil
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
    @State private var deletedID: UUID?
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
                        Button(action: edit) { Label(spanish ? "Editar plan" : "Edit plan", systemImage: "pencil") }
                            .accessibilityIdentifier("guest.plan.edit")
                        Button(action: archive) { Label(spanish ? "Archivar" : "Archive", systemImage: "archivebox") }
                            .accessibilityIdentifier("guest.plan.archive")
                    }
                }
            }
            .overlay(alignment: .bottom) {
                if let deletedID, plan.contributions.first(where: { $0.id == deletedID })?.deleted == true {
                    GuestUndoToast(message: spanish ? "Aporte eliminado" : "Contribution deleted", spanish: spanish,
                                   undo: { _ = try? model.apply { try $0.settingContributionDeleted(deletedID, in: id, false) }; self.deletedID = nil },
                                   close: { self.deletedID = nil })
                }
            }
        } else {
            ContentUnavailableView(spanish ? "Este plan ya no está aquí" : "This plan is no longer here", systemImage: "square.stack")
        }
    }

    private func money(_ minor: Int64, _ plan: BookPlan) -> String {
        GuestPlanPresentation.amount(minor, currency: plan.currency, digits: plan.digits, locale: locale)
    }

    private func heading(_ plan: BookPlan, book: DeviceBook) -> some View {
        let saved = book.goalProgress(plan.id)?.savedMinor ?? book.budgetStatus(plan.id, now: .now)?.spentMinor ?? 0
        return CuadraoPlanDetailHeading(display: CuadraoPlanDetailDisplay(
            name: plan.name, space: spanish ? "Este iPhone" : "This iPhone", look: GuestPlanPresentation.look(plan.look),
            amount: money(saved, plan),
            annotation: plan.kind == .goal ? (spanish ? "reunido" : "saved") : (spanish ? "gastado este mes" : "spent this month"),
            amountIdentifier: "guest.plan.amount")) {
            if book.goalProgress(plan.id)?.reached == true {
                Label(spanish ? "Lo hiciste. Un plan menos, más posibilidades." : "You did it. One plan down, more possibilities ahead.",
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
                    Text((spanish ? "Falta " : "Left ") + money(progress.remainingMinor, plan)).accessibilityIdentifier("guest.plan.remaining")
                }.font(.subheadline).foregroundStyle(.secondary)
            }
            RegistrationButton(title: spanish ? "Añadir aporte" : "Add contribution", action: contribute)
                .accessibilityIdentifier("guest.plan.contribute")
            if !plan.archived { GuestWhatIf(model: model, plan: plan, spanish: spanish) }
            let live = plan.contributions.filter { !$0.deleted }.sorted { $0.occurredAt > $1.occurredAt }
            VStack(alignment: .leading, spacing: 12) {
                Text(spanish ? "Aportes" : "Contributions").font(CuadraoTypography.section).accessibilityAddTraits(.isHeader)
                if live.isEmpty {
                    Text(spanish ? "Aún no hay aportes. Lo que apartes a mano aparece aquí." : "No contributions yet. What you set aside by hand shows up here.")
                        .font(.subheadline).foregroundStyle(.secondary).accessibilityIdentifier("guest.plan.noContributions")
                } else {
                    VStack(spacing: 0) {
                        ForEach(live) { item in
                            ConnectedSwipeRow(leading: [], trailing: [ConnectedSwipeAction(id: "guest.contribution.swipe.delete",
                                title: spanish ? "Eliminar" : "Delete", symbol: "trash", tint: .red) {
                                    if (try? model.apply { try $0.settingContributionDeleted(item.id, in: plan.id, true) }) != nil { deletedID = item.id }
                                }]) {
                                CuadraoFeedRow(title: item.note ?? (spanish ? "Aporte" : "Contribution"), detail: date(item),
                                               amount: "+" + money(item.amountMinor, plan), icon: "arrow.down.left")
                                    .accessibilityElement(children: .combine)
                                    .accessibilityIdentifier("guest.contribution.row." + item.id.uuidString)
                            }
                        }
                    }.connectedSwipeContainer()
                }
            }
            facts(plan) {
                line(spanish ? "Quiero reunir" : "I want to save", money(plan.targetMinor, plan))
                line(spanish ? "Aporte mensual previsto" : "Planned monthly contribution", money(plan.monthlyMinor ?? 0, plan))
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
                    Text(status.isOver ? (spanish ? "Te pasaste por " : "Over by ") + money(-status.remainingMinor, plan)
                         : (spanish ? "Quedan " : "Left ") + money(status.remainingMinor, plan))
                        .accessibilityIdentifier("guest.plan.remaining")
                }.font(.subheadline).foregroundStyle(status.isOver ? WelcomePalette.owedNegative : .secondary)
            }
            if !plan.archived { GuestWhatIf(model: model, plan: plan, spanish: spanish) }
            Text((spanish ? "Mes de " : "Month of ") + status.month.start.formatted(.dateTime.month(.wide).year().locale(locale))
                 + (spanish ? ", día \(status.elapsedDays) de \(status.totalDays)." : ", day \(status.elapsedDays) of \(status.totalDays)."))
                .font(.caption).foregroundStyle(.secondary).accessibilityIdentifier("guest.plan.month")
            facts(plan) {
                line(spanish ? "Quiero gastar hasta" : "I want to spend up to", money(plan.targetMinor, plan))
                line(spanish ? "Cuentas" : "Accounts", plan.accountScope.isEmpty ? (spanish ? "Todas en \(plan.currency)" : "All in \(plan.currency)")
                     : plan.accountScope.map { GuestMovementPresentation.accountTitle($0, in: book, spanish: spanish) }.joined(separator: ", "))
                line(spanish ? "Categorías" : "Categories", plan.categoryScope.isEmpty ? (spanish ? "Todas" : "All")
                     : plan.categoryScope.map { GuestMovementPresentation.categoryTitle($0, spanish: spanish) }.joined(separator: ", "))
            }
        }
    }

    private func facts<Content: View>(_ plan: BookPlan, @ViewBuilder content: @escaping () -> Content) -> some View {
        CuadraoPlanDetailFacts(spanish: spanish) {
            content()
            Text(spanish ? "El plan no mueve dinero. Cuenta solo lo que registras en este iPhone." : "The plan doesn't move money. It counts only what you record on this iPhone.")
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
                ContentUnavailableView(spanish ? "Nada archivado" : "Nothing archived", systemImage: "archivebox",
                    description: Text(spanish ? "Tus planes pueden descansar aquí. Siempre podrás retomarlos." : "Plans can rest here. You can always pick them back up."))
                    .listRowSeparator(.hidden)
            }
            ForEach(model.book.archivedPlans) { plan in
                HStack {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(plan.name)
                        Text(GuestPlanPresentation.kindTitle(plan.kind, spanish: spanish)).font(.caption).foregroundStyle(.secondary)
                    }
                    Spacer()
                    Button(spanish ? "Retomar" : "Restore") { _ = try? model.apply { try $0.settingPlanArchived(plan.id, false) } }
                        .buttonStyle(.bordered).frame(minHeight: 44).accessibilityIdentifier("guest.plan.restore." + plan.id.uuidString)
                }
            }
        }.navigationTitle(spanish ? "Archivados" : "Archived").navigationBarTitleDisplayMode(.inline)
            .toolbar(.visible, for: .navigationBar).safeAreaPadding(.bottom, 90)
            .accessibilityIdentifier("guest.plan.archived")
    }
}
