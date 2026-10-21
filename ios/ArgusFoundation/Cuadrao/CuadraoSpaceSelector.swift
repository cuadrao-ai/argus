import SwiftUI

struct CuadraoSpaceSelector: View {
    let data: CuadraoAccountsPreview
    let spanish: Bool
    let add: () -> Void
    var body: some View {
        CuadraoSpaceSelectorLayout(selection: data.selectedSpaceID,
            addTitle: CuadraoCopy.text("copy.cuadraoSpaceSelector.b50b0f7adc", spanish: spanish),
            addIdentifier: "cuadrao-spaces-add", add: add) {
            ForEach(data.visibleSpaces) { space in
                Button { data.selectedSpaceID = space.id } label: {
                    CuadraoSpaceLabel(title: space.title(spanish), selected: data.selectedSpaceID == space.id)
                        .contentShape(Rectangle())
                }.buttonStyle(.plain).id(space.id)
                    .accessibilityAddTraits(data.selectedSpaceID == space.id ? [.isSelected] : [])
                    .accessibilityIdentifier("cuadrao-space-" + space.id)
            }
        }
    }
}

struct CuadraoSpaceLabel: View {
    let title: String
    let selected: Bool
    var body: some View {
        Text(title)
            .font(.subheadline.weight(selected ? .semibold : .regular))
            .foregroundStyle(selected ? Color.primary : Color.secondary)
            .frame(minHeight: 44).contentShape(Rectangle())
    }
}

/// An available way in, not a space yet: the plus and pine tint say "add", where grey would read as locked.
struct CuadraoSpaceAddLabel: View {
    let title: String
    var body: some View {
        HStack(spacing: 4) {
            Image(systemName: "plus").font(.footnote.weight(.semibold)).accessibilityHidden(true)
            Text(title).font(.subheadline.weight(.medium))
        }.foregroundStyle(WelcomePalette.pine).frame(minHeight: 44).contentShape(Rectangle())
    }
}

struct CuadraoSpaceSelectorLayout<Content: View>: View {
    let selection: String
    let addTitle: String
    let addIdentifier: String
    /// Release builds with no other space to add leave the trailing plus out; Debug and the Preview keep it.
    var showsAdd = true
    let add: () -> Void
    @ViewBuilder let content: () -> Content
    var body: some View {
        HStack(spacing: 4) {
            ScrollViewReader { proxy in
                ScrollView(.horizontal) {
                    HStack(spacing: 24, content: content)
                }.scrollIndicators(.hidden)
                    .onChange(of: selection) { _, id in proxy.scrollTo(id) }
            }
            if showsAdd {
                CuadraoSectionAddButton(title: addTitle, action: add)
                    .accessibilityLabel(addTitle)
                    .accessibilityIdentifier(addIdentifier)
            }
        }
    }
}
