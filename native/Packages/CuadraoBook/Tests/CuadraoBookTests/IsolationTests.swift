import Foundation
import Testing

/// The device book cannot grow a dependency, a network path or floating-point money without a test failing.
@Suite("Package isolation")
struct IsolationTests {
    @Test func packageDeclaresNoDependencies() throws {
        let manifest = try PackageFiles.text("Package.swift")
        #expect(!manifest.contains(".package("), "a package dependency")
        let targetDependencies = manifest.components(separatedBy: "dependencies:").dropFirst()
        #expect(targetDependencies.allSatisfy { $0.trimmingCharacters(in: .whitespaces).hasPrefix("[\"CuadraoBook\"]") },
                "only the test target may depend on the book itself")
    }

    @Test func sourcesImportFoundationOnlyAndHoldNoNetworkOrFloatingPoint() throws {
        let sources = PackageFiles.root.appendingPathComponent("Sources/CuadraoBook")
        let files = try #require(FileManager.default.enumerator(at: sources, includingPropertiesForKeys: nil))
            .compactMap { $0 as? URL }.filter { $0.pathExtension == "swift" }
        #expect(files.count >= 6)
        // Network, UI, and the file-timestamp APIs the app's privacy manifest does not declare.
        let forbidden = ["URLSession", "URLRequest", "NWConnection", "CFNetwork", "import Network", "import UIKit", "import SwiftUI",
                         "modificationDate", "creationDate", "contentModificationDateKey", "attributesOfItem", "fileModificationDate"]
        let floatingPoint = try NSRegularExpression(pattern: #"\b(Double|Float|Float80|CGFloat)\b"#)
        for file in files {
            let text = try String(contentsOf: file, encoding: .utf8)
            let imports = text.split(separator: "\n").filter { $0.hasPrefix("import ") }.map(String.init)
            #expect(imports.allSatisfy { $0 == "import Foundation" }, "\(file.lastPathComponent) imports \(imports)")
            for token in forbidden { #expect(!text.contains(token), "\(file.lastPathComponent) mentions \(token)") }
            let range = NSRange(text.startIndex..., in: text)
            #expect(floatingPoint.firstMatch(in: text, range: range) == nil, "\(file.lastPathComponent) uses floating point")
        }
    }
}
