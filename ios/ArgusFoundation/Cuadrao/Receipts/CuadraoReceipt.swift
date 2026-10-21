import Foundation

struct ReceiptOrigin: Codable, Equatable {
    let groupID: UUID?
    let threadID: String?
}

enum ReceiptDestination: Codable, Equatable {
    case personal(accountID: UUID?)
    case group(UUID)
}

enum ReceiptLifecycle: Codable, Equatable {
    case prepared
    case confirmed
}

struct ReceiptSource: Codable, Equatable {
    let filename: String
    let name: String
    let pdf: Bool
}

struct ReceiptLocation: Codable, Equatable {
    var recordedAt = Date.now
    let latitude: Double
    let longitude: Double
}

struct ReceiptLine: Identifiable, Codable, Equatable {
    var id = UUID()
    var name: String
    var quantity = 1
    var unitCents: Int
    var members: Set<UUID> = []
    var cents: Int { quantity * unitCents }
}

enum ReceiptSplit: String, Codable { case equal, items }

struct ReceiptDraft: Identifiable, Codable, Equatable {
    var id = UUID()
    var currency: String?
    let origin: ReceiptOrigin
    let source: [ReceiptSource]
    let example: Bool
    var merchant = ""
    var date = Date.now
    var category = "other"
    var lines: [ReceiptLine] = []
    var taxCents = 0
    var serviceCents = 0
    var addedTipCents = 0
    var captureLocation: ReceiptLocation?
    var destination: ReceiptDestination
    var payer: UUID?
    var participants: Set<UUID> = []
    var split = ReceiptSplit.equal
    var lifecycle = ReceiptLifecycle.prepared
    var updatedAt = Date.now
    var subtotal: Int { lines.reduce(0) { $0 + $1.cents } }
    var includedCharges: Int { taxCents + serviceCents }
    var receiptTotal: Int { subtotal + includedCharges }
    var total: Int { receiptTotal + addedTipCents }
    var prepared: Bool { lifecycle == .prepared }
    var groupID: UUID? { if case .group(let id) = destination { id } else { nil } }
    var unassigned: Int { split == .items ? lines.filter { $0.members.intersection(participants).isEmpty }.count : 0 }

    func validate() throws {
        guard let currency, PlanCurrency.supported.contains(currency) else { throw ReceiptError.currency }
        guard !merchant.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              !lines.isEmpty, lines.count <= 100,
              lines.allSatisfy({ !$0.name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && (1...999).contains($0.quantity) && (0...CanvasMoney.maximumCents).contains($0.unitCents) }),
              [taxCents, serviceCents, addedTipCents].allSatisfy({ (0...CanvasMoney.maximumCents).contains($0) }),
              total > 0, total <= CanvasMoney.maximumCents else { throw ReceiptError.incomplete }
    }

    func shares(roster: [UUID]) throws -> [UUID: Int] {
        try validate()
        let members = roster.filter { participants.contains($0) }
        guard !members.isEmpty, Set(members) == participants else { throw ReceiptError.participants }
        if split == .equal { return Self.divide(total, among: members) }
        var result = Dictionary(uniqueKeysWithValues: members.map { ($0, 0) })
        for line in lines {
            let assigned = members.filter { line.members.contains($0) }
            guard !assigned.isEmpty, line.members.isSubset(of: participants) else { throw ReceiptError.unassigned }
            for (id, cents) in Self.divide(line.cents, among: assigned) { result[id, default: 0] += cents }
        }
        let charges = includedCharges + addedTipCents
        guard subtotal > 0 else { throw ReceiptError.incomplete }
        let weighted = members.map { (id: $0, numerator: Int64(result[$0, default: 0]) * Int64(charges)) }
        var remainder = charges
        for entry in weighted {
            let cents = Int(entry.numerator / Int64(subtotal))
            result[entry.id, default: 0] += cents; remainder -= cents
        }
        let order = weighted.enumerated().sorted {
            let a = $0.element.numerator % Int64(subtotal), b = $1.element.numerator % Int64(subtotal)
            return a == b ? $0.offset < $1.offset : a > b
        }
        for entry in order.prefix(remainder) { result[entry.element.id, default: 0] += 1 }
        return result
    }

    static func divide(_ cents: Int, among members: [UUID]) -> [UUID: Int] {
        guard !members.isEmpty else { return [:] }
        return Dictionary(uniqueKeysWithValues: members.enumerated().map { ($0.element, cents / members.count + ($0.offset < cents % members.count ? 1 : 0)) })
    }
}

enum ReceiptError: Error {
    case incomplete, participants, unassigned, destination, source, confirmed, missing, currency
    func message(_ es: Bool) -> String {
        switch self {
        case .currency: CuadraoCopy.text("copy.cuadraoReceipt.f415b69dcc", spanish: es)
        case .incomplete: CuadraoCopy.text("copy.cuadraoReceipt.b3d298d7b3", spanish: es)
        case .participants: CuadraoCopy.text("copy.cuadraoReceipt.9f36f3e95a", spanish: es)
        case .unassigned: CuadraoCopy.text("copy.cuadraoReceipt.3e63f3a0bf", spanish: es)
        case .destination: CuadraoCopy.text("copy.cuadraoReceipt.223df8fe4b", spanish: es)
        case .source: CuadraoCopy.text("copy.cuadraoReceipt.9af3b14b7d", spanish: es)
        case .confirmed: CuadraoCopy.text("copy.cuadraoReceipt.860cb27a47", spanish: es)
        case .missing: CuadraoCopy.text("copy.cuadraoReceipt.d381517ce5", spanish: es)
        }
    }
}

struct ReceiptSample {
    let merchant = "La Mesa"
    let category = "food"
    let lines: [ReceiptLine]
    let taxCents = 40680
    let serviceCents = 22600
    var subtotal: Int { lines.reduce(0) { $0 + $1.cents } }
    var total: Int { subtotal + taxCents + serviceCents }
    init(spanish: Bool) {
        lines = [.init(name: CuadraoCopy.text("copy.cuadraoReceipt.82da86a2d2", spanish: spanish), quantity: 2, unitCents: 65000),
                 .init(name: CuadraoCopy.text("copy.cuadraoReceipt.0d55531462", spanish: spanish), unitCents: 42000),
                 .init(name: CuadraoCopy.text("copy.cuadraoReceipt.7397a7cf3f", spanish: spanish), quantity: 3, unitCents: 18000)]
    }
}
