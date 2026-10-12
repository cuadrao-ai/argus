import Foundation

/// The receipt journey's words, Spanish first. Labels reused from the approved receipt review are marked so;
/// every other string is pending the founder's approval.
struct ReceiptJourneyCopy {
    let spanish: Bool

    // Pending approval: consent. It names the data, who reads it and why, as the design guide requires.
    var consentTitle: String { spanish ? "¿Leemos este recibo?" : "Should we read this receipt?" }
    var consentDetail: String {
        spanish ? "Enviamos la imagen a un servicio de lectura con IA (Google Gemini) para sacar el comercio, la fecha, los artículos y el total. Así preparamos el gasto para que lo revises. No se guarda ningún gasto hasta que lo confirmes."
                : "We send the image to an AI reading service (Google Gemini) to pick out the merchant, date, items and total. That prepares the expense for you to review. No expense is saved until you confirm it."
    }
    var consentRead: String { spanish ? "Leer recibo" : "Read receipt" }
    var consentSaveOnly: String { spanish ? "Solo guardar" : "Save only" }
    var consentSaveOnlyDetail: String {
        spanish ? "Solo guardar lo deja en Recibos guardados sin leerlo." : "Save only keeps it in Saved receipts without reading it."
    }

    // Pending approval: progress.
    var sending: String { spanish ? "Enviando recibo…" : "Sending receipt…" }
    var reading: String { spanish ? "Leyendo tu recibo…" : "Reading your receipt…" }
    var readingDetail: String {
        spanish ? "Puedes cerrar esto. Lo encontrarás en Recibos guardados." : "You can close this. You will find it in Saved receipts."
    }
    var stillReading: String {
        spanish ? "Todavía se está leyendo. Ábrelo luego desde Recibos guardados." : "It is still being read. Open it later from Saved receipts."
    }
    var recording: String { spanish ? "Guardando gasto…" : "Saving expense…" }

    // Approved review labels (Cuadrao receipt review).
    var later: String { spanish ? "Después" : "Later" }
    var done: String { spanish ? "Listo" : "Done" }
    var cancel: String { spanish ? "Cancelar" : "Cancel" }
    var confirm: String { spanish ? "Confirmar gasto" : "Confirm expense" }
    var recorded: String { spanish ? "Gasto guardado" : "Expense saved" }
    var correct: String { spanish ? "Corregir datos" : "Correct details" }

    // Pending approval: review.
    var reviewTitle: String { spanish ? "Revisa el gasto" : "Review the expense" }
    var merchant: String { spanish ? "Comercio" : "Merchant" }
    var date: String { spanish ? "Fecha" : "Date" }
    var total: String { spanish ? "Total" : "Total" }
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
    var alreadyRecorded: String { spanish ? "Ya anoté este gasto" : "I already recorded this" }
    var alreadyRecordedDetail: String {
        spanish ? "Encontramos un movimiento con el mismo monto. Puedes añadirle este recibo en vez de crear otro."
                : "We found a movement with the same amount. You can add this receipt to it instead of creating another."
    }
    var linked: String { spanish ? "Recibo añadido al movimiento" : "Receipt added to the movement" }
    var recordedDetail: String {
        spanish ? "Está en tu cuenta con su recibo." : "It is in your account with its receipt."
    }

    // Pending approval: failures.
    var couldNotRead: String {
        spanish ? "No pudimos leer este recibo. Sigue guardado." : "We could not read this receipt. It is still saved."
    }
    var readAgain: String { spanish ? "Leer de nuevo" : "Read again" }
    var nothingToRecord: String {
        spanish ? "No encontramos un gasto en este recibo. Sigue guardado." : "We did not find an expense on this receipt. It is still saved."
    }
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
