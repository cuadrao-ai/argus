import SwiftUI
import ArgusSession

struct FinancialPlanDestination: View {
    @EnvironmentObject private var auth: ProfileAuthModel
    let showProfile: () -> Void
    var nativeNavigation = false
    var audience: Binding<Bool>? = nil
    var bottomSpace: CGFloat = 90
    var body: some View {
        if auth.state == .authenticated, let loop = auth.financialLoop {
            FinancialPlanView(model: loop.plan, loop: loop, nativeNavigation: nativeNavigation, search: auth.financialSearch, audience: audience, bottomSpace: bottomSpace)
        } else {
            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    PersonalContext()
                    Text("plan.overview.empty").font(ArgusStyle.display())
                    Text("accounts.gate.body").foregroundStyle(ArgusStyle.secondary)
                    Button("auth.signIn", action: showProfile).buttonStyle(PillButtonStyle())
                }.padding(24)
            }
        }
    }
}

struct FinancialPlanView: View {
    @EnvironmentObject private var auth: ProfileAuthModel
    @ObservedObject var model: FinancialPlanModel
    @ObservedObject var loop: FinancialLoopModel
    var nativeNavigation = false
    var search: FinancialSearchModel? = nil
    var audience: Binding<Bool>? = nil
    var bottomSpace: CGFloat = 90
    @State private var selectingAccounts = false
    @State private var expanded = false
    @State private var creating = false
    @Environment(\.locale) private var locale
    private var spanish: Bool { locale.language.languageCode?.identifier == "es" }

    private var canCreate: Bool { model.projection != nil && loop.pendingConfirmation == nil && !model.saving }

    var body: some View {
        CuadraoPlanPage(spanish: spanish, audience: audience, bottomSpace: bottomSpace) {
            CuadraoPlanHeader(spanish: spanish, createTitle: spanish ? "Crear plan" : "Create plan", canCreate: canCreate) { creating = true }
        } content: {
            if loop.pendingConfirmation != nil { PlanPendingView(loop: loop) }
            if model.loading && model.projection == nil {
                VStack(alignment: .leading, spacing: 24) {
                    CuadraoSkeleton(layout: .card, identifier: "plan.loading")
                    CuadraoSkeleton(layout: .rows(3), identifier: "plan.loading.rows")
                }
            }
            if let error = model.errorKey {
                CuadraoRetryState(message: LocalizedStringKey(error), identifier: "plan.error",
                                  retryIdentifier: "plan.retry") { Task { await model.refresh() } }
            }
            if let projection = model.projection { overview(projection) }
        } footer: {
            EmptyView()
        }
        .financialPlanDestinations(loop: loop, search: search, host: .plan, enabled: nativeNavigation)
        .task { if model.projection == nil { await model.refresh() } }
        .refreshable { await loop.refresh() }
        .sheet(isPresented: $creating) { ConnectedPlanEditor(loop: loop, seed: .create(kind: nil)) }
        .sheet(isPresented: $selectingAccounts) {
            if let projection = model.projection { FinancialPlanSelectionView(model: model, loop: loop, projection: projection) }
        }
    }

    private func overview(_ projection: FinancialPlanProjection) -> some View {
        VStack(alignment: .leading, spacing: 24) {
            FinancialPlanForecast(projection: projection, primaryCurrency: auth.profile?.currency, chooseAccounts: { selectingAccounts = true },
                canChooseAccounts: loop.pendingConfirmation == nil && !model.saving, bottomSpace: bottomSpace) { currency in
                forecastControls(projection, currency: currency)
            }
            .id(auth.profile?.id)
            .id(ObjectIdentifier(model))
            FinancialPlanCards(model: model, loop: loop, projection: projection,
                create: { creating = true }, bottomSpace: bottomSpace)
            expected(projection)
        }
    }

    private func forecastControls(_ projection: FinancialPlanProjection, currency: FinancialForecastCurrency?) -> some View {
        VStack(alignment: .leading, spacing: 16) {
            DatePicker("plan.until.label", selection: Binding(get: { PlanPresentation.date(projection.endDate) },
                set: { date in Task { await model.refresh(until: PlanPresentation.day(date)) } }),
                in: PlanPresentation.date(projection.startDate)...PlanPresentation.date(projection.startDate).addingTimeInterval(366 * 86400),
                displayedComponents: .date)
                .environment(\.timeZone, TimeZone(secondsFromGMT: 0)!)
                .font(CuadraoTypography.supporting).accessibilityIdentifier("plan.until")
            Button { selectingAccounts = true } label: {
                VStack(alignment: .leading, spacing: 6) {
                    HStack { Text("plan.includedAccounts"); Spacer(); Image(systemName: "chevron.right").font(.caption2) }
                    if let currency {
                        Text(includedNames(projection, currency: currency)).font(CuadraoTypography.caption).foregroundStyle(.secondary)
                    }
                }.font(CuadraoTypography.supporting).frame(minHeight: 48).contentShape(Rectangle())
            }.buttonStyle(.plain).accessibilityIdentifier("plan.accounts").disabled(loop.pendingConfirmation != nil || model.saving)
            Text(projection.selection.timeZone).font(CuadraoTypography.caption).foregroundStyle(.secondary)
        }
    }

    private func expected(_ projection: FinancialPlanProjection) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text("plan.expected").font(CuadraoTypography.section)
                Spacer()
                CuadraoSectionAddButton(title: NSLocalizedString("plan.add.title", comment: "")) { model.create() }
                    .accessibilityIdentifier("plan.add").disabled(!canCreate)
            }
            if !projection.hasExpectations {
                Text("plan.empty").font(CuadraoTypography.supporting).foregroundStyle(.secondary)
            }
            ForEach(Array(projection.occurrences.prefix(expanded ? projection.occurrences.count : 6))) { occurrence in
                Button {
                    if let current = model.projection?.occurrences.first(where: { $0.id == occurrence.id }) {
                        Task { await model.open(current) }
                    }
                } label: { FinancialOccurrenceRow(occurrence: occurrence) }
                    .buttonStyle(.plain).accessibilityIdentifier("plan.occurrence." + occurrence.id)
            }
            if projection.occurrences.count > 6 {
                Button(expanded ? "plan.showLess" : "plan.showMore") { expanded.toggle() }.frame(minHeight: 44)
                    .accessibilityIdentifier("plan.showMore")
            }
            if !projection.expectations.isEmpty {
                DisclosureGroup("plan.manageExpectations") {
                    ForEach(projection.expectations) { expectation in
                        Button {
                            if let current = model.projection?.expectations.first(where: { $0.id == expectation.id }) { model.edit(current) }
                        } label: {
                            HStack { Text(expectation.title); Spacer(); Image(systemName: "chevron.right") }.frame(minHeight: 48).contentShape(Rectangle())
                        }.buttonStyle(.plain).disabled(loop.pendingConfirmation != nil)
                            .accessibilityIdentifier("plan.expectation." + expectation.id.uuidString)
                    }
                }.padding(.top, 16)
            }
        }
    }
    private func includedNames(_ projection: FinancialPlanProjection, currency: FinancialForecastCurrency) -> String {
        let names = projection.accounts.filter { currency.accountIds.contains($0.id) }.map {
            $0.nickname ?? NSLocalizedString("accounts.type." + $0.type, comment: "")
        }.joined(separator: " · ")
        return names.isEmpty ? (spanish ? "Ninguna cuenta seleccionada" : "No accounts selected") : names
    }
}

struct FinancialForecastSummary: View {
    let currency: FinancialForecastCurrency
    /// Home and Plan both render a summary; distinct prefixes keep each total addressable.
    var identifier = "plan.projected."
    @Environment(\.locale) private var locale
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("plan.projectedBalance").font(ArgusStyle.body(14, relativeTo: .subheadline)).foregroundStyle(ArgusStyle.secondary)
            if let ending = currency.endingMinor {
                Text(verbatim: PlanPresentation.money(ending, currency: currency.currency, digits: currency.currencyFractionDigits, locale: locale))
                    .font(ArgusStyle.display(32)).monospacedDigit().fixedSize(horizontal: false, vertical: true)
                    .accessibilityIdentifier(identifier + currency.currency)
            } else {
                Text("accounts.unknown").font(ArgusStyle.display(28))
                Text(verbatim: currency.currency).font(ArgusStyle.body(14))
                Text("plan.unknown").font(ArgusStyle.body(12, relativeTo: .caption)).foregroundStyle(ArgusStyle.secondary)
            }
            if let asOf = currency.asOf {
                Text(verbatim: NSLocalizedString("plan.asOf", comment: "") + " " +
                     AccountPresentation.date(asOf, zone: TimeZone.current.identifier, locale: locale))
                    .font(ArgusStyle.body(11, relativeTo: .caption)).foregroundStyle(ArgusStyle.secondary)
            }
        }
    }
}

struct FinancialOccurrenceRow: View {
    let occurrence: FinancialPlanOccurrence
    @Environment(\.locale) private var locale
    @Environment(\.dynamicTypeSize) private var size
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .firstTextBaseline) {
                Text(occurrence.title).font(CuadraoTypography.body)
                Spacer(minLength: 8)
                if !size.isAccessibilitySize { amount }
            }
            if size.isAccessibilitySize { amount }
            Text(verbatim: PlanPresentation.dateLabel(occurrence.dueDate, locale: locale))
                .font(CuadraoTypography.caption).foregroundStyle(.secondary)
            Text(LocalizedStringKey("plan.status." + occurrence.status.rawValue))
                .font(CuadraoTypography.caption).foregroundStyle(.secondary)
            if occurrence.overdue { Text("plan.overdue").font(CuadraoTypography.caption) }
            if let reason = occurrence.exclusionReason {
                Text(LocalizedStringKey("plan.exclusion." + reason)).font(CuadraoTypography.caption).foregroundStyle(.secondary)
            }
        }.padding(.vertical, 16).frame(maxWidth: .infinity, alignment: .leading).contentShape(Rectangle())
            .overlay(alignment: .bottom) { Rectangle().fill(ArgusStyle.line).frame(height: 1) }.accessibilityElement(children: .combine)
    }
    private var amount: some View {
        Text(verbatim: (occurrence.kind == .income ? "+" : "−") + occurrence.currency + " " + AccountPresentation.amount(occurrence.amount, locale: locale))
            .font(CuadraoTypography.rowAmount)
    }
}

struct PlanValueRow: View {
    let title: LocalizedStringKey
    let value: String
    var body: some View {
        ViewThatFits(in: .horizontal) {
            HStack { Text(title); Spacer(minLength: 12); Text(verbatim: value).monospacedDigit() }
            VStack(alignment: .leading, spacing: 5) { Text(title); Text(verbatim: value).monospacedDigit() }
        }.font(ArgusStyle.body(13, relativeTo: .subheadline))
    }
}

struct PlanPendingView: View {
    @ObservedObject var loop: FinancialLoopModel
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(LocalizedStringKey(loop.pendingTitle)).font(ArgusStyle.body(15))
            Text("loop.pending.body").font(ArgusStyle.body(12, relativeTo: .caption)).foregroundStyle(ArgusStyle.secondary)
            Button("loop.pending.retry") { Task { await loop.retryPending() } }
                .buttonStyle(PillButtonStyle()).disabled(loop.recovering).accessibilityIdentifier("loop.pending.retry")
            if let error = loop.recoveryErrorKey { Text(LocalizedStringKey(error)).foregroundStyle(ArgusStyle.secondary) }
        }.padding(16).overlay(RoundedRectangle(cornerRadius: 14).stroke(ArgusStyle.line))
    }
}
