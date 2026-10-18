import SwiftUI
import PDFKit
import MapKit
import CoreLocation

struct CuadraoReceiptReview: View {
    let id: UUID
    let workspace: ReceiptWorkspace
    let spanish: Bool
    var body: some View {
        if let draft = workspace.receipts.receipt(id) {
            ReceiptEditor(initial: draft, workspace: workspace, spanish: spanish)
        } else { ContentUnavailableView(CuadraoCopy.text("copy.cuadraoReceiptReview.06109900aa", spanish: spanish), systemImage: "receipt") }
    }
}

private struct ReceiptEditor: View {
    let workspace: ReceiptWorkspace
    let spanish: Bool
    @State private var chatFocus: CanvasChatFocus?
    @State private var draft: ReceiptDraft
    @State private var error = ""
    @State private var amountErrors: [String: String] = [:]
    @State private var showSource = false
    @State private var editingLine: ReceiptLine?
    @Environment(\.dismiss) private var dismiss
    @State private var discard = false
    @State private var details = false
    @State private var charges = false
    @State private var location = ReceiptLocationRequest()
    private var es: Bool { spanish }
    private var group: PlanGroup? { draft.groupID.flatMap(workspace.groups.group) }
    private var posted: PlanSharedExpense? { group?.expenses.first { $0.id == draft.id && $0.receiptID == draft.id } }
    private var shares: [UUID: Int] { posted?.shares ?? ((try? draft.shares(roster: group?.activeMembers.map(\.id) ?? [])) ?? [:]) }
    private var compatibleAccounts: [CanvasAccount] {
        workspace.accounts.accounts.filter { !$0.archived && $0.currency == draft.currency && $0.spaceID == CanvasSpace.personalID && [.cash, .checking, .savings, .card].contains($0.kind) }
    }
    init(initial: ReceiptDraft, workspace: ReceiptWorkspace, spanish: Bool) {
        self.workspace = workspace; self.spanish = spanish; _draft = State(initialValue: initial)
    }
    var body: some View {
        Form {
            Section {
                VStack(alignment: .leading, spacing: 10) {
                    Label(draft.prepared ? (CuadraoCopy.text("copy.cuadraoReceiptReview.7da5c41021", spanish: es)) : (CuadraoCopy.text("copy.cuadraoReceiptReview.184bee8c07", spanish: es)), systemImage: draft.prepared ? "checkmark.circle" : "checkmark.seal")
                        .font(CuadraoTypography.caption).foregroundStyle(.secondary).accessibilityIdentifier("receipt-status")
                    if !workspace.postingCapability.allowsPosting {
                        Text(CuadraoCopy.text("copy.cuadraoReceiptReview.3fe028b7e6", spanish: es))
                            .font(CuadraoTypography.caption).foregroundStyle(.secondary).accessibilityIdentifier("receipt-local-draft-notice")
                    }
                    if draft.example { Text(CuadraoCopy.text("copy.cuadraoReceiptReview.3095a4654a", spanish: es)).font(CuadraoTypography.caption).foregroundStyle(WelcomePalette.pine) }
                    Text(posted?.title ?? (draft.merchant.isEmpty ? (CuadraoCopy.text("copy.cuadraoReceiptReview.7986a24789", spanish: es)) : draft.merchant)).font(CuadraoTypography.feature)
                    if draft.lines.isEmpty && posted == nil {
                        Text(CuadraoCopy.text("copy.cuadraoReceiptReview.fa3d07b423", spanish: es)).font(CuadraoTypography.secondaryAmount)
                            .accessibilityIdentifier("receipt-total")
                    } else if let currency = draft.currency {
                        HStack(alignment: .firstTextBaseline) {
                            Text(currency).font(.caption).foregroundStyle(.secondary)
                            Text(money(posted?.cents ?? draft.total)).font(CuadraoTypography.amount)
                                .lineLimit(1).minimumScaleFactor(0.65)
                        }.accessibilityIdentifier("receipt-total")
                    }
                    Text((CanvasExpenseCategory(rawValue: draft.category) ?? .other).title(es) + " · " + draft.date.formatted(.dateTime.day().month(.abbreviated).year().locale(Locale(identifier: CuadraoCopy.text("copy.cuadraoReceiptReview.68ab9be0ef", spanish: es)))))
                        .font(CuadraoTypography.supporting).foregroundStyle(.secondary)
                }.padding(.vertical, 8)
                Button { showSource = true } label: {
                    Label(CuadraoCopy.text("copy.cuadraoReceiptReview.802300b119", spanish: es), systemImage: "doc.text.image").frame(minHeight: 44)
                }.accessibilityIdentifier("receipt-source")
                if !draft.prepared {
                    Button { askCuadrao() } label: {
                        Label(CuadraoCopy.text("copy.cuadraoReceiptReview.b44a9adeb4", spanish: es), systemImage: "bubble").frame(minHeight: 44)
                    }.accessibilityIdentifier("receipt-open-chat")
                }
                if draft.prepared {
                    DisclosureGroup(CuadraoCopy.text("copy.cuadraoReceiptReview.f72bbcda64", spanish: es), isExpanded: $details) {
                        TextField(CuadraoCopy.text("copy.cuadraoReceiptReview.e47fa08736", spanish: es), text: $draft.merchant).accessibilityIdentifier("receipt-merchant")
                        DatePicker(CuadraoCopy.text("copy.cuadraoReceiptReview.9e3d3b41ed", spanish: es), selection: $draft.date, displayedComponents: .date)
                        Picker(CuadraoCopy.text("copy.cuadraoReceiptReview.67c7ee0c0f", spanish: es), selection: $draft.category) {
                            ForEach(CanvasExpenseCategory.allCases) { Text($0.title(es)).tag($0.rawValue) }
                        }
                        if let currency = draft.currency { Label(currency, systemImage: "lock").font(.caption).foregroundStyle(.secondary) }
                    }
                }
            }
            if draft.currency == nil {
                Section {
                    Menu {
                        ForEach(PlanCurrency.supported, id: \.self) { currency in
                            Button(currency) { chooseCurrency(currency) }
                        }
                    } label: {
                        Label(CuadraoCopy.text("copy.cuadraoReceiptReview.15994beaf7", spanish: es), systemImage: "chevron.up.chevron.down")
                            .frame(maxWidth: .infinity, alignment: .leading).contentShape(Rectangle())
                    }.accessibilityIdentifier("receipt-currency")
                    Text(CuadraoCopy.text("copy.cuadraoReceiptReview.81ce59316e", spanish: es))
                        .font(CuadraoTypography.caption).foregroundStyle(.secondary)
                }
            }
            if let currency = draft.currency {
                Section(CuadraoCopy.text("copy.cuadraoReceiptReview.e916404c71", spanish: es)) {
                    if draft.lines.isEmpty {
                        Text(CuadraoCopy.text("copy.cuadraoReceiptReview.3c46e49dfa", spanish: es)).font(.subheadline).foregroundStyle(.secondary)
                    }
                    ForEach(draft.lines) { line in
                        Button { if draft.prepared { editingLine = line } } label: {
                            HStack {
                                VStack(alignment: .leading, spacing: 4) {
                                    Text(line.name).foregroundStyle(WelcomePalette.ink)
                                    Text("\(line.quantity) × \(money(line.unitCents))").font(.caption).foregroundStyle(.secondary)
                                }
                                Spacer()
                                Text(money(line.cents)).font(CuadraoTypography.rowAmount).foregroundStyle(WelcomePalette.ink)
                                if draft.prepared { Image(systemName: "chevron.right").font(.caption2) }
                            }.frame(minHeight: 44).contentShape(Rectangle())
                        }.buttonStyle(.plain).accessibilityIdentifier("receipt-line-\(draft.lines.firstIndex(where: { $0.id == line.id }) ?? 0)")
                    }
                    if draft.prepared {
                        Button(CuadraoCopy.text("copy.cuadraoReceiptReview.d6957c0370", spanish: es), systemImage: "plus") { editingLine = ReceiptLine(name: "", unitCents: 0) }
                            .disabled(draft.lines.count >= 100).accessibilityIdentifier("receipt-add-item")
                    }
                    totalRow(CuadraoCopy.text("copy.cuadraoReceiptReview.fe5a09b661", spanish: es), draft.subtotal)
                    DisclosureGroup(CuadraoCopy.text("copy.cuadraoReceiptReview.a1c35a35d7", spanish: es), isExpanded: $charges) {
                        if draft.prepared {
                            centInput(CuadraoCopy.text("copy.cuadraoReceiptReview.546d6e7903", spanish: es), key: \.taxCents, id: "receipt-tax")
                            centInput(CuadraoCopy.text("copy.cuadraoReceiptReview.9c0b03a055", spanish: es), key: \.serviceCents, id: "receipt-service")
                            centInput(CuadraoCopy.text("copy.cuadraoReceiptReview.3714a680c2", spanish: es), key: \.addedTipCents, id: "receipt-tip")
                        } else {
                            totalRow(CuadraoCopy.text("copy.cuadraoReceiptReview.fbd02a8e49", spanish: es), draft.taxCents)
                            totalRow(CuadraoCopy.text("copy.cuadraoReceiptReview.5c04d9f4ba", spanish: es), draft.serviceCents)
                            totalRow(CuadraoCopy.text("copy.cuadraoReceiptReview.3714a680c2", spanish: es), draft.addedTipCents)
                        }
                        Text(CuadraoCopy.text("copy.cuadraoReceiptReview.79a2d49f7f", spanish: es)).font(.caption).foregroundStyle(.secondary)
                    }
                    totalRow(CuadraoCopy.text("copy.cuadraoReceiptReview.c132bd855a", spanish: es), draft.receiptTotal)
                    if draft.addedTipCents > 0 { totalRow(CuadraoCopy.text("copy.cuadraoReceiptReview.8ee98cc070", spanish: es), draft.total) }
                }
                if workspace.postingCapability.allowsPosting {
                    if draft.prepared { destination }
                    else if case .personal(let accountID) = draft.destination, let accountID, let account = workspace.accounts.account(accountID) {
                        Section(CuadraoCopy.text("copy.cuadraoReceiptReview.6c69ae1c5d", spanish: es)) {
                            Label(account.displayName(es) + " · " + currency, systemImage: "creditcard")
                        }
                    }
                    if let group { splitSection(group) }
                }
            }
            Section {
                if let pin = draft.captureLocation {
                    Map(initialPosition: .region(MKCoordinateRegion(center: .init(latitude: pin.latitude, longitude: pin.longitude), span: .init(latitudeDelta: 0.01, longitudeDelta: 0.01)))) {
                        Marker(CuadraoCopy.text("copy.cuadraoReceiptReview.6429a77a4f", spanish: es), coordinate: .init(latitude: pin.latitude, longitude: pin.longitude))
                    }.frame(height: 150).clipShape(RoundedRectangle(cornerRadius: 16))
                    Text((CuadraoCopy.text("copy.cuadraoReceiptReview.0272f0dfe9", spanish: es)) + pin.recordedAt.formatted(date: .abbreviated, time: .shortened)).font(.caption).foregroundStyle(.secondary)
                    if draft.prepared { Button(CuadraoCopy.text("copy.cuadraoReceiptReview.9312991da9", spanish: es), role: .destructive) { draft.captureLocation = nil } }
                } else if draft.prepared && location.isAvailable {
                    Button { location.request() } label: { Label(CuadraoCopy.text("copy.cuadraoReceiptReview.60f6cffd1a", spanish: es), systemImage: "location").frame(minHeight: 44) }
                    Text(CuadraoCopy.text("copy.cuadraoReceiptReview.8f157f4321", spanish: es)).font(.caption).foregroundStyle(.secondary)
                }
                if location.unavailable { Text(CuadraoCopy.text("copy.cuadraoReceiptReview.f02d689e6d", spanish: es)).font(.caption).foregroundStyle(.secondary) }
            }
            if workspace.postingCapability.allowsPosting || !error.isEmpty {
                Section {
                    if !error.isEmpty { Text(error).foregroundStyle(.red).font(.subheadline).accessibilityIdentifier("receipt-error") }
                    if workspace.postingCapability.allowsPosting {
                        if draft.prepared {
                            Button { confirm() } label: {
                                Text(CuadraoCopy.text("copy.cuadraoReceiptReview.88b4c99896", spanish: es)).font(CuadraoTypography.action).frame(maxWidth: .infinity, minHeight: 44)
                            }.disabled(!valid).accessibilityIdentifier("receipt-confirm")
                            Text(CuadraoCopy.text("copy.cuadraoReceiptReview.b916587004", spanish: es)).font(.caption).foregroundStyle(.secondary)
                        } else {
                            Label(CuadraoCopy.text("copy.cuadraoReceiptReview.fb6e8c6a34", spanish: es), systemImage: "checkmark.seal.fill").foregroundStyle(WelcomePalette.pine).accessibilityIdentifier("receipt-confirmed")
                        }
                    }
                }
            }
        }.cuadraoFormKeyboard().scrollContentBackground(.hidden).background(WelcomePalette.background)
            .navigationTitle(CuadraoCopy.text("copy.cuadraoReceiptReview.e331bed748", spanish: es)).navigationBarTitleDisplayMode(.inline)
            .sheet(isPresented: $showSource) { ReceiptSourceViewer(draft: draft, store: workspace.receipts, spanish: es) }
            .sheet(item: $editingLine) { line in
                if let currency = draft.currency {
                    ReceiptLineEditor(line: line, currency: currency, spanish: es, existing: draft.lines.contains { $0.id == line.id }) { revised in
                        if let revised {
                            if let index = draft.lines.firstIndex(where: { $0.id == revised.id }) { draft.lines[index] = revised }
                            else { draft.lines.append(revised) }
                        } else { draft.lines.removeAll { $0.id == line.id } }
                    }
                }
            }
            .contextualCuadrao(focus: $chatFocus, spanish: es)
            .onChange(of: draft) { old, value in
                guard old.prepared, value.prepared, value != workspace.receipts.receipt(value.id) else { return }
                do { try workspace.receipts.update(value); error = "" } catch { show(error) }
            }
            .onChange(of: location.value) { _, value in if let value, draft.prepared { draft.captureLocation = value } }
            .confirmationDialog(CuadraoCopy.text("copy.cuadraoReceiptReview.c2a46dd89a", spanish: es), isPresented: $discard, titleVisibility: .visible) {
                Button(CuadraoCopy.text("copy.cuadraoReceiptReview.d3251d7d5f", spanish: es), role: .destructive) {
                    do {
                        try workspace.receipts.discard(draft.id, groups: workspace.groups)
                        workspace.chat.removeReceipt(draft.id)
                        dismiss()
                    } catch { show(error) }
                }
            }
            .toolbar {
                if draft.prepared {
                    ToolbarItem(placement: .topBarTrailing) {
                        Menu {
                            Button(CuadraoCopy.text("copy.cuadraoReceiptReview.b44a9adeb4", spanish: es), systemImage: "bubble") { askCuadrao() }
                                .accessibilityIdentifier("receipt-open-chat")
                            Button(CuadraoCopy.text("copy.cuadraoReceiptReview.d3251d7d5f", spanish: es), systemImage: "trash", role: .destructive) { discard = true }
                        } label: { Image(systemName: "ellipsis").frame(width: 44, height: 44) }
                            .accessibilityLabel(CuadraoCopy.text("copy.cuadraoReceiptReview.9739b2c2fe", spanish: es))
                    }
                }
            }
    }
    private func askCuadrao() {
        chatFocus = .receipt(id: draft.id, title: draft.merchant.isEmpty ? (CuadraoCopy.text("copy.cuadraoReceiptReview.7986a24789", spanish: es)) : draft.merchant)
    }
    private var destination: some View {
        Section(CuadraoCopy.text("copy.cuadraoReceiptReview.2225bac54a", spanish: es)) {
            Picker(CuadraoCopy.text("copy.cuadraoReceiptReview.145f020a43", spanish: es), selection: Binding(get: { draft.groupID?.uuidString ?? "personal" }, set: chooseDestination)) {
                Text(CuadraoCopy.text("copy.cuadraoReceiptReview.e49bf008a8", spanish: es)).tag("personal")
                ForEach(workspace.groups.groups.filter { !$0.archived && $0.kind == .trip && $0.currency == draft.currency }) { Text($0.name).tag($0.id.uuidString) }
            }.accessibilityIdentifier("receipt-destination")
            if case .personal(let accountID) = draft.destination {
                Picker(CuadraoCopy.text("copy.cuadraoReceiptReview.f9d32ca2e5", spanish: es), selection: Binding(get: { accountID }, set: { draft.destination = .personal(accountID: $0) })) {
                    Text(CuadraoCopy.text("copy.cuadraoReceiptReview.83157a5f5e", spanish: es)).tag(UUID?.none)
                    ForEach(compatibleAccounts) { Text($0.displayName(es)).tag(Optional($0.id)) }
                }.accessibilityIdentifier("receipt-account")
                if compatibleAccounts.isEmpty { Text(CuadraoCopy.text("copy.cuadraoReceiptReview.d54a853f63", spanish: es)).font(.caption).foregroundStyle(.secondary) }
            }
            if let currency = draft.currency { Text(currency).font(.caption).foregroundStyle(.secondary) }
        }
    }
    private func chooseCurrency(_ currency: String) {
        do {
            try workspace.receipts.setCurrency(currency, for: draft.id)
            if let saved = workspace.receipts.receipt(draft.id) { draft = saved }
            error = ""
        } catch { show(error) }
    }
    private func chooseDestination(_ value: String) {
        guard draft.currency != nil else { return }
        if let id = UUID(uuidString: value), let group = workspace.groups.group(id) {
            draft.destination = .group(id); draft.payer = group.me; draft.participants = Set(group.activeMembers.map(\.id))
            for index in draft.lines.indices { draft.lines[index].members = [] }
        } else { draft.destination = .personal(accountID: nil) }
    }
    private func splitSection(_ group: PlanGroup) -> some View {
        Section(CuadraoCopy.text("copy.cuadraoReceiptReview.78780cf3f5", spanish: es)) {
            if draft.prepared {
                Picker(CuadraoCopy.text("copy.cuadraoReceiptReview.76f42fdad3", spanish: es), selection: $draft.payer) {
                    ForEach(group.activeMembers) { Text($0.name).tag(Optional($0.id)) }
                }.accessibilityIdentifier("receipt-payer")
                Picker(CuadraoCopy.text("copy.cuadraoReceiptReview.23401e7418", spanish: es), selection: $draft.split) {
                    Text(CuadraoCopy.text("copy.cuadraoReceiptReview.12cc303b3a", spanish: es)).tag(ReceiptSplit.equal)
                    Text(CuadraoCopy.text("copy.cuadraoReceiptReview.736b395352", spanish: es)).tag(ReceiptSplit.items)
                }.pickerStyle(.segmented).accessibilityIdentifier("receipt-split")
                ForEach(Array(group.activeMembers.enumerated()), id: \.element.id) { index, member in
                    Button {
                        if draft.participants.contains(member.id) {
                            draft.participants.remove(member.id)
                            for i in draft.lines.indices { draft.lines[i].members.remove(member.id) }
                        } else { draft.participants.insert(member.id) }
                    } label: {
                        HStack {
                            Image(systemName: draft.participants.contains(member.id) ? "checkmark.circle.fill" : "circle")
                            PlanMemberAvatar(member: member, index: index)
                            Text(member.name); Spacer()
                            Text(money(shares[member.id] ?? 0)).font(CuadraoTypography.rowAmount)
                        }.frame(minHeight: 44).contentShape(Rectangle())
                    }.buttonStyle(.plain).accessibilityIdentifier("receipt-member-\(index)")
                        .accessibilityLabel(member.name)
                        .accessibilityValue((draft.participants.contains(member.id) ? (CuadraoCopy.text("copy.cuadraoReceiptReview.125cdfabe6", spanish: es)) : (CuadraoCopy.text("copy.cuadraoReceiptReview.c8b76cad45", spanish: es))) + ", " + money(shares[member.id] ?? 0))
                        .accessibilityAddTraits(draft.participants.contains(member.id) ? .isSelected : [])
                }
                if draft.split == .items {
                    ForEach(draft.lines) { line in
                        VStack(alignment: .leading, spacing: 8) {
                            Text(line.name).font(CuadraoTypography.supporting)
                            ViewThatFits(in: .horizontal) {
                                assignmentButtons(line, group: group, vertical: false)
                                assignmentButtons(line, group: group, vertical: true)
                            }
                        }.padding(.vertical, 4)
                    }
                    Text(draft.unassigned == 0 ? (CuadraoCopy.text("copy.cuadraoReceiptReview.f097481f5b", spanish: es)) : (CuadraoCopy.text("copy.cuadraoReceiptReview.cc3ad80f59", spanish: es, String(describing: draft.unassigned))))
                        .font(.caption).foregroundStyle(draft.unassigned == 0 ? WelcomePalette.pine : .secondary).accessibilityIdentifier("receipt-unassigned")
                    Text(CuadraoCopy.text("copy.cuadraoReceiptReview.7c71ed7778", spanish: es)).font(.caption).foregroundStyle(.secondary)
                }
            } else {
                if let payer = posted?.payer, let member = group.members.first(where: { $0.id == payer }) {
                    Text((CuadraoCopy.text("copy.cuadraoReceiptReview.49162f30e2", spanish: es)) + member.name).font(CuadraoTypography.supporting)
                }
                ForEach(group.members.filter { shares[$0.id] != nil }) { member in
                    HStack { Text(member.name); Spacer(); Text(money(shares[member.id] ?? 0)).font(CuadraoTypography.rowAmount) }
                }
            }
            if !shares.isEmpty {
                totalRow(CuadraoCopy.text("copy.cuadraoReceiptReview.15732a4703", spanish: es), shares[group.me] ?? 0)
                let payer = posted?.payer ?? draft.payer
                let net = (payer == group.me ? (posted?.cents ?? draft.total) : 0) - (shares[group.me] ?? 0)
                if let currency = draft.currency { CuadraoOwedRow(cents: net, currency: currency, spanish: es) }
            }
        }
    }
    private func assignmentButtons(_ line: ReceiptLine, group: PlanGroup, vertical: Bool) -> some View {
        let layout = vertical ? AnyLayout(VStackLayout(alignment: .leading, spacing: 4)) : AnyLayout(HStackLayout(spacing: 6))
        return layout {
            ForEach(group.activeMembers.filter { draft.participants.contains($0.id) }) { member in
                Button {
                    guard let index = draft.lines.firstIndex(where: { $0.id == line.id }) else { return }
                    if draft.lines[index].members.contains(member.id) { draft.lines[index].members.remove(member.id) }
                    else { draft.lines[index].members.insert(member.id) }
                } label: {
                    HStack(spacing: 6) {
                        Image(systemName: line.members.contains(member.id) ? "checkmark.circle.fill" : "circle")
                        Text(member.name)
                    }
                        .font(.subheadline).fixedSize(horizontal: !vertical, vertical: true)
                        .padding(.horizontal, 8).frame(minHeight: 44)
                        .background(line.members.contains(member.id) ? WelcomePalette.sage : .clear, in: Capsule()).contentShape(Rectangle())
                }.buttonStyle(.plain).accessibilityIdentifier("receipt-assign-\(draft.lines.firstIndex(where: { $0.id == line.id }) ?? 0)-\(group.activeMembers.firstIndex(where: { $0.id == member.id }) ?? 0)")
                    .accessibilityLabel("\(line.name), \(member.name)")
                    .accessibilityValue(line.members.contains(member.id) ? (CuadraoCopy.text("copy.cuadraoReceiptReview.6f2cd50a9a", spanish: es)) : (CuadraoCopy.text("copy.cuadraoReceiptReview.45896e9456", spanish: es)))
                    .accessibilityAddTraits(line.members.contains(member.id) ? .isSelected : [])
            }
        }
    }
    private var valid: Bool {
        guard !amountErrors.values.contains(where: { !$0.isEmpty }), (try? draft.validate()) != nil else { return false }
        if let group { return (try? draft.shares(roster: group.activeMembers.map(\.id))) != nil && draft.payer != nil }
        if case .personal(let id) = draft.destination { return compatibleAccounts.contains { $0.id == id } }
        return false
    }
    private func confirm() {
        do {
            try workspace.receipts.update(draft)
            try workspace.receipts.confirm(draft.id, groups: workspace.groups, accounts: workspace.accounts)
            if let saved = workspace.receipts.receipt(draft.id) { draft = saved }
        } catch { show(error) }
    }
    private func show(_ failure: Error) {
        error = (failure as? ReceiptError)?.message(es) ?? (CuadraoCopy.text("copy.cuadraoReceiptReview.9330f3ccfa", spanish: es))
    }
    private func money(_ cents: Int) -> String {
        guard let currency = draft.currency else { return "" }
        return CanvasMoney.format(Decimal(cents) / 100, currency: currency)
    }
    private func totalRow(_ title: String, _ cents: Int) -> some View {
        HStack { Text(title).font(CuadraoTypography.supporting); Spacer(); Text(money(cents)).font(CuadraoTypography.rowAmount) }
    }
    private func centInput(_ title: String, key: WritableKeyPath<ReceiptDraft, Int>, id: String) -> some View {
        VStack(alignment: .leading) {
            HStack {
                Text(title).font(CuadraoTypography.supporting)
                if let currency = draft.currency {
                CanvasMoneyValueInput(value: Binding(get: { Double(draft[keyPath: key]) / 100 }, set: { draft[keyPath: key] = Int(($0 * 100).rounded()) }),
                                      error: $amountErrors.message(for: id), currency: currency, spanish: es,
                                      identifier: id, title: title, size: .row, alignment: .right).frame(minHeight: 44)
                }
            }
            if let error = amountErrors[id], !error.isEmpty { Text(error).font(.caption).foregroundStyle(.red) }
        }
    }
}
