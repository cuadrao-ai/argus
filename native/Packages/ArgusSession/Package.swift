// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "ArgusSession",
    platforms: [.iOS(.v17), .macOS(.v14)],
    products: [.library(name: "ArgusSession", targets: ["ArgusSession"])],
    dependencies: [.package(url: "https://github.com/supabase/supabase-swift.git", exact: "2.55.2")],
    targets: [
        .target(name: "ArgusSession", dependencies: [.product(name: "Auth", package: "supabase-swift")]),
        .testTarget(name: "ArgusSessionTests", dependencies: ["ArgusSession", .product(name: "Auth", package: "supabase-swift")])
    ]
)
