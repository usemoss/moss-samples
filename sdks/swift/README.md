# Moss Swift SDK

The Swift SDK for [Moss](https://github.com/usemoss/moss) — fast on-device search for iOS.

## Requirements

- iOS 15+
- Xcode 15+

## Install

In Xcode: **File ▸ Add Package Dependencies…** and enter

```
https://github.com/usemoss/moss
```

Pick the latest version under "Up to Next Major Version".

Or in `Package.swift`:

```swift
dependencies: [
    .package(url: "https://github.com/usemoss/moss", from: "0.2.0"),
],
targets: [
    .target(name: "YourTarget", dependencies: [
        .product(name: "Moss", package: "moss"),
    ]),
]
```

## Quick start

```swift
import Moss

let client = try MossClient(projectId: "your_project_id", projectKey: "your_project_key")
defer { client.close() }

// Create an index, load it, query.
_ = try await client.createIndex("support-docs", docs: [
    .init(id: "1", text: "Refunds are processed within 3-5 business days."),
    .init(id: "2", text: "You can track your order on the dashboard."),
])

try await client.loadIndex("support-docs")

let result = try await client.query("support-docs", "how long do refunds take?")
for doc in result.docs {
    print(String(format: "[%.3f] %@", doc.score, doc.text))
}
```

## Authentication

Two ways to authenticate:

**Static project key** — simplest, fine for prototyping:

```swift
let client = try MossClient(projectId: id, projectKey: key)
```

**`Authenticator` protocol** — for apps that fetch short-lived tokens from
your backend:

```swift
final class MyAuth: Authenticator {
    func getAuthHeader() async throws -> String {
        // Fetch / refresh a bearer token from your server.
        return try await myServer.fetchToken()
    }
}

let client = try MossClient(projectId: id, authenticator: MyAuth())
```

## Memory pressure

When the OS sends a memory warning, ask the SDK to drop reclaimable
caches:

```swift
NotificationCenter.default.addObserver(
    forName: UIApplication.didReceiveMemoryWarningNotification,
    object: nil,
    queue: .main
) { _ in
    Task { _ = try? await client.onMemoryPressure(.critical) }
}
```

On-disk caches are kept; only in-memory structures are freed. Next
`loadIndex` rehydrates from disk.

## Threading

All operations are `async throws` and dispatch work onto a background
thread. The underlying client is thread-safe — you can share a single
`MossClient` across the app.

## Custom cache directory (advanced)

`MossClient` automatically caches model files under
`<Library/Caches>/moss-models/`. To point it somewhere else — e.g. a
shared App Group container so multiple targets share the same models —
call `setModelCacheDir` *before* constructing your first client:

```swift
try MossClient.setModelCacheDir("/path/to/your/cache")
let client = try MossClient(projectId: id, projectKey: key)
```

## Reporting issues

Open an issue at <https://github.com/usemoss/moss/issues>.

## License

[PolyForm Shield 1.0.0](./LICENSE.txt)
