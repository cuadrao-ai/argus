import Foundation
import UIKit
import PhotosUI
import PDFKit

@main struct ScanCaptureChecks {
    @MainActor static func main() async throws {
        let image = UIGraphicsImageRenderer(size: CGSize(width: 32, height: 48)).image { context in
            UIColor.white.setFill()
            context.fill(CGRect(x: 0, y: 0, width: 32, height: 48))
        }
        let imageData = image.jpegData(compressionQuality: 0.8)!
        let file = (data: imageData, name: "Receipt.jpg", pdf: false)
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: folder) }

        var scanned: [ReceiptCapturedFiles] = []
        let scan = ReceiptNativePicker.Coordinator(spanish: false) { result in
            precondition(Thread.isMainThread, "Capture completion must return to the UI thread")
            scanned.append(try! result.get())
        }
        scan.finishScan([image, image])
        precondition(scanned.isEmpty, "Encoding must yield before it completes")
        try await wait { !scanned.isEmpty }
        precondition(scanned.count == 1 && scanned[0].count == 2)
        let prepared = await SavedReceiptFiles.preparing(scanned[0], source: .scan, spanish: false)
        precondition(prepared.count == 1 && prepared[0].pdf)
        precondition(PDFDocument(data: prepared[0].data)?.pageCount == 2)
        scan.finishScan([image])
        try await Task.sleep(for: .milliseconds(200))
        precondition(scanned.count == 1, "Repeated scanner results must complete once")

        var cancelled = 0
        let cancel = ReceiptNativePicker.Coordinator(spanish: false) { result in
            guard case .failure(let error) = result else { preconditionFailure("Cancelled scan returned files") }
            precondition((error as NSError).code == NSUserCancelledError)
            cancelled += 1
        }
        let documentPicker = UIDocumentPickerViewController(forOpeningContentTypes: [.image, .pdf])
        cancel.finishScan([image])
        cancel.documentPickerWasCancelled(documentPicker)
        cancel.documentPickerWasCancelled(documentPicker)
        try await Task.sleep(for: .milliseconds(200))
        precondition(cancelled == 1, "Cancellation must suppress a pending encode result")

        var failures = 0
        let failure = ReceiptNativePicker.Coordinator(spanish: false) { result in
            guard case .failure = result else { preconditionFailure("Unreadable file returned success") }
            failures += 1
        }
        failure.documentPicker(documentPicker, didPickDocumentsAt: [folder.appendingPathComponent("missing.pdf")])
        failure.finishScan([image])
        try await Task.sleep(for: .milliseconds(200))
        precondition(failures == 1, "An error must complete once even with an encode pending")

        for pdf in [false, true] {
            let data = pdf ? prepared[0].data : imageData
            let url = folder.appendingPathComponent(pdf ? "Receipt.pdf" : "Receipt.jpg")
            try data.write(to: url)
            var received: ReceiptCapturedFiles = []
            let files = ReceiptNativePicker.Coordinator(spanish: false) { received = try! $0.get() }
            files.documentPicker(documentPicker, didPickDocumentsAt: [url])
            precondition(received.count == 1 && received[0].pdf == pdf && received[0].data == data)
            let stored = await SavedReceiptFiles.preparing(received, source: .file, spanish: false)
            precondition(stored.count == 1 && stored[0].data == data)
        }
        let photo = await SavedReceiptFiles.preparing([file], source: .photos, spanish: false)
        precondition(photo.count == 1 && photo[0].data == imageData && !photo[0].pdf)
        var photoCancelled = 0
        let photos = ReceiptNativePicker.Coordinator(spanish: false) { result in
            guard case .failure(let error) = result else { preconditionFailure("Empty photo selection returned success") }
            precondition((error as NSError).code == NSUserCancelledError)
            photoCancelled += 1
        }
        let photoPicker = PHPickerViewController(configuration: PHPickerConfiguration())
        photos.picker(photoPicker, didFinishPicking: [])
        photos.picker(photoPicker, didFinishPicking: [])
        precondition(photoCancelled == 1)

        for source in [ReceiptSourceChoice.scan, .photos, .file] {
            let presentation = CapturePresentation()
            presentation.complete(.success([file]), source: source)
            precondition(presentation.consumed.isEmpty)
            try await wait { presentation.capturing == nil }
            precondition(presentation.captured?.count == 1)
            precondition(presentation.consumed.isEmpty, "Consent must wait until the picker closes")
            presentation.dismissed()
            presentation.dismissed()
            precondition(presentation.consumed.count == 1, "Dismissal must hand off files once")
        }
        let cancelledPresentation = CapturePresentation()
        cancelledPresentation.complete(.failure(NSError(domain: NSCocoaErrorDomain, code: NSUserCancelledError)), source: .scan)
        cancelledPresentation.dismissed()
        precondition(cancelledPresentation.consumed.isEmpty && cancelledPresentation.auth.savedReceipts!.count == 0)
        let failedPresentation = CapturePresentation()
        failedPresentation.complete(.failure(ReceiptError.source), source: .file)
        failedPresentation.dismissed()
        precondition(failedPresentation.consumed.isEmpty && failedPresentation.auth.savedReceipts!.count == 1)

        #if DEBUG
        var stubPages = 0
        let stub = ScanStub.controller { stubPages = $0.count }
        stub.loadViewIfNeeded()
        let done = stub.view.subviews.compactMap { $0 as? UIButton }.first!
        done.sendActions(for: .touchUpInside)
        precondition(stubPages == 2, "The debug scanner must return its two camera-sized pages")
        #endif
        print("Scan capture checks passed. Scan, cancellation, error, photo, file, PDF and duplicate completion.")
    }

    @MainActor static func wait(_ ready: () -> Bool) async throws {
        for _ in 0..<100 {
            if ready() { return }
            try await Task.sleep(for: .milliseconds(20))
        }
        preconditionFailure("Capture did not complete")
    }
}
