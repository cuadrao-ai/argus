import Foundation
import Testing
@testable import CuadraoBook

@Suite("Money")
struct MoneyTests {
    @Test func typedAmountsAcceptTheDotsAStrictParserRefuses() {
        #expect(MoneyParser.parseTyped("12.", digits: 2) == .success(1200))
        #expect(MoneyParser.parseTyped(".5", digits: 2) == .success(50))
        #expect(MoneyParser.parseTyped("-.5", digits: 2) == .success(-50))
        #expect(MoneyParser.parseTyped(" 7 ", digits: 0) == .success(7))
        #expect(MoneyParser.parseTyped(".", digits: 2) == .failure(.invalid))
        #expect(MoneyParser.parseTyped("1,5", digits: 2) == .failure(.invalid))
    }

    @Test func excessPrecisionIsRefusedNeverRounded() {
        #expect(MoneyParser.parseTyped("0.001", digits: 2) == .failure(.precision(digits: 2)))
        #expect(MoneyParser.parseTyped("0.5", digits: 0) == .failure(.precision(digits: 0)))
        #expect(MoneyParser.parseTyped("0.0005", digits: 3) == .failure(.precision(digits: 3)))
    }

    @Test func zeroAndUnknownAreDifferentToTheCaller() {
        // The parser has no default for blank text: an empty field is "unknown" and never reaches it as zero.
        #expect(MoneyParser.parse("", digits: 2) == .failure(.invalid))
        #expect(MoneyParser.parse("0", digits: 2) == .success(0))
    }

    @Test func groupedTextUsesTheGivenSeparatorsAndKeepsEveryDigit() {
        #expect(MoneyFormatter.grouped(123_456_789, digits: 2) == "1,234,567.89")
        #expect(MoneyFormatter.grouped(-123_456_789, digits: 2, grouping: ".", decimal: ",") == "-1.234.567,89")
        #expect(MoneyFormatter.grouped(1_234_567, digits: 0) == "1,234,567")
        #expect(MoneyFormatter.grouped(1_234_567, digits: 3) == "1,234.567")
        #expect(MoneyFormatter.grouped(5, digits: 3) == "0.005")
        #expect(MoneyFormatter.grouped(100, digits: 0) == "100")
        #expect(MoneyFormatter.grouped(Int64.min, digits: 0) == "-9,223,372,036,854,775,808")
    }

    @Test func plainTextRoundTripsThroughTheParserForEveryDigitCount() {
        for digits in 0...3 {
            for minor: Int64 in [0, 1, -1, 99, 100, 123_456_789, -987_654_321, Limits.maximumMinor, -Limits.maximumMinor] {
                let text = MoneyFormatter.plain(minor, digits: digits)
                #expect(MoneyParser.parse(text, digits: digits) == .success(minor), "\(text) at \(digits)")
            }
        }
    }

    @Test func moneyCarriesItsSnapshotDigits() {
        let yen = Money(minor: 1500, currency: "JPY", digits: 0)
        let dinar = Money(minor: 1500, currency: "KWD", digits: 3)
        #expect(yen.plain == "1500")
        #expect(dinar.plain == "1.500")
    }

    @Test func decimalConversionIsExactOrRefused() {
        #expect(MinorUnits.decimal(1234, digits: 2) == Decimal(string: "12.34"))
        #expect(MinorUnits.decimal(-5, digits: 3) == Decimal(string: "-0.005"))
        #expect(MinorUnits.exactMinor(Decimal(string: "12.34")!, digits: 2) == 1234)
        #expect(MinorUnits.exactMinor(Decimal(string: "12.345")!, digits: 2) == nil)
        #expect(MinorUnits.exactMinor(Decimal(string: "-3")!, digits: 0) == -3)
        #expect(MinorUnits.exactMinor(Decimal(string: "99999999999999999999")!, digits: 2) == nil)
    }

    @Test func amountLimitKeepsTotalsInsideInt64() {
        #expect(Limits.withinAmount(Limits.maximumMinor))
        #expect(Limits.withinAmount(-Limits.maximumMinor))
        #expect(!Limits.withinAmount(Limits.maximumMinor + 1))
        #expect(!Limits.withinAmount(Int64.min))
        #expect(Int64.max / Limits.maximumMinor >= 9_000)
    }

    @Test func currencyLookupTrimsAndUppercases() {
        #expect(CurrencyTable.currency(" dop ")?.digits == 2)
        #expect(CurrencyTable.currency("XXX") == nil)
        #expect(CurrencyTable.currency("") == nil)
        #expect(CurrencyTable.pickerCodes.prefix(3).elementsEqual(["DOP", "USD", "EUR"]))
        #expect(Set(CurrencyTable.pickerCodes).count == CurrencyTable.all.count)
    }
}
