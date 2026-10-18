import Foundation

/// The receipt journey's words, Spanish first. Labels reused from the approved receipt review are marked so;
/// every other string is pending the founder's approval.
struct ReceiptJourneyCopy {
    let spanish: Bool

    // Consent: asked once per account, until reading is turned off in Settings.
    var consentTitle: String { CuadraoCopy.text("copy.receiptJourneyCopy.5f6fa34cb3", spanish: spanish) }
    var consentDetail: String {
        CuadraoCopy.text("copy.receiptJourneyCopy.8e96c640cc", spanish: spanish)
    }
    func choiceTitle(_ count: Int) -> String {
        (count == 1 ? CuadraoCopy.text("copy.receiptJourneyCopy.2956914fa6", spanish: spanish) : CuadraoCopy.text("copy.receiptJourneyCopy.528d92bdda", spanish: spanish, String(describing: count)))
    }
    var read: String { CuadraoCopy.text("copy.receiptJourneyCopy.f6e569c91f", spanish: spanish) }
    var consentSaveOnly: String { CuadraoCopy.text("copy.receiptJourneyCopy.8a305c5e3c", spanish: spanish) }

    // Settings: the long explanation lives here and in the first question only.
    var settingTitle: String { CuadraoCopy.text("copy.receiptJourneyCopy.51fddd2271", spanish: spanish) }
    var settingFooter: String {
        CuadraoCopy.text("copy.receiptJourneyCopy.3dc5995bd6", spanish: spanish)
    }

    // Pending approval: progress.
    var sending: String { CuadraoCopy.text("copy.receiptJourneyCopy.02737393df", spanish: spanish) }
    var reading: String { CuadraoCopy.text("copy.receiptJourneyCopy.9f2ed9f6be", spanish: spanish) }
    var readingDetail: String {
        CuadraoCopy.text("copy.receiptJourneyCopy.b1a30a5a78", spanish: spanish)
    }
    var stillReading: String {
        CuadraoCopy.text("copy.receiptJourneyCopy.283209abd4", spanish: spanish)
    }
    var recording: String { CuadraoCopy.text("copy.receiptJourneyCopy.4b4e939302", spanish: spanish) }

    // Approved review labels (Cuadrao receipt review).
    var later: String { CuadraoCopy.text("copy.receiptJourneyCopy.fb09b69c44", spanish: spanish) }
    var done: String { CuadraoCopy.text("copy.guestClaimModel.bd6b05a681", spanish: spanish) }
    var cancel: String { CuadraoCopy.text("copy.connectedCuadraoProfile.62a128b722", spanish: spanish) }
    var confirm: String { CuadraoCopy.text("copy.receiptJourneyCopy.88b4c99896", spanish: spanish) }
    var recorded: String { CuadraoCopy.text("copy.receiptJourneyCopy.fb6e8c6a34", spanish: spanish) }
    var correct: String { CuadraoCopy.text("copy.receiptJourneyCopy.f72bbcda64", spanish: spanish) }

    // Pending approval: review.
    var reviewTitle: String { CuadraoCopy.text("copy.receiptJourneyCopy.ddd896d668", spanish: spanish) }
    var merchant: String { CuadraoCopy.text("copy.receiptJourneyCopy.e47fa08736", spanish: spanish) }
    var date: String { CuadraoCopy.text("copy.connectedTransactionSheet.9e3d3b41ed", spanish: spanish) }
    var total: String { CuadraoCopy.text("copy.receiptJourneyCopy.b0d12f3afd", spanish: spanish) }
    var category: String { CuadraoCopy.text("copy.connectedCuadraoHome.67c7ee0c0f", spanish: spanish) }
    var noCategory: String { CuadraoCopy.text("copy.receiptJourneyCopy.225664ae74", spanish: spanish) }
    var account: String { CuadraoCopy.text("copy.connectedAccountPresentation.f9d32ca2e5", spanish: spanish) }
    var chooseAccount: String { CuadraoCopy.text("copy.receiptJourneyCopy.2644936461", spanish: spanish) }
    var noAccount: String {
        CuadraoCopy.text("copy.receiptJourneyCopy.2abe13d666", spanish: spanish)
    }
    var items: String { CuadraoCopy.text("copy.receiptJourneyCopy.cc033fc1d3", spanish: spanish) }
    var itemsNote: String {
        CuadraoCopy.text("copy.receiptJourneyCopy.af72fbf701", spanish: spanish)
    }
    var unknown: String { CuadraoCopy.text("copy.receiptJourneyCopy.22aeea771f", spanish: spanish) }
    var alreadyRecorded: String { CuadraoCopy.text("copy.receiptJourneyCopy.5e98f536b8", spanish: spanish) }
    var alreadyRecordedDetail: String {
        CuadraoCopy.text("copy.receiptJourneyCopy.6751bbc478", spanish: spanish)
    }
    var linked: String { CuadraoCopy.text("copy.receiptJourneyCopy.724c065e73", spanish: spanish) }
    var recordedDetail: String {
        CuadraoCopy.text("copy.receiptJourneyCopy.dabc84976a", spanish: spanish)
    }

    // Pending approval: failures.
    var couldNotReadTitle: String { CuadraoCopy.text("copy.receiptJourneyCopy.4f6e4f2289", spanish: spanish) }
    var nothingToRecordTitle: String { CuadraoCopy.text("copy.receiptJourneyCopy.8dbbc7ed8e", spanish: spanish) }
    var stillSaved: String { CuadraoCopy.text("copy.receiptJourneyCopy.f19696359f", spanish: spanish) }
    var stillReadingTitle: String { CuadraoCopy.text("copy.receiptJourneyCopy.cd5de1072d", spanish: spanish) }
    var offlineTitle: String { CuadraoCopy.text("copy.receiptJourneyCopy.b2652dac6f", spanish: spanish) }
    var offlineDetail: String {
        CuadraoCopy.text("copy.receiptJourneyCopy.cb0aa10792", spanish: spanish)
    }
    var couldNotSendTitle: String { CuadraoCopy.text("copy.receiptJourneyCopy.69007b1cdc", spanish: spanish) }
    var readAgain: String { CuadraoCopy.text("copy.receiptJourneyCopy.4a3f9b4af6", spanish: spanish) }
    var couldNotRecord: String { CuadraoCopy.text("copy.receiptJourneyCopy.f3b44fd27f", spanish: spanish) }
    var balanceCheck: String {
        CuadraoCopy.text("copy.receiptJourneyCopy.07bd00b851", spanish: spanish)
    }
    func nextReceipt(_ count: Int) -> String {
        (count == 1 ? CuadraoCopy.text("copy.receiptJourneyCopy.ac639e5b2c", spanish: spanish) : CuadraoCopy.text("copy.receiptJourneyCopy.6962a3aaa7", spanish: spanish, String(describing: count)))
    }
    var viewReceipt: String { CuadraoCopy.text("copy.receiptJourneyCopy.176bc5563c", spanish: spanish) }
    var backToReview: String { CuadraoCopy.text("copy.receiptJourneyCopy.a098e5adcb", spanish: spanish) }
    var retry: String { CuadraoCopy.text("copy.connectedCuadraoAuth.ada77fc089", spanish: spanish) }

    func recordFailure(_ code: String?) -> String {
        code == "balance_coverage_required" ? balanceCheck : couldNotRecord
    }
}
