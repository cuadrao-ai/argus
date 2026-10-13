import Foundation

/// The receipt journey's words, Spanish first. Labels reused from the approved receipt review are marked so;
/// every other string is pending the founder's approval.
struct ReceiptJourneyCopy {
    let spanish: Bool

    // Consent: asked once per account, until reading is turned off in Settings.
    var consentTitle: String { spanish ? "¿Leemos tus recibos con IA?" : "Read your receipts with AI?" }
    var consentDetail: String {
        spanish ? "Google Gemini lee la foto y prepara el gasto para que lo revises. Nada se guarda hasta que lo confirmes. Puedes apagarlo en Perfil."
                : "Google Gemini reads the photo and prepares the expense for you to review. Nothing is saved until you confirm. You can turn this off in Profile."
    }
    func choiceTitle(_ count: Int) -> String {
        spanish ? (count == 1 ? "Recibo listo" : "\(count) recibos listos") : (count == 1 ? "Receipt ready" : "\(count) receipts ready")
    }
    var read: String { spanish ? "Leer" : "Read" }
    var consentSaveOnly: String { spanish ? "Solo guardar" : "Save only" }

    // Settings: the long explanation lives here and in the first question only.
    var settingTitle: String { spanish ? "Leer recibos con IA" : "Read receipts with AI" }
    var settingFooter: String {
        spanish ? "Cuando lees un recibo, enviamos la imagen a Google Gemini para sacar el comercio, la fecha, los artículos y el total. No se guarda ningún gasto hasta que lo confirmes. Si lo apagas, te preguntamos antes de leer otro recibo; los recibos guardados no cambian."
                : "When you read a receipt, we send the image to Google Gemini to pick out the merchant, date, items and total. No expense is saved until you confirm it. If you turn this off, we ask before reading another receipt; saved receipts do not change."
    }

    // Pending approval: progress.
    var sending: String { spanish ? "Enviando recibo…" : "Sending receipt…" }
    var reading: String { spanish ? "Leyendo tu recibo…" : "Reading your receipt…" }
    var readingDetail: String {
        spanish ? "Puedes cerrar esto. Lo encontrarás en Recibos guardados." : "You can close this. You will find it in Saved receipts."
    }
    var stillReading: String {
        spanish ? "Ábrelo luego desde Recibos guardados." : "Open it later from Saved receipts."
    }
    var recording: String { spanish ? "Guardando gasto…" : "Saving expense…" }

    // Approved review labels (Cuadrao receipt review).
    var later: String { spanish ? "Después" : "Later" }
    var done: String { spanish ? "Listo" : "Done" }
    var cancel: String { spanish ? "Cancelar" : "Cancel" }
    var confirm: String { spanish ? "Confirmar gasto" : "Confirm expense" }
    var recorded: String { spanish ? "Gasto guardado" : "Expense saved" }

    // Pending approval: review.
    var reviewTitle: String { spanish ? "Revisa el gasto" : "Review the expense" }
    var merchant: String { spanish ? "Comercio" : "Merchant" }
    var date: String { spanish ? "Fecha" : "Date" }
    var total: String { spanish ? "Total" : "Total" }
    var chooseDate: String { spanish ? "Elegir fecha" : "Choose a date" }
    var useDate: String { spanish ? "Usar esta fecha" : "Use this date" }
    var category: String { spanish ? "Categoría" : "Category" }
    var noCategory: String { spanish ? "Sin categoría" : "No category" }
    var account: String { spanish ? "Cuenta" : "Account" }
    var chooseAccount: String { spanish ? "Elige la cuenta que pagó" : "Choose the account that paid" }
    var noAccount: String {
        spanish ? "No tienes una cuenta abierta en esta moneda para este gasto." : "You have no open account in this currency for this expense."
    }
    var items: String { spanish ? "Artículos del recibo" : "Receipt items" }
    var itemsNote: String {
        spanish ? "Los artículos son detalle del recibo. Se guarda un solo gasto por el total."
                : "Items are receipt detail. One expense is saved for the total."
    }
    var unknown: String { spanish ? "Sin dato" : "Unknown" }
    var alreadyRecorded: String { spanish ? "Añadir a ese movimiento" : "Add to that movement" }
    var newPurchase: String { spanish ? "Es otro gasto" : "It is a new expense" }
    var duplicateTitle: String { spanish ? "¿Ya anotaste este gasto?" : "Already recorded this?" }
    /// Says nothing about the matched movement's amount: the server returns only which movement matched.
    var duplicateDetail: String {
        spanish ? "Encontramos un movimiento que se parece a este recibo. Puedes añadirle el recibo en vez de crear otro gasto."
                : "We found a movement that looks like this receipt. You can add the receipt to it instead of creating another expense."
    }
    var writeByHand: String { spanish ? "Escribirlo a mano" : "Write it by hand" }
    var linked: String { spanish ? "Recibo añadido al movimiento" : "Receipt added to the movement" }
    var recordedDetail: String {
        spanish ? "Está en tu cuenta con su recibo." : "It is in your account with its receipt."
    }

    // Pending approval: failures.
    var couldNotReadTitle: String { spanish ? "No pudimos leerlo" : "We could not read it" }
    var nothingToRecordTitle: String { spanish ? "No encontramos un gasto" : "No expense found" }
    var stillSaved: String { spanish ? "Sigue guardado en Recibos guardados." : "It is still in Saved receipts." }
    var stillReadingTitle: String { spanish ? "Sigue leyéndose" : "Still reading" }
    var offlineTitle: String { spanish ? "Sin conexión" : "No connection" }
    var offlineDetail: String {
        spanish ? "El recibo sigue en este iPhone. Inténtalo cuando vuelva la conexión." : "The receipt is still on this iPhone. Try again when you are back online."
    }
    var couldNotSendTitle: String { spanish ? "No se pudo enviar" : "Could not send" }
    var readAgain: String { spanish ? "Leer de nuevo" : "Read again" }
    var couldNotRecord: String { spanish ? "No pudimos guardar el gasto." : "We could not save the expense." }
    var balanceCheck: String {
        spanish ? "Esta cuenta necesita un saldo confirmado antes de este gasto. Revísala y vuelve a intentarlo."
                : "This account needs a confirmed balance before this expense. Check it and try again."
    }
    func nextReceipt(_ count: Int) -> String {
        spanish ? (count == 1 ? "Revisar el siguiente recibo" : "Revisar el siguiente (quedan \(count))")
                : (count == 1 ? "Review the next receipt" : "Review the next one (\(count) left)")
    }
    var viewReceipt: String { spanish ? "Ver recibo" : "View receipt" }
    var backToReview: String { spanish ? "Volver a revisar" : "Back to review" }
    var retry: String { spanish ? "Reintentar" : "Try again" }

    func recordFailure(_ code: String?) -> String {
        code == "balance_coverage_required" ? balanceCheck : couldNotRecord
    }
}
