import SwiftUI
import PhotosUI
import VisionKit
import PDFKit
import UniformTypeIdentifiers

struct ReceiptNativePicker: UIViewControllerRepresentable {
    let source: ReceiptSourceChoice
    let spanish: Bool
    let completed: (Result<ReceiptCapturedFiles, Error>) -> Void
    func makeCoordinator() -> Coordinator { Coordinator(spanish: spanish, completed: completed) }
    func makeUIViewController(context: Context) -> UIViewController {
        switch source {
        case .scan:
            #if DEBUG
            if ScanStub.active { return ScanStub.controller { context.coordinator.finishScan($0) } }
            #endif
            let controller = VNDocumentCameraViewController()
            controller.delegate = context.coordinator
            return controller
        case .photos:
            var configuration = PHPickerConfiguration(photoLibrary: .shared())
            configuration.filter = .images; configuration.selectionLimit = 1
            let controller = PHPickerViewController(configuration: configuration)
            controller.delegate = context.coordinator
            return controller
        case .file, .sample:
            let controller = UIDocumentPickerViewController(forOpeningContentTypes: [.image, .pdf], asCopy: true)
            controller.delegate = context.coordinator
            return controller
        }
    }
    func updateUIViewController(_ controller: UIViewController, context: Context) {}
    final class Coordinator: NSObject, VNDocumentCameraViewControllerDelegate, PHPickerViewControllerDelegate, UIDocumentPickerDelegate {
        let spanish: Bool
        let completed: (Result<ReceiptCapturedFiles, Error>) -> Void
        private var finished = false
        init(spanish: Bool, completed: @escaping (Result<ReceiptCapturedFiles, Error>) -> Void) {
            self.spanish = spanish; self.completed = completed
        }
        private func finish(_ result: Result<ReceiptCapturedFiles, Error>) {
            guard !finished else { return }; finished = true; completed(result)
        }
        private func cancel() { finish(.failure(NSError(domain: NSCocoaErrorDomain, code: NSUserCancelledError))) }
        func documentPickerWasCancelled(_ controller: UIDocumentPickerViewController) { cancel() }
        func documentPicker(_ controller: UIDocumentPickerViewController, didPickDocumentsAt urls: [URL]) {
            guard let url = urls.first else { cancel(); return }
            do {
                let access = url.startAccessingSecurityScopedResource()
                defer { if access { url.stopAccessingSecurityScopedResource() } }
                guard (try url.resourceValues(forKeys: [.fileSizeKey]).fileSize ?? 0) <= 20_000_000 else { throw ReceiptError.source }
                let data = try Data(contentsOf: url)
                let pdf = url.pathExtension.lowercased() == "pdf"
                if pdf {
                    guard let document = PDFDocument(data: data), (1...10).contains(document.pageCount) else { throw ReceiptError.source }
                } else { guard UIImage(data: data) != nil else { throw ReceiptError.source } }
                finish(.success([(data, url.lastPathComponent, pdf)]))
            } catch { finish(.failure(error)) }
        }
        func picker(_ picker: PHPickerViewController, didFinishPicking results: [PHPickerResult]) {
            guard let result = results.first else { cancel(); return }
            result.itemProvider.loadDataRepresentation(forTypeIdentifier: UTType.image.identifier) { data, error in
                DispatchQueue.main.async {
                    if let error { self.finish(.failure(error)); return }
                    guard let data, data.count <= 20_000_000, UIImage(data: data) != nil else { self.finish(.failure(ReceiptError.source)); return }
                    self.finish(.success([(data, self.spanish ? "Foto del recibo" : "Receipt photo", false)]))
                }
            }
        }
        func documentCameraViewControllerDidCancel(_ controller: VNDocumentCameraViewController) { ScanTrace.mark("cancel"); cancel() }
        func documentCameraViewController(_ controller: VNDocumentCameraViewController, didFailWithError error: Error) {
            ScanTrace.mark("fail \((error as NSError).domain) \((error as NSError).code)"); finish(.failure(error))
        }
        func documentCameraViewController(_ controller: VNDocumentCameraViewController, didFinishWith scan: VNDocumentCameraScan) {
            ScanTrace.mark("confirm pages=\(scan.pageCount)")
            guard (1...10).contains(scan.pageCount) else { finish(.failure(ReceiptError.source)); return }
            finishScan((0..<scan.pageCount).map { scan.imageOfPage(at: $0) })
        }

        /// Encoding full-resolution pages takes seconds on a phone; it runs off the main thread so the
        /// confirm tap never freezes the app, and the result comes back on the main thread.
        func finishScan(_ images: [UIImage]) {
            ScanTrace.mark("encoding pages=\(images.count)")
            let spanish = spanish
            DispatchQueue.global(qos: .userInitiated).async {
                let pages = images.compactMap { $0.jpegData(compressionQuality: 0.8) }
                let result: Result<ReceiptCapturedFiles, Error> =
                    pages.count == images.count && pages.reduce(0, { $0 + $1.count }) <= 20_000_000
                    ? .success(pages.enumerated().map { ($0.element, "\(spanish ? "Página" : "Page") \($0.offset + 1)", false) })
                    : .failure(ReceiptError.source)
                ScanTrace.mark("encoded")
                DispatchQueue.main.async { self.finish(result) }
            }
        }
    }
}
