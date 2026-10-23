# Moss .NET SDK

The .NET SDK for [Moss](https://github.com/usemoss/moss) — fast on-device
retrieval. It wraps the native `libmoss` runtime through P/Invoke and exposes an
idiomatic, async C# API for index management, hybrid search, and metadata
filtering.

## Architecture

```
        ┌──────────────────────────────────┐
        │      Your application code       │
        └──────────────┬───────────────────┘
                       │
        ┌──────────────▼───────────────────┐
        │  Moss  (managed C#)              │  ← src/Moss
        │  MossClient — async API for      │
        │  indexing, querying, management  │
        └──────────────┬───────────────────┘
                       │  P/Invoke ([DllImport("moss")])
        ┌──────────────▼───────────────────┐
        │  libmoss  (native C ABI)         │  ← prebuilt runtime
        │  hybrid search, data models      │
        └──────────────────────────────────┘
```

- `src/Moss/` — the public SDK. `MossClient` plus the data models.
- `src/Moss/Interop/` — the P/Invoke layer: raw `libmoss` declarations, C-ABI
  struct mirrors, UTF-8 marshaling, and native-memory conversion/cleanup.

The interop layer targets the same stable C ABI (`libmoss.h`) that the Go
bindings bind via cgo.

## Quick start

```csharp
using Moss;

using var client = new MossClient("your_project_id", "your_project_key");

await client.CreateIndexAsync("support-docs", new[]
{
    new DocumentInfo("1", "Refunds are processed within 3-5 business days."),
    new DocumentInfo("2", "You can track your order on the dashboard."),
});

await client.LoadIndexAsync("support-docs");

var results = await client.QueryAsync(
    "support-docs", "how long do refunds take?", new QueryOptions { TopK = 3 });

foreach (var doc in results.Docs)
    Console.WriteLine($"[{doc.Score:F3}] {doc.Text}");
```

### Metadata filtering

Attach string metadata at index time and pass a JSON filter at query time:

```csharp
await client.AddDocsAsync("support-docs", new[]
{
    new DocumentInfo("3", "EU refund policy…",
        metadata: new Dictionary<string, string> { ["region"] = "eu" }),
});

var results = await client.QueryAsync("support-docs", "refund policy",
    new QueryOptions
    {
        TopK = 5,
        FilterJson = "{\"region\": \"eu\"}",
    });
```

## API surface

| Area | Methods |
|------|---------|
| Indexes | `CreateIndexAsync`, `GetIndexAsync`, `ListIndexesAsync`, `DeleteIndexAsync` |
| Documents | `AddDocsAsync`, `DeleteDocsAsync`, `GetDocsAsync` |
| Jobs | `GetJobStatusAsync` |
| Local runtime | `LoadIndexAsync`, `UnloadIndexAsync`, `RefreshIndexAsync`, `QueryAsync` |

All methods are asynchronous and accept a `CancellationToken`. Failures from the
native runtime surface as `MossException` (carrying the status `Code` and the
`moss_last_error` message).

## The native runtime

The SDK calls into `libmoss`, distributed as a prebuilt native library
(`libmoss.so` on Linux, `libmoss.dylib` on macOS, `moss.dll` on Windows). It
must be discoverable at runtime — on the standard library search path, next to
your application, or via `NativeLibrary` resolution. Building and unit-testing
the SDK does **not** require the native library; only running queries does.

## Building and testing

Requires the [.NET 8 SDK](https://dotnet.microsoft.com/download/dotnet/8.0).

```bash
cd sdks/dotnet
dotnet build
dotnet test        # unit tests run without libmoss
```

The unit tests cover the managed logic and the marshaling layer (UTF-8
round-trips, native buffer packing, ABI struct sizes) and do not load the native
library.

## License

[BSD 2-Clause License](../../LICENSE)
