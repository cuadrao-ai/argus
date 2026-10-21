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
                                Label(spanish ? "Usar un recibo" : "Use a receipt", systemImage: "receipt").frame(minHeight: 44)
                            }.accessibilityIdentifier("group-expense-receipt")
                        }
                        TextField(group.kind == .saving ? (spanish ? "¿Para qué aportas?" : "What are you saving for?") : (spanish ? "¿Qué pagaron?" : "What was it for?"), text: $title).font(CuadraoTypography.section).accessibilityIdentifier("group-expense-name")
                        PlanAmountInput(value: $amount, currency: .constant(group.currency), error: $amountErrors.message(for: "amount"),
                                        title: spanish ? "Monto" : "Amount", identifier: "group-expense-amount", spanish: spanish)
                        Picker(group.kind == .saving ? (spanish ? "Aportó" : "Contributed by") : (spanish ? "Pagó" : "Paid by"), selection: $payer) {
                            ForEach(participants(group)) { member in Text(member.name).tag(Optional(member.id)) }
                        }.pickerStyle(.menu)
                        if group.kind == .trip {
                            HStack {
                                Text(spanish ? "¿Cómo lo repartimos?" : "How shall we split it?").font(.headline)
                                Spacer()
                                Menu(custom ? (spanish ? "Montos" : "Amounts") : (spanish ? "Igual" : "Equally")) {
                                    Button(spanish ? "Por igual" : "Equally") { custom = false }
                                    Button(spanish ? "Montos exactos" : "Exact amounts") {
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
                                    }.buttonStyle(.plain).accessibilityLabel("\(member.name), \(selected.contains(member.id) ? (spanish ? "incluido" : "included") : (spanish ? "excluido" : "excluded"))")
                                    Spacer()
                                    if custom && selected.contains(member.id) {
                                        VStack(alignment: .trailing) {
                                            CanvasMoneyValueInput(value: Binding(get: { exactShares[member.id] ?? 0 }, set: { exactShares[member.id] = $0 }),
                                                error: $amountErrors.message(for: member.id.uuidString), currency: group.currency, spanish: spanish,
                                                identifier: "group-share-\(index)", title: spanish ? "Parte de \(member.name)" : "\(member.name)'s share",
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
                                Text(remainder == 0 ? (spanish ? "Todo cuadra." : "It all adds up.") : remainder < 0 ? (spanish ? "Hay \(PlanFormat.amount(Double(-remainder) / 100, currency: group.currency)) de más." : "\(PlanFormat.amount(Double(-remainder) / 100, currency: group.currency)) over the total.") : (spanish ? "Por repartir: \(PlanFormat.amount(Double(remainder) / 100, currency: group.currency))" : "Left to split: \(PlanFormat.amount(Double(remainder) / 100, currency: group.currency))"))
                                    .font(.caption).foregroundStyle(remainder == 0 ? WelcomePalette.pine : .orange)
                            }
                        }
                        if let receipt, let image = UIImage(data: receipt) {
                            Image(uiImage: image).resizable().scaledToFit().frame(maxHeight: 160).clipShape(RoundedRectangle(cornerRadius: 16))
                            Button(spanish ? "Quitar foto" : "Remove photo", role: .destructive) { self.receipt = nil; photo = nil }
                        }
                        PhotosPicker(selection: $photo, matching: .images) {
                            Label(spanish ? "Añadir foto del recibo" : "Add receipt photo", systemImage: "camera").frame(minHeight: 44)
                        }
                        if photoError { Text(spanish ? "No pudimos abrir esa foto. Prueba otra." : "Couldn't open that photo. Try another.").font(.caption).foregroundStyle(.red) }
                        if receipt != nil { Text(spanish ? "La foto queda adjunta. Revisa e introduce el total; esta vista previa no lee recibos." : "Photo attached. Review and enter the total; this preview doesn't read receipts.").font(.caption).foregroundStyle(.secondary) }
                        PlanPrimaryButton(title: group.kind == .trip ? (spanish ? "Guardar reparto" : "Save split") : (spanish ? "Registrar aporte" : "Record contribution")) { save(group, draft: false) }
                            .disabled(!valid || shares(group).values.contains(where: { $0 < 0 }) || shares(group).values.reduce(0, +) != cents)
                            .accessibilityIdentifier("group-expense-save")
                        if initial == nil || initial?.draft == true {
                            Button(spanish ? "Guardar para después" : "Save for later") { save(group, draft: true) }
                                .frame(maxWidth: .infinity, minHeight: 44).disabled(!validDraft).accessibilityIdentifier("group-expense-draft")
                            Text(spanish ? "Un borrador no cambia los balances ni avisa a nadie." : "A draft doesn't change balances or notify anyone.").font(.caption).foregroundStyle(.secondary)
                        }
                        if initial != nil {
                            Button(spanish ? "Eliminar registro" : "Delete entry", role: .destructive) { discard = true }
                        }
                    }.padding(24)
                }.cuadraoFormKeyboard().background(WelcomePalette.background)
                    .navigationTitle(group.kind == .trip ? (spanish ? "Un gasto juntos" : "A shared expense") : (spanish ? "Un paso más" : "One step closer")).navigationBarTitleDisplayMode(.inline)
                    .toolbar {
                        CuadraoCancelToolbar(title: spanish ? "Cancelar" : "Cancel") { dismiss() }
                    }
                    .confirmationDialog(spanish ? "¿Eliminar este registro?" : "Delete this entry?", isPresented: $discard, titleVisibility: .visible) {
                        Button(spanish ? "Eliminar" : "Delete", role: .destructive) {
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
        let name = trimmed.isEmpty ? (spanish ? "Recibo por revisar" : "Receipt to review") : trimmed
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
                        Picker(spanish ? "Envió" : "Sent by", selection: $from) { ForEach(group.members.filter { group.balance($0.id) < 0 }) { Text($0.name).tag(Optional($0.id)) } }
                        Picker(spanish ? "Recibió" : "Received by", selection: $to) { ForEach(group.members.filter { group.balance($0.id) > 0 }) { Text($0.name).tag(Optional($0.id)) } }
                        PlanAmountInput(value: $amount, currency: .constant(group.currency), error: $amountErrors.message(for: "amount"),
                                        title: spanish ? "Monto devuelto" : "Amount repaid", identifier: "group-repayment-amount", spanish: spanish)
                    } footer: { Text(spanish ? "Registra dinero que ya se devolvió por fuera de Cuadrao. Puedes registrar una parte." : "Record money already returned outside Cuadrao. Partial repayments are welcome.") }
                    Section {
                        Button(spanish ? "Registrar reembolso" : "Record repayment") {
                            guard let from, let to else { return }
                            var updated = group
                            if updated.repay(from: from, to: to, cents: Int((amount * 100).rounded())) { store.save(updated); dismiss() }
                        }.disabled(amountErrors.values.contains { !$0.isEmpty } || !amount.isFinite || amount < 0.01 || amount * 100 > Double(maximum)).accessibilityIdentifier("group-repayment-save")
                    }
                }.cuadraoFormKeyboard().navigationTitle(spanish ? "Vamos cuadrando" : "Settling up").navigationBarTitleDisplayMode(.inline)
                    .toolbar {
                        CuadraoCancelToolbar(title: spanish ? "Cerrar" : "Close") { dismiss() }
                    }
                    .onAppear { from = group.members.first { group.balance($0.id) < 0 }?.id; to = group.members.first { group.balance($0.id) > 0 }?.id; amount = Double(maximum) / 100 }
                    .onChange(of: from) { _, _ in amount = Double(maximum) / 100 }
                    .onChange(of: to) { _, _ in amount = Double(maximum) / 100 }
            }
        }.presentationDetents([.medium, .large]).presentationDragIndicator(.visible)
    }
}
