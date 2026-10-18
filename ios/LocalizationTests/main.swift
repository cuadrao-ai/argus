import Foundation

func expect(_ value: @autoclosure () -> Bool, _ message: String) {
    precondition(value(), message)
}

expect(CuadraoCopy.locale(preferredLanguages: ["zz-ZZ"]).identifier == "es-419", "Unknown locale falls back to Spanish")
expect(CuadraoCopy.locale(preferredLanguages: ["fr-FR", "en-GB"]).identifier == "en", "Ordered supported device language wins")
expect(CuadraoCopy.locale(preferredLanguages: []).identifier == "es-419", "No locale falls back to Spanish")
expect(CuadraoCopy.isSpanish(preferredLanguages: ["fr_FR"]), "Unknown UI language uses Spanish")
expect(!CuadraoCopy.isSpanish(preferredLanguages: ["en_GB"]), "English remains supported")
expect(CuadraoCopy.isSpanish(preferredLanguages: ["es_ES"]), "Regional Spanish remains supported")
expect(CuadraoCopy.text("destination.home", spanish: true) == "Inicio", "Spanish resource lookup")
expect(CuadraoCopy.text("destination.home", spanish: false) == "Home", "English resource lookup")
expect(CuadraoCopy.text("destination.argus", spanish: true) == "Cuadrao", "Visible brand")
let regional = Locale(identifier: "es_ES")
let formatter = NumberFormatter()
formatter.locale = regional
formatter.minimumFractionDigits = 2
formatter.maximumFractionDigits = 2
let entered = formatter.string(from: 1.5)!
expect(entered == "1,50", "Regional editor seeds decimal comma")
let accepted = try AccountEntry.amount(entered, locale: regional)
expect(accepted == "1.50", "Regional editor parses the same value")
expect(CuadraoCopy.text("localization.test.format", spanish: true, "first", "second") == "second, first: 50%", "Reordered interpolation and literal percent")
expect(CuadraoCopy.text("localization.test.percent", spanish: false) == "50%", "Literal percent without interpolation")
expect(!CuadraoCopy.isSpanish(preferredLanguages: ["fr-FR", "en-GB"]), "Later supported device language agrees with Bundle")
expect(CuadraoCopy.text("copy.connectedTransactionSheet.9e3d3b41ed", spanish: true) == "Fecha", "Approved date label remains Spanish")
expect(CuadraoCopy.text("copy.connectedAccountPresentation.f9d32ca2e5", spanish: true) == "Cuenta", "Approved account label remains Spanish")
expect(CuadraoCopy.text("copy.connectedCuadraoHome.67c7ee0c0f", spanish: true) == "Categoría", "Approved category label remains Spanish")
expect(CuadraoCopy.text("copy.connectedCuadraoAuth.ada77fc089", spanish: true) == "Reintentar", "Approved retry label remains Spanish")
expect(CuadraoCopy.text("copy.receiptJourneyCopy.e47fa08736", spanish: true) == "Comercio", "Approved receipt merchant label is reused")
expect(CuadraoCopy.text("copy.receiptJourneyCopy.225664ae74", spanish: true) == "Sin categoría", "Approved nil category label is reused")
expect(CuadraoCopy.text("copy.invitationViews.2b2821ec48", spanish: true) == "Entendido", "Approved alert dismiss label is reused")
print("Localization behavior: 21 assertions passed; unknown locale, supported languages, bundle copy, interpolation, percent, decimal-comma roundtrip")
