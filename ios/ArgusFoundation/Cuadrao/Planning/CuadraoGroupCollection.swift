import SwiftUI

struct CuadraoGroupCollection: View {
    let store: CuadraoGroupPreview
    let spanish: Bool
    let bottomSpace: CGFloat
    let create: () -> Void
    let open: (UUID) -> Void
    @State private var editing: PlanGroup?
    var body: some View {
        VStack(alignment: .leading, spacing: 22) {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text(CuadraoCopy.text("copy.cuadraoGroupCollection.3ab3b02437", spanish: spanish))
                        .font(CuadraoTypography.section)
                    Text(CuadraoCopy.text("copy.cuadraoGroupCollection.b5cd9f7d82", spanish: spanish))
                        .font(.subheadline).foregroundStyle(.secondary)
                }
            }
            CuadraoOrderedCollection(items: store.groups.filter { !$0.archived }, spanish: spanish, spacing: 22,
                identifier: { "group-card-\($0.kind.rawValue)" },
                open: { open($0.id) }, edit: { editing = $0 }, canEdit: { _ in store.canManage },
                archive: { store.archive($0.id, true) }, reorder: store.reorder) { group in
                    VStack(alignment: .leading, spacing: 16) {
                        PlanGroupArtwork(look: group.look, progress: group.kind == .saving ? group.progress : nil, cover: group.cover)
                            .frame(height: 140)
                            .overlay(alignment: .bottomLeading) { PlanAvatarStack(members: group.activeMembers).padding(16) }
                        VStack(alignment: .leading, spacing: 8) {
                            Text(group.name).font(CuadraoTypography.section).foregroundStyle(WelcomePalette.ink)
                            HStack {
                                Text(group.kind.title(spanish))
                                Spacer()
                                Image(systemName: "arrow.up.right")
                            }.font(.caption).foregroundStyle(group.look.color)
                            if group.kind == .saving {
                                ProgressView(value: group.progress).tint(group.look.color)
                                Text(CuadraoCopy.text("copy.cuadraoGroupCollection.56832f422b", spanish: spanish, String(describing: Int(group.progress * 100)))).font(.caption).foregroundStyle(.secondary)
                            } else {
                                ViewThatFits(in: .horizontal) {
                                    HStack(spacing: 6) { shareLabel; shareAmount(group) }
                                    VStack(alignment: .leading, spacing: 4) { shareLabel; shareAmount(group) }
                                }.foregroundStyle(WelcomePalette.ink)
                            }
                        }.padding(.horizontal, 20).padding(.bottom, 20)
                    }.background(group.look.color.opacity(0.055), in: RoundedRectangle(cornerRadius: 28)).clipShape(RoundedRectangle(cornerRadius: 28))
            }
            if store.groups.allSatisfy(\.archived) {
                PlanPrimaryButton(title: CuadraoCopy.text("copy.cuadraoGroupCollection.f62cbfb5b0", spanish: spanish), symbol: "plus", action: create)
                    .accessibilityIdentifier("group-create")
            }
            NavigationLink {
                CuadraoArchivedGroups(store: store, spanish: spanish)
            } label: {
                Label(CuadraoCopy.text("copy.cuadraoSpacesSheet.e95aacbabf", spanish: spanish), systemImage: "archivebox")
                    .font(CuadraoTypography.supporting).foregroundStyle(.secondary).frame(minHeight: 44)
            }.accessibilityIdentifier("group-archives")
        }.sheet(item: $editing) { CuadraoGroupEditor(store: store, spanish: spanish, initial: $0) }
    }
    private var shareLabel: some View { Text(CuadraoCopy.text("copy.cuadraoGroupCollection.02522520f4", spanish: spanish)).font(CuadraoTypography.supporting) }
    private func shareAmount(_ group: PlanGroup) -> some View {
        Text(PlanFormat.amount(Double(group.share(group.me)) / 100, currency: group.currency)).font(CuadraoTypography.rowAmount)
    }
}

private struct CuadraoArchivedGroups: View {
    let store: CuadraoGroupPreview
    let spanish: Bool
    var body: some View {
        List {
            if store.groups.filter(\.archived).isEmpty {
                ContentUnavailableView(CuadraoCopy.text("copy.cuadraoGroupCollection.e07523e83a", spanish: spanish), systemImage: "archivebox")
            }
            ForEach(store.groups.filter(\.archived)) { group in
                HStack {
                    Text(group.name); Spacer()
                    Button(CuadraoCopy.text("copy.cuadraoGroupCollection.1ae3bf9797", spanish: spanish)) { store.archive(group.id, false) }.buttonStyle(.bordered)
                }
            }
        }.navigationTitle(CuadraoCopy.text("copy.cuadraoSpacesSheet.e95aacbabf", spanish: spanish)).navigationBarTitleDisplayMode(.inline)
            .toolbar(.visible, for: .navigationBar)
    }
}

struct PlanAvatarStack: View {
    let members: [PlanMember]
    var body: some View {
        HStack(spacing: -8) {
            ForEach(Array(members.prefix(4).enumerated()), id: \.element.id) { index, member in
                PlanMemberAvatar(member: member, index: index)
            }
            if members.count > 4 { Text("+\(members.count - 4)").font(.caption.bold()).padding(10).background(.regularMaterial, in: Circle()) }
        }.accessibilityElement(children: .ignore).accessibilityLabel(members.map(\.name).joined(separator: ", "))
    }
}
struct PlanMemberAvatar: View {
    let member: PlanMember
    var index = 0
    var body: some View {
        Image(systemName: member.symbol).font(.system(size: 16, weight: .medium))
            .foregroundStyle(CanvasPlanLook.allCases[index % 4].color)
            .frame(width: 38, height: 38)
            .background(WelcomePalette.background, in: Circle())
            .overlay { Circle().stroke(CanvasPlanLook.allCases[index % 4].color.opacity(0.2), lineWidth: 2) }
            .accessibilityLabel(member.name)
    }
}

struct PlanGroupArtwork: View {
    let look: CanvasPlanLook
    var progress: Double? = nil
    var cover: Data? = nil
    var body: some View {
        GeometryReader { g in
            ZStack {
                LinearGradient(colors: [look.color.opacity(0.1), look.color.opacity(0.35)], startPoint: .topLeading, endPoint: .bottomTrailing)
                Circle().fill(look.color.opacity(0.22)).frame(width: 115, height: 115).offset(x: g.size.width * 0.24, y: -22)
                Ellipse().fill(look.color.opacity(0.13)).frame(width: g.size.width * 1.4, height: 160).rotationEffect(.degrees(-18)).offset(y: 90)
                Ellipse().fill(look.color.opacity(0.24)).frame(width: g.size.width * 1.5, height: 120).rotationEffect(.degrees(12)).offset(y: 100)
                Image(systemName: look.symbol).font(.system(size: 65, weight: .ultraLight)).foregroundStyle(look.color.opacity(0.7))
                if let progress {
                    Circle().trim(from: 0, to: progress).stroke(look.color, style: StrokeStyle(lineWidth: 3, lineCap: .round))
                        .frame(width: 104, height: 104).rotationEffect(.degrees(-90))
                }
            }.overlay {
                if let cover, let image = UIImage(data: cover) {
                    Image(uiImage: image).resizable().scaledToFill().frame(width: g.size.width, height: g.size.height).clipped()
                }
            }.frame(width: g.size.width, height: g.size.height).clipped()
        }.accessibilityHidden(true)
    }
}
