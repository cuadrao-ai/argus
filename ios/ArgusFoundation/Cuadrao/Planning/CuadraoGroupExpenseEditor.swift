import SwiftUI
import PhotosUI

struct CuadraoGroupExpenseEditor: View {
    @Environment(\.receiptWorkspace) private var receiptWorkspace
    @State private var receiptRoute: ReceiptRoute?
    @State private var initialized = false
    let store: CuadraoGroupPreview
    let groupID: UUID
    var initial: PlanSharedExpense?
    let spanish: Bool
    @State private var title = ""
    @State private var amount = 0.0
    @State private var amountErrors: [String: String] = [:]
    @State private var payer: UUID?
    @State private var selected: Set<UUID> = []
    @State private var custom = false
    @State private var exactShares: [UUID: Double] = [:]
    @State private var photo: PhotosPickerItem?
    @State private var receipt: Data?
    @State private var photoError = false
    @State private var discard = false
    @Environment(\.dismiss) private var dismiss
    private var group: PlanGroup? { store.group(groupID) }
    private var cents: Int { amount.isFinite && (0...CanvasMoney.maximumValue).contains(amount) ? Int((amount * 100).rounded()) : 0 }
    private var hasAmountError: Bool {
        amountErrors.contains { key, error in
            !error.isEmpty && (key == "amount" || (custom && selected.contains { $0.uuidString == key }))
        }
    }
    private var validDraft: Bool { !hasAmountError && (receipt != nil || !title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty) && amount.isFinite && (0...CanvasMoney.maximumValue).contains(amount) }
    private var valid: Bool { !hasAmountError && !title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && cents > 0 && payer != nil }
    private func shares(_ group: PlanGroup) -> [UUID: Int] {
        if group.kind == .saving { return payer.map { [$0: cents] } ?? [:] }
        if custom {
            return Dictionary(uniqueKeysWithValues: participants(group).filter { selected.contains($0.id) }.map {
                let value = exactShares[$0.id] ?? 0
                return ($0.id, value.isFinite && (0...CanvasMoney.maximumValue).contains(value) ? Int((value * 100).rounded()) : -1)
            })
        }
        return PlanSharedExpense.equal(cents, among: participants(group).filter { selected.contains($0.id) }.map(\.id))
    }
    private func participants(_ group: PlanGroup) -> [PlanMember] { initial == nil ? group.activeMembers : group.members }
    var body: some View {
        NavigationStack {
            if let group {
                ScrollView {
                    VStack(alignment: .leading, spacing: 22) {
                        if initial == nil && group.kind == .trip && receiptWorkspace != nil {
                            Menu { ReceiptSourceActions(spanish: spanish) { receiptRoute = .capture(ReceiptOrigin(groupID: groupID, threadID: nil), $0) } } label: {
                                Label(CuadraoCopy.text("copy.cuadraoGroupExpenseEditor.35f095c382", spanish: spanish), systemImage: "receipt").frame(minHeight: 44)
                            }.accessibilityIdentifier("group-expense-receipt")
                        }
                        TextField(group.kind == .saving ? (CuadraoCopy.text("copy.cuadraoGroupExpenseEditor.9940c451e0", spanish: spanish)) : (CuadraoCopy.text("copy.cuadraoGroupExpenseEditor.e00e06b68d", spanish: spanish)), text: $title).font(CuadraoTypography.section).accessibilityIdentifier("group-expense-name")
                        PlanAmountInput(value: $amount, currency: .constant(group.currency), error: $amountErrors.message(for: "amount"),
                                        title: CuadraoCopy.text("copy.canvasDecimalInput.69f09a95c5", spanish: spanish), identifier: "group-expense-amount", spanish: spanish)
                        Picker(group.kind == .saving ? (CuadraoCopy.text("copy.cuadraoGroupExpenseEditor.d1f214d485", spanish: spanish)) : (CuadraoCopy.text("copy.cuadraoGroupExpenseEditor.76f42fdad3", spanish: spanish)), selection: $payer) {
                            ForEach(participants(group)) { member in Text(member.name).tag(Optional(member.id)) }
                        }.pickerStyle(.menu)
                        if group.kind == .trip {
                            HStack {
                                Text(CuadraoCopy.text("copy.cuadraoGroupExpenseEditor.27e862291e", spanish: spanish)).font(.headline)
                                Spacer()
                                Menu(custom ? (CuadraoCopy.text("copy.cuadraoGroupExpenseEditor.e8a46f3dbb", spanish: spanish)) : (CuadraoCopy.text("copy.cuadraoGroupExpenseEditor.0817ba2531", spanish: spanish))) {
                                    Button(CuadraoCopy.text("copy.cuadraoGroupExpenseEditor.12cc303b3a", spanish: spanish)) { custom = false }
                                    Button(CuadraoCopy.text("copy.cuadraoGroupExpenseEditor.9f5a089947", spanish: spanish)) {
                                        exactShares = shares(group).mapValues { Double($0) / 100 }; custom = true
                                    }
                                }.accessibilityIdentifier("group-split-method")
                            }
                            ForEach(Array(participants(group).enumerated()), id: \.element.id) { index, member in
                                HStack(spacing: 12) {
                                    Button {
                                        if selected.contains(member.id) { selected.remove(member.id) } else { selected.insert(member.id) }
                                    } label: {
                                        HStack { Image(systemName: selected.contains(member.id) ? "checkmark.circle.fill" : "circle"); PlanMemberAvatar(member: member, index: index); Text(member.name) }
                                            .frame(minHeight: 44)
                                    }.buttonStyle(.plain).accessibilityLabel("\(member.name), \(selected.contains(member.id) ? (CuadraoCopy.text("copy.cuadraoGroupExpenseEditor.59d85d47f8", spanish: spanish)) : (CuadraoCopy.text("copy.cuadraoGroupExpenseEditor.e7ff4eb642", spanish: spanish)))")
                                    Spacer()
                                    if custom && selected.contains(member.id) {
                                        VStack(alignment: .trailing) {
                                            CanvasMoneyValueInput(value: Binding(get: { exactShares[member.id] ?? 0 }, set: { exactShares[member.id] = $0 }),
                                                error: $amountErrors.message(for: member.id.uuidString), currency: group.currency, spanish: spanish,
                                                identifier: "group-share-\(index)", title: CuadraoCopy.text("copy.cuadraoGroupExpenseEditor.4df59a5cf3", spanish: spanish, String(describing: member.name)),
                                                size: .row, alignment: .right).frame(minWidth: 90, maxWidth: 140, minHeight: 44)
                                            if let error = amountErrors[member.id.uuidString], !error.isEmpty {
                                                Text(error).font(CuadraoTypography.caption).foregroundStyle(.red)
                                            }
                                        }
                                    } else { Text(PlanFormat.amount(Double(shares(group)[member.id] ?? 0) / 100, currency: group.currency)).font(CuadraoTypography.rowAmount) }
                                }
                            }
                            if custom {
                                let remainder = cents - shares(group).values.reduce(0, +)
                                Text(remainder == 0 ? (CuadraoCopy.text("copy.cuadraoGroupExpenseEditor.d158b68db6", spanish: spanish)) : remainder < 0 ? (CuadraoCopy.text("copy.cuadraoGroupExpenseEditor.c987e9cd17", spanish: spanish, String(describing: PlanFormat.amount(Double(-remainder) / 100, currency: group.currency)))) : (CuadraoCopy.text("copy.cuadraoGroupExpenseEditor.7ab9ebe423", spanish: spanish, String(describing: PlanFormat.amount(Double(remainder) / 100, currency: group.currency)))))
                                    .font(.caption).foregroundStyle(remainder == 0 ? WelcomePalette.pine : .orange)
                            }
                        }
                        if let receipt, let image = UIImage(data: receipt) {
                            Image(uiImage: image).resizable().scaledToFit().frame(maxHeight: 160).clipShape(RoundedRectangle(cornerRadius: 16))
                            Button(CuadraoCopy.text("copy.cuadraoProfileAvatar.363f525e28", spanish: spanish), role: .destructive) { self.receipt = nil; photo = nil }
                        }
                        PhotosPicker(selection: $photo, matching: .images) {
                            Label(CuadraoCopy.text("copy.cuadraoGroupExpenseEditor.9926e318e8", spanish: spanish), systemImage: "camera").frame(minHeight: 44)
                        }
                        if photoError { Text(CuadraoCopy.text("copy.cuadraoGroupExpenseEditor.f07161357b", spanish: spanish)).font(.caption).foregroundStyle(.red) }
                        if receipt != nil { Text(CuadraoCopy.text("copy.cuadraoGroupExpenseEditor.68daf29fd0", spanish: spanish)).font(.caption).foregroundStyle(.secondary) }
                        PlanPrimaryButton(title: group.kind == .trip ? (CuadraoCopy.text("copy.cuadraoGroupExpenseEditor.5f56a4641d", spanish: spanish)) : (CuadraoCopy.text("copy.cuadraoGroupDetail.087e4a279d", spanish: spanish))) { save(group, draft: false) }
                            .disabled(!valid || shares(group).values.contains(where: { $0 < 0 }) || shares(group).values.reduce(0, +) != cents)
                            .accessibilityIdentifier("group-expense-save")
                        if initial == nil || initial?.draft == true {
                            Button(CuadraoCopy.text("copy.cuadraoGroupExpenseEditor.4d01753246", spanish: spanish)) { save(group, draft: true) }
                                .frame(maxWidth: .infinity, minHeight: 44).disabled(!validDraft).accessibilityIdentifier("group-expense-draft")
                            Text(CuadraoCopy.text("copy.cuadraoGroupExpenseEditor.e4e3728b05", spanish: spanish)).font(.caption).foregroundStyle(.secondary)
                        }
                        if initial != nil {
                            Button(CuadraoCopy.text("copy.cuadraoGroupExpenseEditor.f209b9e889", spanish: spanish), role: .destructive) { discard = true }
                        }
                    }.padding(24)
                }.cuadraoFormKeyboard().background(WelcomePalette.background)
                    .navigationTitle(group.kind == .trip ? (CuadraoCopy.text("copy.cuadraoGroupExpenseEditor.63e621180b", spanish: spanish)) : (CuadraoCopy.text("copy.cuadraoGroupExpenseEditor.772039f139", spanish: spanish))).navigationBarTitleDisplayMode(.inline)
                    .toolbar {
                        CuadraoCancelToolbar(title: CuadraoCopy.text("copy.connectedCuadraoProfile.62a128b722", spanish: spanish)) { dismiss() }
                    }
                    .confirmationDialog(CuadraoCopy.text("copy.cuadraoGroupExpenseEditor.215456660f", spanish: spanish), isPresented: $discard, titleVisibility: .visible) {
                        Button(CuadraoCopy.text("copy.savedReceiptCopy.534547cf82", spanish: spanish), role: .destructive) {
                            var updated = group; updated.expenses.removeAll { $0.id == initial?.id }; store.save(updated); dismiss()
                        }
                    }
                    .onAppear {
                        guard !initialized else { return }
                        initialized = true
                        payer = initial?.payer ?? group.me; selected = Set(initial?.shares.keys.map { $0 } ?? group.activeMembers.map(\.id))
                        if let initial { title = initial.title; amount = Double(initial.cents) / 100; receipt = initial.receipt; exactShares = initial.shares.mapValues { Double($0) / 100 }; custom = !initial.draft }
                    }
            }
        }.presentationDragIndicator(.visible).interactiveDismissDisabled()
            .receiptPresentation(route: $receiptRoute, workspace: receiptWorkspace, spanish: spanish)
            .task(id: photo) {
                guard let photo else { return }; photoError = false
                if let data = try? await photo.loadTransferable(type: Data.self), let image = UIImage(data: data) {
                    let size = image.size; let ratio = min(1, 1200 / max(size.width, size.height))
                    receipt = UIGraphicsImageRenderer(size: CGSize(width: size.width * ratio, height: size.height * ratio)).image { _ in image.draw(in: CGRect(x: 0, y: 0, width: size.width * ratio, height: size.height * ratio)) }.jpegData(compressionQuality: 0.65)
                } else { photoError = true }
            }
    }
    private func save(_ group: PlanGroup, draft: Bool) {
        guard let payer else { return }
        var updated = group
        let trimmed = title.trimmingCharacters(in: .whitespacesAndNewlines)
        let name = trimmed.isEmpty ? (CuadraoCopy.text("copy.cuadraoGroupExpenseEditor.0a67f1e2f2", spanish: spanish)) : trimmed
        var expense = PlanSharedExpense(title: name, cents: cents, payer: payer, shares: shares(group), draft: draft, receipt: receipt)
        if let initial { expense.id = initial.id }
        if updated.record(expense) { store.save(updated); dismiss() }
    }
}

struct CuadraoGroupSettlement: View {
    let store: CuadraoGroupPreview
    let groupID: UUID
    let spanish: Bool
    @State private var from: UUID?
    @State private var to: UUID?
    @State private var amount = 0.0
    @State private var amountErrors: [String: String] = [:]
    @Environment(\.dismiss) private var dismiss
    private var group: PlanGroup? { store.group(groupID) }
    private var maximum: Int { guard let group, let from, let to else { return 0 }; return max(0, min(-group.balance(from), group.balance(to))) }
    var body: some View {
        NavigationStack {
            if let group {
                Form {
                    Section {
                        Picker(CuadraoCopy.text("copy.cuadraoGroupExpenseEditor.aa571c42f7", spanish: spanish), selection: $from) { ForEach(group.members.filter { group.balance($0.id) < 0 }) { Text($0.name).tag(Optional($0.id)) } }
                        Picker(CuadraoCopy.text("copy.cuadraoGroupExpenseEditor.2bc47f8607", spanish: spanish), selection: $to) { ForEach(group.members.filter { group.balance($0.id) > 0 }) { Text($0.name).tag(Optional($0.id)) } }
                        PlanAmountInput(value: $amount, currency: .constant(group.currency), error: $amountErrors.message(for: "amount"),
                                        title: CuadraoCopy.text("copy.cuadraoGroupExpenseEditor.9a1f5d5ed1", spanish: spanish), identifier: "group-repayment-amount", spanish: spanish)
                    } footer: { Text(CuadraoCopy.text("copy.cuadraoGroupExpenseEditor.bb5b52ca75", spanish: spanish)) }
                    Section {
                        Button(CuadraoCopy.text("copy.cuadraoGroupExpenseEditor.7f81574043", spanish: spanish)) {
                            guard let from, let to else { return }
                            var updated = group
                            if updated.repay(from: from, to: to, cents: Int((amount * 100).rounded())) { store.save(updated); dismiss() }
                        }.disabled(amountErrors.values.contains { !$0.isEmpty } || !amount.isFinite || amount < 0.01 || amount * 100 > Double(maximum)).accessibilityIdentifier("group-repayment-save")
                    }
                }.cuadraoFormKeyboard().navigationTitle(CuadraoCopy.text("copy.cuadraoGroupExpenseEditor.fe62817ffe", spanish: spanish)).navigationBarTitleDisplayMode(.inline)
                    .toolbar {
                        CuadraoCancelToolbar(title: CuadraoCopy.text("copy.cuadraoAccountsCollection.f296f2cba3", spanish: spanish)) { dismiss() }
                    }
                    .onAppear { from = group.members.first { group.balance($0.id) < 0 }?.id; to = group.members.first { group.balance($0.id) > 0 }?.id; amount = Double(maximum) / 100 }
                    .onChange(of: from) { _, _ in amount = Double(maximum) / 100 }
                    .onChange(of: to) { _, _ in amount = Double(maximum) / 100 }
            }
        }.presentationDetents([.medium, .large]).presentationDragIndicator(.visible)
    }
}
