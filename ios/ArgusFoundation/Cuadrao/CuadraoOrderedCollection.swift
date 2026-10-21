import SwiftUI

/// A swipe action a connected host puts in place of the Preview's Edit and Archive.
struct CuadraoCollectionSwipe: Identifiable {
    let id: String
    let title: String
    let symbol: String
    let tint: Color
    let action: () -> Void
}

/// One collection interaction vocabulary. State and persistence stay with the item owner.
struct CuadraoOrderedCollection<Item: Identifiable, Row: View>: View where Item.ID == UUID {
    let items: [Item]
    let spanish: Bool
    var spacing: CGFloat = 18
    let identifier: (Item) -> String
    let open: (Item) -> Void
    let edit: (Item) -> Void
    var canEdit: (Item) -> Bool = { _ in true }
    let archive: (Item) -> Void
    let reorder: ([UUID]) -> Void
    /// Connected hosts pass their own swipe sets; the Preview leaves these nil and keeps Edit and Archive.
    var leadingSwipes: ((Item) -> [CuadraoCollectionSwipe])?
    var trailingSwipes: ((Item) -> [CuadraoCollectionSwipe])?
    @ViewBuilder let row: (Item) -> Row

    var body: some View {
        if #available(iOS 27.0, *), !ProcessInfo.processInfo.arguments.contains("--legacy-collection") {
            VStack(spacing: spacing) {
                ForEach(items) { item in
                    itemButton(item)
                        .swipeActions(edge: .leading, allowsFullSwipe: false) {
                            if let custom = leadingSwipes?(item) { ForEach(custom) { swipeButton($0) } }
                            else if canEdit(item) { Button { edit(item) } label: { Image(systemName: "pencil") }.tint(.blue).accessibilityLabel(CuadraoCopy.text("copy.connectedCuadraoHome.2ddd4a589f", spanish: spanish)) }
                        }
                        .swipeActions(edge: .trailing, allowsFullSwipe: false) {
                            if let custom = trailingSwipes?(item) { ForEach(custom) { swipeButton($0) } }
                            else { Button { archive(item) } label: { Image(systemName: "archivebox") }.tint(.orange).accessibilityLabel(CuadraoCopy.text("copy.connectedCuadraoHome.0960027352", spanish: spanish)) }
                        }
                }.reorderable()
            }
            .reorderContainer(for: Item.self) { difference in
                switch difference.destination.position {
                case .before(let id): move(difference.sources, before: id)
                case .end: move(difference.sources, before: nil)
                @unknown default: break
                }
            }.swipeActionsContainer()
        } else {
            // Older systems keep explicit controls and native drag/drop; no competing hold menu.
            VStack(spacing: spacing) {
                ForEach(items) { item in
                    VStack(alignment: .leading, spacing: 0) {
                        itemButton(item)
                            .draggable(item.id.uuidString)
                            .dropDestination(for: String.self) { values, _ in
                                guard let value = values.first, let id = UUID(uuidString: value), items.contains(where: { $0.id == id }) else { return false }
                                move([id], before: item.id); return true
                            }
                        HStack {
                            if canEdit(item) { Button { edit(item) } label: { Label(CuadraoCopy.text("copy.connectedCuadraoHome.2ddd4a589f", spanish: spanish), systemImage: "pencil").frame(minHeight: 44).contentShape(Rectangle()) }.buttonStyle(.plain) }
                            Spacer()
                            Button { archive(item) } label: { Label(CuadraoCopy.text("copy.connectedCuadraoHome.0960027352", spanish: spanish), systemImage: "archivebox").frame(minHeight: 44).contentShape(Rectangle()) }.buttonStyle(.plain)
                        }.font(.caption).frame(minHeight: 44)
                    }
                }
            }
        }
    }
    private func swipeButton(_ swipe: CuadraoCollectionSwipe) -> some View {
        Button(action: swipe.action) { Image(systemName: swipe.symbol) }
            .tint(swipe.tint).accessibilityLabel(swipe.title).accessibilityIdentifier(swipe.id)
    }
    private func itemButton(_ item: Item) -> some View {
        Button { open(item) } label: { row(item).contentShape(Rectangle()) }
            .buttonStyle(.plain).accessibilityIdentifier(identifier(item))
            .accessibilityAction(named: Text(CuadraoCopy.text("copy.connectedCuadraoHome.0960027352", spanish: spanish))) { archive(item) }
            .accessibilityActions {
                ForEach((leadingSwipes?(item) ?? []) + (trailingSwipes?(item) ?? [])) { swipe in Button(swipe.title, action: swipe.action) }
                if leadingSwipes == nil, canEdit(item) { Button(CuadraoCopy.text("copy.connectedCuadraoHome.2ddd4a589f", spanish: spanish)) { edit(item) } }
                if items.first?.id != item.id {
                    Button(CuadraoCopy.text("copy.cuadraoAvatarCrop.117365a0d7", spanish: spanish)) { step(item.id, by: -1) }
                }
                if items.last?.id != item.id {
                    Button(CuadraoCopy.text("copy.cuadraoAvatarCrop.e45af00213", spanish: spanish)) { step(item.id, by: 1) }
                }
            }
    }
    private func step(_ id: UUID, by delta: Int) {
        var ids = items.map(\.id)
        guard let index = ids.firstIndex(of: id), ids.indices.contains(index + delta) else { return }
        ids.swapAt(index, index + delta); reorder(ids)
    }
    private func move(_ moving: [UUID], before destination: UUID?) {
        let current = items.map(\.id)
        guard !moving.isEmpty, Set(moving).isSubset(of: Set(current)), destination.map({ !moving.contains($0) }) ?? true else { return }
        var result = current.filter { !moving.contains($0) }
        let index = destination.flatMap { result.firstIndex(of: $0) } ?? result.endIndex
        result.insert(contentsOf: current.filter { moving.contains($0) }, at: index)
        reorder(result)
    }
}
