import Foundation
import XCTest
import CuadraoBook
@testable import FinancialModels

/// Founder walk step 13: every currency picker offers the same three, from one list.
final class CurrencyChoiceTests: XCTestCase {
    func testTheAppListIsTheBookListOfExactlyThree() {
        XCTAssertEqual(PlanCurrency.supported, ["DOP", "USD", "EUR"])
        XCTAssertEqual(PlanCurrency.supported, CurrencyTable.offered)
        XCTAssertEqual(CurrencyTable.pickerCodes, CurrencyTable.offered)
    }

    func testNoPickerBuildsItsOwnCurrencyList() throws {
        let root = URL(fileURLWithPath: try XCTUnwrap(ProcessInfo.processInfo.environment["ARGUS_REPO_ROOT"]))
        let app = root.appendingPathComponent("ios/ArgusFoundation")
        let files = try XCTUnwrap(FileManager.default.enumerator(at: app, includingPropertiesForKeys: nil))
        var offenders: [String] = []
        for case let url as URL in files where url.pathExtension == "swift" {
            let text = try String(contentsOf: url, encoding: .utf8)
            let ownList = text.contains("commonISOCurrencyCodes") || text.contains("isoCurrencyCodes")
                || text.contains("[\"DOP\", \"USD\"") || text.contains("accounts.map(\\.currency))).sorted()")
            if ownList { offenders.append(url.lastPathComponent) }
        }
        XCTAssertEqual(offenders, [])
    }
}
