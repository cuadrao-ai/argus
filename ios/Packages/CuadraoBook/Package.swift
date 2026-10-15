// swift-tools-version: 6.0
import PackageDescription

// The device book is Foundation only. A test reads this file and fails on any dependency.
let package = Package(
    name: "CuadraoBook",
    platforms: [.iOS(.v17), .macOS(.v14)],
    products: [.library(name: "CuadraoBook", targets: ["CuadraoBook"])],
    targets: [
        .target(name: "CuadraoBook"),
        .testTarget(name: "CuadraoBookTests", dependencies: ["CuadraoBook"])
    ]
)
