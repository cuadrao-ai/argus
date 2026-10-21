import SwiftUI

// Presentation fixtures only; these are not household authorization contracts.
enum CanvasSpaceKind: String, CaseIterable, Identifiable {
    case personal, household, business, custom
    var id: String { rawValue }
    func title(_ es: Bool) -> String {
        switch self {
        case .personal: CuadraoCopy.text("context.personal", spanish: es)
        case .household: CuadraoCopy.text("copy.cuadraoSpacesPreview.b845d91db6", spanish: es)
        case .business: CuadraoCopy.text("copy.cuadraoSpacesPreview.2d7db3e0c9", spanish: es)
        case .custom: CuadraoCopy.text("copy.cuadraoSpacesPreview.28600a1682", spanish: es)
        }
    }
    var symbol: String {
        switch self {
        case .personal: "person"
        case .household: "person.2"
        case .business: "briefcase"
        case .custom: "square.grid.2x2"
        }
    }
}

struct CanvasSpace: Identifiable {
    static let personalID = "personal"
    static let householdID = "household"
    var id = UUID().uuidString
    let kind: CanvasSpaceKind
    var name: String
    var archived = false
    var deleted = false
    var isPrivate: Bool { kind == .business || kind == .custom }
    func title(_ es: Bool) -> String { name.isEmpty ? kind.title(es) : name }
}

extension CuadraoAccountsPreview {
    var selectedSpace: CanvasSpace { spaces.first { $0.id == selectedSpaceID }! }
    var visibleSpaces: [CanvasSpace] { spaces.filter { !$0.archived && !$0.deleted } }
    var scopedAccounts: [CanvasAccount] {
        accounts.filter { account in
            if selectedSpace.kind == .household { return account.sharedWithHousehold }
            if selectedSpace.kind == .personal {
                return account.spaceID == CanvasSpace.personalID || account.spaceID == CanvasSpace.householdID
            }
            return account.spaceID == selectedSpaceID
        }
    }
    var visibleActivity: [CanvasActivity] {
        let ids = Set(scopedAccounts.map(\.id))
        return activity.filter { ids.contains($0.accountID) }.sorted { $0.date > $1.date }
    }
    func spaceNameAvailable(_ name: String, except id: String? = nil) -> Bool {
        let candidate = name.trimmingCharacters(in: .whitespacesAndNewlines)
        let reserved = ["personal", "hogar", "household"]
        return !candidate.isEmpty && !reserved.contains(candidate.lowercased()) && !spaces.contains {
            $0.id != id && $0.name.compare(candidate, options: [.caseInsensitive, .diacriticInsensitive]) == .orderedSame
        }
    }
    func openHousehold() {
        if !spaces.contains(where: { $0.id == CanvasSpace.householdID }) {
            spaces.append(CanvasSpace(id: CanvasSpace.householdID, kind: .household, name: ""))
        }
        selectedSpaceID = CanvasSpace.householdID
    }
    func saveSpace(kind: CanvasSpaceKind, name: String, existing: CanvasSpace?) {
        let trimmed = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard spaceNameAvailable(trimmed, except: existing?.id) else { return }
        if let existing, let index = spaces.firstIndex(where: { $0.id == existing.id }) {
            spaces[index].name = trimmed
        } else {
            let space = CanvasSpace(kind: kind, name: trimmed)
            spaces.append(space); selectedSpaceID = space.id
        }
    }
    func archiveSpace(_ id: String, archived: Bool) {
        guard let i = spaces.firstIndex(where: { $0.id == id }), spaces[i].isPrivate else { return }
        spaces[i].archived = archived
        if archived && selectedSpaceID == id { selectedSpaceID = CanvasSpace.personalID }
    }
    func canDeleteSpace(_ space: CanvasSpace) -> Bool {
        space.isPrivate && !accounts.contains { $0.spaceID == space.id }
    }
    func deleteSpace(_ space: CanvasSpace) {
        guard canDeleteSpace(space), let i = spaces.firstIndex(where: { $0.id == space.id }) else { return }
        spaces[i].deleted = true
        if selectedSpaceID == space.id { selectedSpaceID = CanvasSpace.personalID }
    }
    func restoreSpace(_ id: String) {
        guard let i = spaces.firstIndex(where: { $0.id == id }) else { return }
        spaces[i].deleted = false; spaces[i].archived = false
    }
}
