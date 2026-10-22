// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "Moss",
    platforms: [.iOS(.v15)],
    products: [
        .library(name: "Moss", targets: ["Moss"]),
    ],
    targets: [
        .binaryTarget(
            name: "MossC",
            url: "https://github.com/usemoss/moss/releases/download/v0.11.0/Moss.xcframework.zip",
            checksum: "44c7d3346bd1865fdfae96d39db9223ed81700b1a29c66aa13ce19ff2403410d"
        ),
        .target(
            name: "MossRuntimeBridge",
            dependencies: ["MossC"],
            path: "sdks/swift/Sources/MossRuntimeBridge",
            publicHeadersPath: "include"
        ),
        .target(
            name: "Moss",
            dependencies: ["MossC", "MossRuntimeBridge"],
            path: "sdks/swift/Sources/Moss"
        ),
    ]
)
