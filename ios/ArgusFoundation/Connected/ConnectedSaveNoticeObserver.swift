import SwiftUI

/// Turns each save the server accepted into the notice, the highlight and the success haptic, wherever the person is.
/// A connected create has no authorized delete, so the notice offers "Ver", never Undo.
struct ConnectedSaveNoticeObserver: View {
    @ObservedObject var loop: FinancialLoopModel
    let result: CuadraoSaveResult
    let spanish: Bool
    let view: (UUID) -> Void

    var body: some View {
        Color.clear.frame(width: 0, height: 0)
            .onChange(of: loop.saveNotice) { _, notice in
                guard let notice else { return }
                if let id = notice.activityID, !notice.corrected {
                    result.saved(spanish ? "Movimiento guardado" : "Transaction saved", highlight: id,
                                 actionTitle: spanish ? "Ver" : "View", actionIdentifier: "toast.view") {
                        view(id); result.dismiss()
                    }
                } else if notice.corrected {
                    result.saved(spanish ? "Cambios guardados" : "Changes saved", highlight: notice.activityID)
                } else {
                    result.saved(spanish ? "Cuenta guardada" : "Account saved")
                }
            }
    }
}
