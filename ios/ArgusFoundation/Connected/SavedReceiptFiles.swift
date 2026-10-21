import UIKit
import VisionKit

/// Shapes what the pickers return into what the server stores: one document per capture, and only
/// PDF, JPEG or PNG within the decoded-pixel limit.
enum SavedReceiptFiles {
    typealias File = (data: Data, name: String, pdf: Bool)

    static let maxPixels: CGFloat = 20_000_000
    static var scannerAvailable: Bool {
        #if DEBUG
        if ScanStub.active { return true }
        #endif
        return VNDocumentCameraViewController.isSupported
    }

    /// The same shaping off the main thread: a multi-page scan becomes one full-resolution PDF, which takes seconds.
    static func preparing(_ files: [File], source: ReceiptSourceChoice, spanish: Bool) async -> [File] {
        await Task.detached(priority: .userInitiated) { prepared(files, source: source, spanish: spanish) }.value
    }

    static func prepared(_ files: [File], source: ReceiptSourceChoice, spanish: Bool) -> [File] {
        switch source {
        case .scan:
            let pages = files.compactMap { UIImage(data: $0.data) }
            guard pages.count == files.count, let pdf = combined(pages) else { return files }
            return [(pdf, spanish ? "Escaneo.pdf" : "Scan.pdf", true)]
        case .photos, .file, .sample:
            return files.map { $0.pdf ? $0 : storable($0) }
        }
    }

    /// One PDF with a page per scanned image, so a multi-page receipt is one saved receipt.
    static func combined(_ pages: [UIImage]) -> Data? {
        guard let first = pages.first else { return nil }
        let renderer = UIGraphicsPDFRenderer(bounds: CGRect(origin: .zero, size: first.size))
        return renderer.pdfData { context in
            for page in pages {
                let rect = CGRect(origin: .zero, size: page.size)
                context.beginPage(withBounds: rect, pageInfo: [:])
                page.draw(in: rect)
            }
        }
    }

    /// Photos from the library are usually HEIC and cameras can exceed the pixel limit; both are re-encoded as JPEG.
    private static func storable(_ file: File) -> File {
        let isPNG = file.data.starts(with: [0x89, 0x50, 0x4E, 0x47])
        let isJPEG = file.data.starts(with: [0xFF, 0xD8, 0xFF])
        guard let image = UIImage(data: file.data) else { return file }
        let pixels = image.size.width * image.scale * image.size.height * image.scale
        if (isPNG || isJPEG) && pixels <= maxPixels { return file }
        let shrink = pixels > maxPixels ? (maxPixels / pixels).squareRoot() * 0.98 : 1
        let size = CGSize(width: (image.size.width * image.scale * shrink).rounded(.down),
                          height: (image.size.height * image.scale * shrink).rounded(.down))
        let format = UIGraphicsImageRendererFormat.default()
        format.scale = 1
        let drawn = UIGraphicsImageRenderer(size: size, format: format).image { _ in image.draw(in: CGRect(origin: .zero, size: size)) }
        guard let data = drawn.jpegData(compressionQuality: 0.85) else { return file }
        let base = (file.name as NSString).deletingPathExtension
        return (data, base.isEmpty ? file.name : base + ".jpg", false)
    }
}
