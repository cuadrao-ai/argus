import SwiftUI
import CuadraoBook

/// One movement as a feed row. Tapping opens it; swipes edit and delete, and both are also accessibility actions.
struct GuestMovementRow: View {
    let movement: Movement
    let book: DeviceBook
    var perspective: UUID?
    let spanish: Bool
    let open: () -> Void
    let edit: () -> Void
    let delete: () -> Void
    @Environment(\.locale) private var locale

    var body: some View {
        let row = GuestMovementPresentation.row(movement, in: book, perspective: perspective, spanish: spanish, locale: locale)
        ConnectedSwipeRow(
            leading: [ConnectedSwipeAction(id: "guest.movement.swipe.edit", title: spanish ? "Editar" : "Edit", symbol: "pencil", tint: .blue, action: edit)],
            trailing: [ConnectedSwipeAction(id: "guest.movement.swipe.delete", title: spanish ? "Eliminar" : "Delete", symbol: "trash", tint: .red, action: delete)]
        ) {
            Button(action: open) {
                CuadraoFeedRow(title: row.title, detail: row.detail, amount: row.amount, icon: row.icon)
            }
            .buttonStyle(.plain)
            .accessibilityElement(children: .combine)
            .accessibilityIdentifier("guest.movement.row." + movement.id.uuidString)
        }
    }
}

/// Home's Activity section: the newest movements, with a way to add one.
struct GuestActivitySection: View {
    @ObservedObject var model: GuestBookModel
    let spanish: Bool
    let open: (UUID) -> Void
    let add: () -> Void
    let edit: (UUID) -> Void
    let delete: (UUID) -> Void

    private var recent: [Movement] { Array(model.book.liveMovements().prefix(8)) }

    var body: some View {
        if !model.book.activeAccounts.isEmpty {
            VStack(alignment: .leading, spacing: 16) {
                HStack {
                    Text(spanish ? "Movimientos" : "Activity").font(CuadraoTypography.section).accessibilityAddTraits(.isHeader)
                    Spacer()
                    CuadraoSectionAddButton(title: spanish ? "Añadir movimiento" : "Add activity", action: add)
                        .accessibilityIdentifier("home.record")
                }
                if recent.isEmpty {
                    Text(spanish ? "Aún no hay movimientos. Añade el primero con el botón +." : "No activity yet. Add the first with the + button.")
                        .font(.subheadline).foregroundStyle(.secondary).accessibilityIdentifier("guest.activity.empty")
                } else {
                    VStack(spacing: 0) {
                        ForEach(recent) { movement in
                            GuestMovementRow(movement: movement, book: model.book, spanish: spanish,
                                open: { open(movement.id) }, edit: { edit(movement.id) }, delete: { delete(movement.id) })
                        }
                    }.connectedSwipeContainer()
                }
            }
        }
    }
}

/// One movement in full, with the two things the book can do to it.
struct GuestMovementDetail: View {
    @ObservedObject var model: GuestBookModel
    let id: UUID
    let spanish: Bool
    let edit: () -> Void
    let delete: () -> Void
    @Environment(\.locale) private var locale

    var body: some View {
        if let movement = model.book.movement(id), !movement.deleted {
            let book = model.book
            let currency = book.account(movement.accountID)?.currency ?? ""
            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    VStack(alignment: .leading, spacing: 8) {
                        Text(GuestMovementPresentation.title(movement, spanish: spanish)).font(CuadraoTypography.screen)
                            .accessibilityIdentifier("guest.movement.title")
                        HStack(alignment: .firstTextBaseline, spacing: 9) {
                            Text(currency).font(.subheadline).foregroundStyle(.secondary)
                            Text(GuestMovementPresentation.sign(movement, perspective: nil) + GuestMovementPresentation.amount(movement, in: book, locale: locale))
                                .font(CuadraoTypography.amount).monospacedDigit().lineLimit(1).minimumScaleFactor(0.6)
                                .accessibilityIdentifier("guest.movement.amount.value")
                        }
                    }
                    VStack(spacing: 0) {
                        line(spanish ? "Tipo" : "Type", GuestMovementPresentation.kindTitle(movement.kind, spanish: spanish))
                        line(movement.kind == .transfer ? (spanish ? "Desde" : "From") : (spanish ? "Cuenta" : "Account"),
                             GuestMovementPresentation.accountTitle(movement.accountID, in: book, spanish: spanish))
                        if movement.kind == .transfer {
                            line(spanish ? "Hacia" : "To", GuestMovementPresentation.accountTitle(movement.counterpartID, in: book, spanish: spanish))
                        }
                        line(spanish ? "Fecha" : "Date", GuestMovementPresentation.date(movement, locale: locale, style: .long))
                        if let category = movement.category {
                            line(spanish ? "Categoría" : "Category", GuestMovementPresentation.categoryTitle(category, spanish: spanish))
                        }
                    }
                    VStack(spacing: 0) {
                        CanvasActionRow(title: spanish ? "Editar movimiento" : "Edit transaction", symbol: "pencil", action: edit)
                            .accessibilityIdentifier("guest.movement.edit")
                        Divider()
                        CanvasActionRow(title: spanish ? "Eliminar movimiento" : "Delete transaction", symbol: "trash", action: delete)
                            .foregroundStyle(.red).accessibilityIdentifier("guest.movement.delete")
                    }
                }.padding(24)
            }
            .accessibilityIdentifier("guest.movement.detail")
            .background(WelcomePalette.background)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar(.visible, for: .navigationBar)
        }
    }

    private func line(_ label: String, _ value: String) -> some View {
        VStack(spacing: 0) {
            HStack(alignment: .firstTextBaseline) {
                Text(label).foregroundStyle(.secondary)
                Spacer(minLength: 16)
                Text(value).multilineTextAlignment(.trailing)
            }.font(.body).padding(.vertical, 14)
            Divider()
        }.accessibilityElement(children: .combine)
    }
}
