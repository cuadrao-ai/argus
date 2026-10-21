import Foundation
import Observation

// Fictional, device-local collaboration. No invites, payments or financial APIs.
struct PlanMember: Identifiable, Codable, Equatable {
    var id = UUID()
    var name: String
    var symbol: String
}
struct PlanSharedExpense: Identifiable, Codable, Equatable {
    var id = UUID()
    var title: String
    var cents: Int
    var payer: UUID
    var shares: [UUID: Int]
    var draft = false
    var receipt: Data?
    var receiptID: UUID?
    static func equal(_ cents: Int, among members: [UUID]) -> [UUID: Int] {
        guard cents >= 0, !members.isEmpty else { return [:] }
        return Dictionary(uniqueKeysWithValues: members.enumerated().map { ($0.element, cents / members.count + ($0.offset < cents % members.count ? 1 : 0)) })
    }
}
struct PlanRepayment: Identifiable, Codable, Equatable {
    var id = UUID()
    var from: UUID
    var to: UUID
    var cents: Int
}
enum PlanGroupKind: String, Codable, CaseIterable {
    case trip, saving
    func title(_ es: Bool) -> String { self == .trip ? (CuadraoCopy.text("copy.cuadraoGroupPreview.93325ee3fe", spanish: es)) : (CuadraoCopy.text("copy.cuadraoGroupPreview.e442bef193", spanish: es)) }
}
struct PlanGroup: Identifiable, Codable, Equatable {
    var id = UUID()
    var name: String
    var kind: PlanGroupKind = .trip
    var currency = "DOP"
    var look: CanvasPlanLook = .coast
    var cover: Data?
    var members: [PlanMember]
    var estimatedCents: Int = 4800000
    var expectedPeople = 8
    var expenses: [PlanSharedExpense] = []
    var repayments: [PlanRepayment] = []
    var archived = false
    var removedMemberIDs: [UUID] = []
    var activeMembers: [PlanMember] { members.filter { !removedMemberIDs.contains($0.id) } }
    var me: UUID { members[0].id }
    func canRemove(_ id: UUID) -> Bool { id != me && balance(id) == 0 && activeMembers.contains { $0.id == id } }

    var total: Int { expenses.filter { !$0.draft }.reduce(0) { $0 + $1.cents } }
    func paid(_ id: UUID) -> Int { expenses.filter { !$0.draft && $0.payer == id }.reduce(0) { $0 + $1.cents } }
    func share(_ id: UUID) -> Int { expenses.filter { !$0.draft }.reduce(0) { $0 + ($1.shares[id] ?? 0) } }
    func balance(_ id: UUID) -> Int {
        paid(id) - share(id) + repayments.filter { $0.from == id }.reduce(0) { $0 + $1.cents }
        - repayments.filter { $0.to == id }.reduce(0) { $0 + $1.cents }
    }
    var progress: Double { min(1, Double(total) / Double(max(1, estimatedCents))) }
    var valid: Bool {
        PlanCurrency.supported.contains(currency) && !name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && !members.isEmpty && estimatedCents > 0 && expectedPeople > 0
    }
    mutating func record(_ expense: PlanSharedExpense) -> Bool {
        let ids = Set(members.map(\.id))
        guard expense.cents >= (expense.draft ? 0 : 1), expense.cents <= CanvasMoney.maximumCents, ids.contains(expense.payer),
              !expense.title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              expense.draft || (expense.shares.values.allSatisfy { $0 >= 0 } && Set(expense.shares.keys).isSubset(of: ids)
                && expense.shares.values.reduce(0, +) == expense.cents) else { return false }
        if let index = expenses.firstIndex(where: { $0.id == expense.id }) { expenses[index] = expense }
        else { expenses.append(expense) }
        return true
    }
    mutating func repay(from: UUID, to: UUID, cents: Int) -> Bool {
        guard from != to, cents > 0, cents <= -balance(from), cents <= balance(to) else { return false }
        repayments.append(.init(from: from, to: to, cents: cents)); return true
    }
}

// Earlier previews supported DOP only. Preserve those saved groups and amounts.
extension PlanGroup {
    enum CodingKeys: String, CodingKey {
        case id, name, kind, currency, look, cover, members, estimatedCents, expectedPeople, expenses, repayments, archived, removedMemberIDs
    }
    init(from decoder: Decoder) throws {
        let saved = try decoder.container(keyedBy: CodingKeys.self)
        id = try saved.decode(UUID.self, forKey: .id)
        name = try saved.decode(String.self, forKey: .name)
        kind = try saved.decode(PlanGroupKind.self, forKey: .kind)
        currency = try saved.decodeIfPresent(String.self, forKey: .currency) ?? "DOP"
        look = try saved.decode(CanvasPlanLook.self, forKey: .look)
        cover = try saved.decodeIfPresent(Data.self, forKey: .cover)
        members = try saved.decode([PlanMember].self, forKey: .members)
        estimatedCents = try saved.decode(Int.self, forKey: .estimatedCents)
        expectedPeople = try saved.decode(Int.self, forKey: .expectedPeople)
        expenses = try saved.decode([PlanSharedExpense].self, forKey: .expenses)
        repayments = try saved.decode([PlanRepayment].self, forKey: .repayments)
        archived = try saved.decode(Bool.self, forKey: .archived)
        removedMemberIDs = try saved.decodeIfPresent([UUID].self, forKey: .removedMemberIDs) ?? []
    }
}

@Observable final class CuadraoGroupPreview {
    var groups: [PlanGroup] = []
    // Local design role scenario, not an authorization contract.
    var canManage: Bool { !ProcessInfo.processInfo.arguments.contains("--group-member") }
    func removeMember(_ memberID: UUID, from groupID: UUID) {
        guard canManage, var group = group(groupID), group.canRemove(memberID) else { return }
        group.removedMemberIDs.append(memberID); save(group)
    }

    private let defaults: UserDefaults?
    private let storageURL: URL?
    private(set) var loadFailed = false
    private let key = "cuadrao.design.groups.v1"
    init(spanish: Bool, defaults: UserDefaults? = .standard, reset: Bool = false, empty: Bool = false, storageURL: URL? = nil) {
        // Standard defaults and the default file persist only in the design preview.
        self.defaults = defaults === UserDefaults.standard && !CuadraoDesignPreview.isActive ? nil : defaults
        self.storageURL = storageURL ?? (self.defaults !== UserDefaults.standard ? nil : FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0].appendingPathComponent("cuadrao-groups.json"))
        if !reset, !empty, let storageURL = self.storageURL, FileManager.default.fileExists(atPath: storageURL.path) {
            do { groups = try JSONDecoder().decode([PlanGroup].self, from: Data(contentsOf: storageURL)) }
            catch { loadFailed = true }
        } else if !reset, !empty, let data = self.defaults?.data(forKey: key), let saved = try? JSONDecoder().decode([PlanGroup].self, from: data) {
            groups = saved
            persist()
        } else { resetExamples(spanish: spanish, empty: empty) }
    }
    func group(_ id: UUID) -> PlanGroup? { groups.first { $0.id == id } }
    func save(_ group: PlanGroup) {
        guard group.valid, self.group(group.id).map({ $0.currency == group.currency }) ?? true else { return }
        if let i = groups.firstIndex(where: { $0.id == group.id }) { groups[i] = group } else { groups.append(group) }
        persist()
    }
    func reorder(_ ids: [UUID]) {
        guard Set(ids) == Set(groups.filter { !$0.archived }.map(\.id)) else { return }
        groups = CuadraoCollectionOrder.applying(ids, to: groups); persist()
    }
    func archive(_ id: UUID, _ archived: Bool) {
        guard var group = group(id) else { return }; group.archived = archived; save(group)
    }
    func resetExamples(spanish es: Bool, empty: Bool = false) {
        let members = [PlanMember(name: CuadraoCopy.text("copy.cuadraoGroupPreview.df8578d82b", spanish: es), symbol: "sun.max.fill"), .init(name: "Ana", symbol: "leaf.fill"), .init(name: "Leo", symbol: "moon.fill"), .init(name: "Sol", symbol: "sparkle")]
        var trip = PlanGroup(name: CuadraoCopy.text("copy.cuadraoGroupPreview.bc28d3beb6", spanish: es), members: members)
        _ = trip.record(.init(title: CuadraoCopy.text("copy.cuadraoGroupPreview.d180480ca4", spanish: es), cents: 1200000, payer: members[0].id, shares: PlanSharedExpense.equal(1200000, among: members.map(\.id))))
        var saving = PlanGroup(name: CuadraoCopy.text("copy.cuadraoGroupPreview.0d8bb02894", spanish: es), kind: .saving, look: .sunshine, members: members, estimatedCents: 8000000, expectedPeople: 4)
        _ = saving.record(.init(title: CuadraoCopy.text("copy.cuadraoGroupPreview.dbea0f2ca6", spanish: es), cents: 1000000, payer: members[0].id, shares: [members[0].id: 1000000]))
        groups = empty ? [] : [trip, saving]; persist()
    }
    func confirmReceipt(_ draft: ReceiptDraft, groupID: UUID) throws {
        guard var group = group(groupID), group.kind == .trip, group.currency == draft.currency else { throw ReceiptError.destination }
        if let existing = group.expenses.first(where: { $0.id == draft.id }) {
            guard existing.receiptID == draft.id, !existing.draft else { throw ReceiptError.destination }
            return
        }
        guard let payer = draft.payer, group.activeMembers.contains(where: { $0.id == payer }) else { throw ReceiptError.destination }
        let shares = try draft.shares(roster: group.activeMembers.map(\.id))
        let expense = PlanSharedExpense(id: draft.id, title: draft.merchant, cents: draft.total,
                                       payer: payer, shares: shares, receiptID: draft.id)
        guard group.record(expense) else { throw ReceiptError.incomplete }
        let updated = groups.map { $0.id == groupID ? group : $0 }
        try write(updated)
        groups = updated
    }
    private func write(_ values: [PlanGroup]) throws {
        guard !loadFailed else { throw ReceiptError.missing }
        let data = try JSONEncoder().encode(values)
        if let storageURL {
            try FileManager.default.createDirectory(at: storageURL.deletingLastPathComponent(), withIntermediateDirectories: true)
            try data.write(to: storageURL, options: .atomic)
        }
        if storageURL == nil { defaults?.set(data, forKey: key) }
    }
    private func persist() { try? write(groups) }
}
