import SwiftUI

struct CuadraoGroupDetail: View {
    @Environment(\.receiptWorkspace) private var receiptWorkspace
    let store: CuadraoGroupPreview
    let groupID: UUID
    let spanish: Bool
    var bottomSpace: CGFloat = 90
    @State private var chatFocus: CanvasChatFocus?
    @State private var section = 0
    @State private var sheet: GroupSheet?
    @State private var people = 8.0
    @State private var didSave = false
    @Environment(\.dismiss) private var dismiss
    private var group: PlanGroup? { store.group(groupID) }
    private enum GroupSheet: Identifiable {
        case invite, edit, expense(PlanSharedExpense?), settle, remove(PlanMember)
        var id: String { switch self { case .invite: "invite"; case .edit: "edit"; case .expense: "expense"; case .settle: "settle"; case .remove: "remove" } }
    }
    var body: some View {
        Group {
            if let group {
                ScrollView {
                    VStack(alignment: .leading, spacing: 24) {
                        hero(group)
                        Picker(CuadraoCopy.text("copy.savedReceiptCopy.2b0aad47ef", spanish: spanish), selection: $section) {
                            Text(CuadraoCopy.text("copy.cuadraoGroupDetail.b7b5977d12", spanish: spanish)).tag(0)
                            Text(group.kind == .trip ? (CuadraoCopy.text("copy.cuadraoGroupDetail.e81263a140", spanish: spanish)) : (CuadraoCopy.text("copy.cuadraoGroupDetail.4400cb3469", spanish: spanish))).tag(1)
                            Text(CuadraoCopy.text("copy.cuadraoHomeEmptyState.bede691c92", spanish: spanish)).tag(2)
                        }.pickerStyle(.segmented).accessibilityIdentifier("group-sections")
                        if section == 0 { overview(group) }
                        if section == 1 { expenses(group) }
                        if section == 2 { members(group) }
                        if section != 2 {
                            Text(CuadraoCopy.text("copy.cuadraoGroupDetail.1e49ad1a60", spanish: spanish))
                                .font(.caption2).foregroundStyle(.secondary).frame(maxWidth: .infinity).multilineTextAlignment(.center)
                        }
                    }.padding(.horizontal, 24).padding(.bottom, bottomSpace)
                }.background(WelcomePalette.background).cuadraoSoftScrollEdges()
                    .toolbar {
                        ToolbarItem(placement: .topBarTrailing) {
                            Menu {
                                if receiptWorkspace != nil {
                                    Button(CuadraoCopy.text("copy.cuadraoAccountCanvas.b44a9adeb4", spanish: spanish), systemImage: "bubble") { chatFocus = .group(id: group.id, title: group.name) }
                                        .accessibilityIdentifier("group-open-chat")
                                }
                                if store.canManage { Button(CuadraoCopy.text("copy.cuadraoGroupDetail.0881b07c3a", spanish: spanish), systemImage: "pencil") { sheet = .edit } }
                                Button(CuadraoCopy.text("copy.connectedCuadraoHome.0960027352", spanish: spanish), systemImage: "archivebox") { store.archive(group.id, true); dismiss() }
                            } label: { Image(systemName: "ellipsis").frame(width: 44, height: 44) }.accessibilityIdentifier("group-options")
                        }
                    }
                    .sheet(item: $sheet) { route in
                        switch route {
                        case .invite: CuadraoGroupInvitation(store: store, groupID: group.id, spanish: spanish)
                        case .edit: CuadraoGroupEditor(store: store, spanish: spanish, initial: group)
                        case .expense(let entry): CuadraoGroupExpenseEditor(store: store, groupID: group.id, initial: entry, spanish: spanish)
                        case .settle: CuadraoGroupSettlement(store: store, groupID: group.id, spanish: spanish)
                        case .remove(let member): CuadraoGroupMemberReview(store: store, groupID: group.id, member: member, spanish: spanish)
                        }
                    }
                    .onAppear { people = Double(group.expectedPeople) }
            }
        }.navigationTitle("").navigationBarTitleDisplayMode(.inline).toolbar(.visible, for: .navigationBar)
            .contextualCuadrao(focus: $chatFocus, spanish: spanish)
            .sensoryFeedback(.success, trigger: didSave) { _, new in new }
    }
    private func hero(_ group: PlanGroup) -> some View {
        VStack(alignment: .leading, spacing: 16) {
            PlanGroupArtwork(look: group.look, progress: group.kind == .saving ? group.progress : nil, cover: group.cover)
                .frame(height: 145).clipShape(RoundedRectangle(cornerRadius: 28))
                .overlay(alignment: .bottomLeading) {
                    Button { section = 2 } label: { PlanAvatarStack(members: group.activeMembers).padding(16) }
                        .accessibilityLabel(CuadraoCopy.text("copy.cuadraoGroupDetail.0e52ae861f", spanish: spanish)).accessibilityIdentifier("group-people-open")
                }
            Text(group.name).font(CuadraoTypography.screen)
            Text(CuadraoCopy.text("copy.cuadraoGroupDetail.6619b87cfe", spanish: spanish, String(describing: group.activeMembers.count), String(describing: (spanish ? (group.kind.title(true)) : (group.kind.title(false))))))
                .font(.caption).foregroundStyle(.secondary)
        }
    }
    @ViewBuilder private func overview(_ group: PlanGroup) -> some View {
        if group.kind == .saving {
            VStack(alignment: .leading, spacing: 10) {
                Text(PlanFormat.amount(Double(group.total) / 100, currency: group.currency)).font(CuadraoTypography.amount).monospacedDigit()
                Text(CuadraoCopy.text("copy.cuadraoGroupDetail.d5a27eecc1", spanish: spanish, String(describing: PlanFormat.amount(Double(group.estimatedCents) / 100, currency: group.currency)))).font(.subheadline).foregroundStyle(.secondary)
                ProgressView(value: group.progress).tint(group.look.color)
                Text(group.progress >= 1 ? (CuadraoCopy.text("copy.cuadraoGroupDetail.c5034e375a", spanish: spanish)) : (CuadraoCopy.text("copy.cuadraoGroupDetail.e6ba8ca4a7", spanish: spanish)))
                    .font(.system(.title3, design: .serif)).foregroundStyle(group.look.color)
            }
        } else { balances(group) }
        VStack(alignment: .leading, spacing: 14) {
            Text(CuadraoCopy.text("copy.cuadraoGroupDetail.f2de2bc4e3", spanish: spanish)).font(CuadraoTypography.section)
            Text(PlanFormat.amount(Double(group.estimatedCents) / 100 / people, currency: group.currency)).font(CuadraoTypography.secondaryAmount).monospacedDigit().contentTransition(.numericText())
                .accessibilityIdentifier("group-estimate-per-person")
            Text(CuadraoCopy.text("copy.cuadraoGroupDetail.c3698c4e5c", spanish: spanish, String(describing: Int(people)))).font(.subheadline).foregroundStyle(.secondary)
            Slider(value: $people, in: 1...50, step: 1).tint(group.look.color).accessibilityLabel(CuadraoCopy.text("copy.cuadraoGroupDetail.13b097df01", spanish: spanish)).accessibilityIdentifier("group-people-slider")
            Text(CuadraoCopy.text("copy.cuadraoGroupDetail.9949d8d541", spanish: spanish, String(describing: PlanFormat.amount(Double(group.estimatedCents) / 100, currency: group.currency))))
                .font(.caption).foregroundStyle(.secondary)
            if store.canManage && Int(people) != group.expectedPeople {
                Button(CuadraoCopy.text("copy.cuadraoGroupDetail.19c5307901", spanish: spanish)) {
                    var updated = group; updated.expectedPeople = Int(people); store.save(updated); didSave = true
                }.font(.subheadline.weight(.medium)).frame(minHeight: 44).accessibilityIdentifier("group-save-estimate")
            }
        }.padding(20).background(group.look.color.opacity(0.07), in: RoundedRectangle(cornerRadius: 26))
        PlanPrimaryButton(title: group.kind == .trip ? (CuadraoCopy.text("copy.cuadraoGroupDetail.d4ebecc441", spanish: spanish)) : (CuadraoCopy.text("copy.cuadraoGroupDetail.087e4a279d", spanish: spanish)), symbol: "plus") { sheet = .expense(nil) }
            .accessibilityIdentifier("group-add-expense")
    }
    private func balances(_ group: PlanGroup) -> some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack(alignment: .firstTextBaseline) {
                VStack(alignment: .leading, spacing: 6) {
                    Text(CuadraoCopy.text("copy.cuadraoFirstAccountSheet.15732a4703", spanish: spanish)).font(.subheadline).foregroundStyle(.secondary)
                    Text(PlanFormat.amount(Double(group.share(group.me)) / 100, currency: group.currency)).font(CuadraoTypography.secondaryAmount).monospacedDigit().accessibilityIdentifier("group-own-share")
                }
                Spacer()
                Image(systemName: "person.crop.circle").font(.title).foregroundStyle(group.look.color)
            }
            HStack {
                metric(CuadraoCopy.text("copy.cuadraoGroupDetail.49645dadc7", spanish: spanish), cents: group.total, group: group)
                Spacer()
                metric(CuadraoCopy.text("copy.cuadraoGroupDetail.4d38b12861", spanish: spanish), cents: group.paid(group.me), group: group)
            }
            Divider()
            CuadraoOwedRow(cents: group.balance(group.me), currency: group.currency, spanish: spanish)
                .accessibilityIdentifier("group-outstanding")
            if group.members.contains(where: { group.balance($0.id) < 0 }) {
                Button(CuadraoCopy.text("copy.cuadraoGroupDetail.2278671cc6", spanish: spanish)) { sheet = .settle }
                    .font(.subheadline).frame(minHeight: 44).accessibilityIdentifier("group-settle")
            }
        }
    }
    private func metric(_ label: String, cents: Int, group: PlanGroup) -> some View {
        VStack(alignment: .leading, spacing: 6) { Text(label).font(.caption).foregroundStyle(.secondary); Text(PlanFormat.amount(Double(cents) / 100, currency: group.currency)).font(CuadraoTypography.rowAmount) }
    }
    private func expenses(_ group: PlanGroup) -> some View {
        VStack(alignment: .leading, spacing: 18) {
            if group.kind == .trip, let workspace = receiptWorkspace {
                Menu {
                    ReceiptSourceActions(spanish: spanish) { workspace.capture(ReceiptOrigin(groupID: group.id, threadID: nil), $0) }
                } label: {
                    Label(CuadraoCopy.text("copy.cuadraoGroupDetail.9f86838362", spanish: spanish), systemImage: "receipt").frame(minHeight: 44)
                }.accessibilityIdentifier("group-add-receipt")
                ForEach(workspace.receipts.receipts.filter { $0.groupID == group.id && $0.prepared }) { draft in
                    ReceiptCard(draft: draft, spanish: spanish) { workspace.open(draft.id) }
                }
            }
            PlanPrimaryButton(title: group.kind == .trip ? (CuadraoCopy.text("copy.cuadraoGroupDetail.d4ebecc441", spanish: spanish)) : (CuadraoCopy.text("copy.cuadraoGroupDetail.087e4a279d", spanish: spanish)), symbol: "plus") { sheet = .expense(nil) }
                .accessibilityIdentifier("group-add-expense")
            if group.expenses.isEmpty { Text(CuadraoCopy.text("copy.cuadraoGroupDetail.a1fa3cf39f", spanish: spanish)).foregroundStyle(.secondary) }
            ForEach(group.expenses.reversed()) { entry in
                Button {
                    if let id = entry.receiptID { receiptWorkspace?.open(id) }
                    else { sheet = .expense(entry) }
                } label: {
                    HStack(spacing: 12) {
                        Image(systemName: entry.draft ? "doc.badge.clock" : group.kind == .saving ? "leaf" : "receipt").frame(width: 42, height: 42).background(group.look.color.opacity(0.1), in: RoundedRectangle(cornerRadius: 14))
                        VStack(alignment: .leading, spacing: 5) {
                            Text(entry.title).foregroundStyle(WelcomePalette.ink)
                            Text(entry.draft ? (CuadraoCopy.text("copy.cuadraoGroupDetail.3bad4f7140", spanish: spanish)) : "\(group.members.first { $0.id == entry.payer }?.name ?? "") · \(CuadraoCopy.text("copy.cuadraoGroupDetail.a6323107e2", spanish: spanish))")
                                .font(.caption).foregroundStyle(.secondary)
                        }
                        Spacer()
                        Text(entry.draft && entry.cents == 0 ? (CuadraoCopy.text("copy.cuadraoGroupDetail.fb7d09ac4c", spanish: spanish)) : PlanFormat.amount(Double(entry.cents) / 100, currency: group.currency)).font(CuadraoTypography.rowAmount).foregroundStyle(WelcomePalette.ink)
                    }.frame(minHeight: 64).contentShape(Rectangle())
                }.buttonStyle(.plain).accessibilityIdentifier("group-entry-\(entry.draft ? "draft" : "recorded")")
            }
            if !group.repayments.isEmpty {
                Text(CuadraoCopy.text("copy.cuadraoGroupDetail.e0e874bf3d", spanish: spanish)).font(.headline)
                ForEach(group.repayments) { entry in
                    HStack {
                        Text("\(group.members.first { $0.id == entry.from }?.name ?? "") → \(group.members.first { $0.id == entry.to }?.name ?? "")")
                        Spacer(); Text(PlanFormat.amount(Double(entry.cents) / 100, currency: group.currency)).font(CuadraoTypography.rowAmount)
                        Button { var updated = group; updated.repayments.removeAll { $0.id == entry.id }; store.save(updated) } label: { Image(systemName: "arrow.uturn.backward").frame(width: 44, height: 44) }.accessibilityLabel(CuadraoCopy.text("copy.cuadraoGroupDetail.13c51fe6c3", spanish: spanish))
                    }.font(.subheadline)
                }
            }
        }
    }
    private func members(_ group: PlanGroup) -> some View {
        VStack(alignment: .leading, spacing: 20) {
            if #available(iOS 27.0, *), !ProcessInfo.processInfo.arguments.contains("--legacy-collection") {
                VStack(spacing: 20) {
                    ForEach(Array(group.activeMembers.enumerated()), id: \.element.id) { index, member in
                        if store.canManage && member.id != group.me {
                            memberRow(member, index: index, group: group)
                                .swipeActions(edge: .trailing, allowsFullSwipe: false) { removeAction(member) }
                        } else {
                            memberRow(member, index: index, group: group)
                        }
                    }
                }.swipeActionsContainer()
            } else {
                ForEach(Array(group.activeMembers.enumerated()), id: \.element.id) { index, member in
                    memberRow(member, index: index, group: group)
                        .contextMenu {
                            if store.canManage && member.id != group.me { removeAction(member) }
                        }
                }
            }
            if store.canManage {
                Button { sheet = .invite } label: { Label(CuadraoCopy.text("copy.cuadraoHomeEmptyState.d9987908d0", spanish: spanish), systemImage: "person.badge.plus").frame(minHeight: 44) }
                    .accessibilityIdentifier("group-invite")
            }
            if !group.removedMemberIDs.isEmpty {
                DisclosureGroup(CuadraoCopy.text("copy.cuadraoGroupDetail.a845c35bc6", spanish: spanish)) {
                    ForEach(group.members.filter { group.removedMemberIDs.contains($0.id) }) { member in
                        Text(member.name).font(.subheadline).foregroundStyle(.secondary).frame(maxWidth: .infinity, alignment: .leading)
                    }
                }
            }
            Text(CuadraoCopy.text("copy.cuadraoGroupDetail.e88ccfd53d", spanish: spanish)).font(.caption).foregroundStyle(.secondary)
        }
    }
    private func memberRow(_ member: PlanMember, index: Int, group: PlanGroup) -> some View {
        HStack(spacing: 12) {
            PlanMemberAvatar(member: member, index: index)
            VStack(alignment: .leading, spacing: 4) {
                Text(member.name)
                if member.id == group.me && store.canManage { Text(CuadraoCopy.text("copy.cuadraoGroupDetail.63d3c4f3f7", spanish: spanish)).font(.caption).foregroundStyle(.secondary) }
            }
            Spacer()
            if group.kind == .saving {
                Text(PlanFormat.amount(Double(group.paid(member.id)) / 100, currency: group.currency)).font(CuadraoTypography.rowAmount)
            } else {
                CuadraoOwedRow(cents: group.balance(member.id), currency: group.currency,
                              spanish: spanish, own: member.id == group.me, compact: true)
            }
        }
        .frame(minHeight: 54).contentShape(Rectangle())
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("group-member-" + member.name)
        .accessibilityActions {
            if store.canManage && member.id != group.me { removeAction(member) }
        }
    }
    private func removeAction(_ member: PlanMember) -> some View {
        Button(CuadraoCopy.text("copy.cuadraoChatAnswer.1b73d18e75", spanish: spanish), systemImage: "person.crop.circle.badge.minus", role: .destructive) { sheet = .remove(member) }
            .tint(.red)
            .accessibilityLabel((CuadraoCopy.text("copy.cuadraoGroupDetail.0ad213f5a8", spanish: spanish)) + member.name)
            .accessibilityIdentifier("group-remove-" + member.name)
    }

}
