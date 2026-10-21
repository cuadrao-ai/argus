import Foundation

/// Every word of the saved-receipts surface, Spanish first. These are the founder-approved Consumer words
/// (October 8). The ones marked "pending approval" are not in the approved table.
struct SavedReceiptCopy {
    let spanish: Bool

    var title: String { CuadraoCopy.text("copy.savedReceiptCopy.d4f38a690a", spanish: spanish) }
    /// Pending approval: the approved empty text names a row, "Escanear o subir archivo", that the locked + menu
    /// no longer has (it now offers camera, photo and file rows).
    var empty: String {
        CuadraoCopy.text("copy.savedReceiptCopy.e630851585", spanish: spanish)
    }
    var saving: String { CuadraoCopy.text("copy.savedReceiptCopy.5a6b400da0", spanish: spanish) }
    var savedTitle: String { CuadraoCopy.text("copy.savedReceiptCopy.6f29c5dd9e", spanish: spanish) }
    var savedDetail: String {
        CuadraoCopy.text("copy.savedReceiptCopy.bc4d23a249", spanish: spanish)
    }
    var alreadySaved: String { CuadraoCopy.text("copy.savedReceiptCopy.1693909e16", spanish: spanish) }
    var tooLarge: String {
        CuadraoCopy.text("copy.savedReceiptCopy.12b75b52bb", spanish: spanish)
    }
    var wrongType: String { CuadraoCopy.text("copy.savedReceiptCopy.e34d749120", spanish: spanish) }
    var limitReached: String {
        CuadraoCopy.text("copy.savedReceiptCopy.d3c603bb44", spanish: spanish)
    }
    var offline: String {
        CuadraoCopy.text("copy.savedReceiptCopy.baec1c9f1c", spanish: spanish)
    }
    var couldNotSave: String { CuadraoCopy.text("copy.savedReceiptCopy.c1b38f8857", spanish: spanish) }
    var retry: String { CuadraoCopy.text("copy.connectedCuadraoAuth.ada77fc089", spanish: spanish) }
    var view: String { CuadraoCopy.text("copy.savedReceiptCopy.2b0aad47ef", spanish: spanish) }
    var delete: String { CuadraoCopy.text("copy.savedReceiptCopy.534547cf82", spanish: spanish) }
    var cancel: String { CuadraoCopy.text("copy.connectedCuadraoProfile.62a128b722", spanish: spanish) }
    var done: String { CuadraoCopy.text("copy.guestClaimModel.bd6b05a681", spanish: spanish) }
    var deleteTitle: String { CuadraoCopy.text("copy.savedReceiptCopy.4ca1494b4d", spanish: spanish) }
    var deleteMessage: String {
        CuadraoCopy.text("copy.savedReceiptCopy.f0a7244e55", spanish: spanish)
    }
    /// Pending approval: not in the approved table.
    var couldNotOpen: String { CuadraoCopy.text("copy.savedReceiptCopy.b74a2f9cac", spanish: spanish) }
    /// Pending approval: not in the approved table.
    var couldNotLoad: String { CuadraoCopy.text("copy.savedReceiptCopy.15140a35c0", spanish: spanish) }

    /// Founder-approved October 8.
    var couldNotDelete: String { CuadraoCopy.text("copy.savedReceiptCopy.f89ffead5a", spanish: spanish) }
    /// The approved receipt-source wording.
    var unusableFile: String {
        CuadraoCopy.text("copy.savedReceiptCopy.9af3b14b7d", spanish: spanish)
    }
    /// The approved scanner wording.
    var scannerUnavailable: String {
        CuadraoCopy.text("copy.savedReceiptCopy.c20136d6f3", spanish: spanish)
    }

    func failure(_ failure: SavedReceiptFailure) -> String {
        switch failure {
        case .tooLarge: tooLarge
        case .wrongType: wrongType
        case .limitReached: limitReached
        case .couldNotSave: couldNotSave
        case .couldNotDelete: couldNotDelete
        case .unusableFile: unusableFile
        case .scannerUnavailable: scannerUnavailable
        case .offline: offline
        }
    }
}
