import SwiftUI
import CuadraoBook

/// Where Home's navigation stack can go: an account, or one movement.
enum GuestRoute: Hashable {
    case account(UUID)
    case movement(UUID)
}

/// Every sheet the book's Home and its detail screens can open.
enum GuestSheet: Identifiable, Equatable {
    case account(GuestAccountSheet.Mode)
    case movement(GuestMovementSheet.Mode)
    case archive(UUID)
    case archived
    case plan(GuestPlanSheet.Mode)
    case contribution(UUID)

    var id: String {
        switch self {
        case .account(let mode): "account." + mode.id
        case .movement(let mode): "movement." + mode.id
        case .archive(let id): "archive." + id.uuidString
        case .archived: "archived"
        case .plan(let mode): "plan." + mode.id
        case .contribution(let id): "contribution." + id.uuidString
        }
    }
}

/// Home for the on-device book, built from the shared Home layout. It reads the book and nothing else.
struct GuestHome: View {
    @ObservedObject var model: GuestBookModel
    let scroll: CuadraoNavigationScroll
    let active: Bool
    @Binding var path: [GuestRoute]
    @Binding var sheet: GuestSheet?
    @State private var archivedID: UUID?
    @State private var deletedID: UUID?
    @Environment(\.locale) private var locale

    private var spanish: Bool { locale.language.languageCode?.identifier == "es" }

    var body: some View {
        NavigationStack(path: $path) {
            CuadraoHomeLayout(order: [.overview, .accounts, .activity], canCustomize: false, spanish: spanish, customize: {}) {
                CuadraoHomeGreeting(name: "", spanish: spanish)
                Text(spanish ? "Este iPhone" : "This iPhone")
                    .font(.subheadline.weight(.semibold)).foregroundStyle(.secondary).frame(minHeight: 44)
                    .accessibilityIdentifier("guest.home.space")
            } notice: {
                if model.saveFailed {
                    Text(spanish ? "No se pudo guardar en este iPhone. Tus cambios siguen aquí mientras la app esté abierta."
                         : "Couldn't save on this iPhone. Your changes stay here while the app is open.")
                        .font(.footnote).foregroundStyle(.secondary).accessibilityIdentifier("guest.home.saveFailed")
                }
            } section: { section in
                switch section {
                case .overview:
                    GuestOverview(model: model, spanish: spanish)
                case .accounts:
                    GuestAccountsSection(model: model, spanish: spanish,
                        open: { path.append(.account($0)) }, add: { sheet = .account(.create) },
                        edit: { sheet = .account(.edit($0)) }, archive: { sheet = .archive($0) },
                        showArchived: { sheet = .archived })
                case .activity:
                    GuestActivitySection(model: model, spanish: spanish,
                        open: { path.append(.movement($0)) }, add: { sheet = .movement(.create(account: nil)) },
                        edit: { sheet = .movement(.edit($0)) }, delete: { delete($0) })
                case .upcoming:
                    EmptyView()
                }
            }
            .accessibilityIdentifier("screen.home")
            .modifier(CuadraoNavigationScrollObserver(scroll: scroll, enabled: active && path.isEmpty && sheet == nil))
            .background(WelcomePalette.background)
            .toolbar(.hidden, for: .navigationBar)
            .navigationDestination(for: GuestRoute.self) { route in
                switch route {
                case .account(let id):
                    GuestAccountDetail(model: model, id: id, spanish: spanish,
                        add: { sheet = .movement(.create(account: id)) },
                        open: { path.append(.movement($0)) },
                        editMovement: { sheet = .movement(.edit($0)) }, deleteMovement: { delete($0) },
                        edit: { sheet = .account(.edit(id)) },
                        archive: { sheet = .archive(id) },
                        restore: { restore(id) })
                case .movement(let id):
                    GuestMovementDetail(model: model, id: id, spanish: spanish,
                        edit: { sheet = .movement(.edit(id)) }, delete: { delete(id); path = Array(path.dropLast()) })
                }
            }
        }
        .overlay(alignment: .bottom) {
            if let archivedID, path.isEmpty, model.book.account(archivedID)?.archived == true {
                CuadraoArchivedAccountToast(spanish: spanish, undo: { restore(archivedID) }, close: { self.archivedID = nil })
            } else if let deletedID, model.book.movement(deletedID)?.deleted == true {
                GuestUndoToast(message: spanish ? "Movimiento eliminado" : "Transaction deleted", spanish: spanish,
                               undo: { undelete(deletedID) }, close: { self.deletedID = nil })
            }
        }
        .onChange(of: sheet) { previous, current in
            // A confirmed archive arrives as the sheet closing after the book changed.
            if case .archive(let id)? = previous, current == nil, model.book.account(id)?.archived == true {
                path = []
                archivedID = id
            }
        }
    }

    private func restore(_ id: UUID) {
        _ = try? model.apply { try $0.settingArchived(id, false) }
        if archivedID == id { archivedID = nil }
    }

    private func delete(_ id: UUID) {
        guard (try? model.apply { try $0.settingMovementDeleted(id, true) }) != nil else { return }
        deletedID = id
    }

    private func undelete(_ id: UUID) {
        _ = try? model.apply { try $0.settingMovementDeleted(id, false) }
        deletedID = nil
    }
}
