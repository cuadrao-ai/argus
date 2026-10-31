import Foundation
import Testing
@testable import CuadraoBook

/// Package files, found from this file so the tests read the same vectors the server's pytest reads.
enum PackageFiles {
    static let root = URL(fileURLWithPath: #filePath)
        .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()

    static func json(_ path: String) throws -> Any {
        try JSONSerialization.jsonObject(with: Data(contentsOf: root.appendingPathComponent(path)))
    }

    static func text(_ path: String) throws -> String {
        try String(contentsOf: root.appendingPathComponent(path), encoding: .utf8)
    }
}

@Suite("Conformance vectors shared with the server")
struct ConformanceTests {
    private var vectors: [String: Any] { get throws { try #require(PackageFiles.json("Vectors/conformance.json") as? [String: Any]) } }

    @Test func parsingMatchesTheServerParser() throws {
        let rows = try #require(vectors["parse"] as? [[String: Any]])
        #expect(rows.count > 20)
        for row in rows {
            let text = try #require(row["text"] as? String)
            let digits = try #require(row["digits"] as? Int)
            let result = MoneyParser.parse(text, digits: digits)
            if let minor = row["minor"] as? NSNumber {
                #expect(result == .success(minor.int64Value), "\(text) at \(digits) digits")
            } else {
                let code = try #require(row["error"] as? String)
                switch result {
                case .success(let value): Issue.record("\(text) should fail with \(code), got \(value)")
                case .failure(let error): #expect(Self.code(error) == code, "\(text) at \(digits) digits")
                }
            }
        }
    }

    @Test func formattingMatchesTheServerFormatter() throws {
        let rows = try #require(vectors["format"] as? [[String: Any]])
        for row in rows {
            let minor = try #require(row["minor"] as? NSNumber).int64Value
            let digits = try #require(row["digits"] as? Int)
            #expect(MoneyFormatter.plain(minor, digits: digits) == (row["text"] as? String), "\(minor) at \(digits) digits")
        }
    }

    @Test func shareMatchesTheServerRounding() throws {
        let rows = try #require(vectors["share"] as? [[String: Any]])
        for row in rows {
            let amount = try #require(row["amount"] as? NSNumber).int64Value
            let bps = try #require(row["bps"] as? Int)
            let expected = (row["result"] as? NSNumber)?.int64Value
            #expect(Ownership.share(of: amount, bps: bps) == expected, "\(amount) at \(bps) bps")
        }
    }

    @Test func categoriesMatchTheServerList() throws {
        let ids = try #require(vectors["categories"] as? [String])
        #expect(ExpenseCategory.allCases.map(\.rawValue) == ids)
    }

    @Test func currencyTableMatchesTheServerSet() throws {
        let server = try #require(PackageFiles.json("Vectors/currencies.json") as? [String: Int])
        let book = Dictionary(uniqueKeysWithValues: CurrencyTable.all.map { ($0.code, $0.digits) })
        #expect(book == server)
        #expect(server["JPY"] == 0)
        #expect(server["DOP"] == 2)
        #expect(server["KWD"] == 3)
    }

    private static func code(_ error: MoneyError) -> String {
        switch error {
        case .invalid: "amount_invalid"
        case .precision: "amount_precision"
        case .outOfRange: "amount_out_of_range"
        }
    }
}
