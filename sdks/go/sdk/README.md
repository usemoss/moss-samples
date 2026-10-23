# Moss client library for Go

`moss` provides a typed Go client for Moss semantic search workflows.

The Go SDK now has two layers:

- a public SDK in `sdks/go/sdk`
- native `libmoss` bindings in `sdks/go/bindings`

## Features

- typed Go client and models
- bindings-backed index creation and document mutation
- bindings-backed index metadata and document reads
- local index loading, metadata, and query via native bindings
- cloud query fallback when an index is not loaded locally
- optional caller-provided embeddings for custom indexes
- env-gated live integration tests

## Current limitations

- CGO and a C compiler are required for full SDK functionality (`CGO_ENABLED=1`)
- Native bindings support Linux (`amd64`, `arm64`) and Apple Silicon macOS
  (`arm64`); unsupported platforms use the bindings-unavailable stub
- cloud query fallback supports `TopK` and caller-provided embeddings; `Alpha` and `Filter` require a locally loaded index
- `LoadIndexOptions.CachePath` is not exposed by the current `libmoss` C API yet

## Installation

```bash
go get github.com/usemoss/moss/sdks/go/sdk
go run github.com/usemoss/moss/sdks/go/tools/install@latest --vendor
```

The install tool downloads the static `libmoss` library for your platform. See
[`../bindings/README.md`](../bindings/README.md) for supported platforms and
toolchain notes.
The explicit `--vendor` option vendors the SDK so CGO can link the downloaded
library from a writable directory; commit `vendor/` if your project commits
vendored dependencies. Run it after your application imports the SDK so the
bindings package is included in `vendor/`.
In a Go workspace, the installer uses `go work vendor` instead.

Monorepo development uses the workspace in [`../go.work`](../go.work) and
[`../scripts/link_dev_lib.sh`](../scripts/link_dev_lib.sh).

## Quick start

```go
package main

import (
	"context"
	"fmt"
	"log"

	"github.com/usemoss/moss/sdks/go/sdk"
)

func main() {
	ctx := context.Background()

	client := moss.NewClient("your-project-id", "your-project-key")
	defer client.Close()

	docs := []moss.DocumentInfo{
		{
			ID:   "doc-1",
			Text: "Refunds are processed within five to seven business days.",
			Metadata: map[string]string{
				"topic": "refunds",
			},
		},
		{
			ID:   "doc-2",
			Text: "Orders can be tracked from the account dashboard.",
			Metadata: map[string]string{
				"topic": "shipping",
			},
		},
	}

	result, err := client.CreateIndex(ctx, "support-docs", docs, nil)
	if err != nil {
		log.Fatal(err)
	}

	fmt.Println("created job:", result.JobID)

	if _, err := client.LoadIndex(ctx, "support-docs", &moss.LoadIndexOptions{}); err != nil {
		log.Fatal(err)
	}

	search, err := client.Query(ctx, "support-docs", "how long do refunds take?", &moss.QueryOptions{
		TopK: 3,
	})
	if err != nil {
		log.Fatal(err)
	}

	for _, doc := range search.Docs {
		fmt.Printf("%s %.3f\n", doc.ID, doc.Score)
	}
}
```

## Custom embeddings

If your documents already have embeddings, omit `ModelID` and the SDK will
default to `"custom"` automatically:

```go
docs := []moss.DocumentInfo{
	{
		ID:        "doc-1",
		Text:      "Attach a caller-provided embedding.",
		Embedding: []float32{1, 0, 0, 0},
	},
	{
		ID:        "doc-2",
		Text:      "This index uses custom vectors.",
		Embedding: []float32{0, 1, 0, 0},
	},
}

_, err := client.CreateIndex(ctx, "custom-embeddings", docs, nil)
if err != nil {
	log.Fatal(err)
}

if _, err := client.LoadIndex(ctx, "custom-embeddings", &moss.LoadIndexOptions{}); err != nil {
	log.Fatal(err)
}

results, err := client.Query(ctx, "custom-embeddings", "", &moss.QueryOptions{
	Embedding: []float32{1, 0, 0, 0},
	TopK:      5,
})
```

All documents must either provide embeddings or omit them entirely in the same
batch.

## Examples

Runnable examples live here:

- [`../../../examples/go/basic/main.go`](../../../examples/go/basic/main.go)
- [`../../../examples/go/custom-embeddings/main.go`](../../../examples/go/custom-embeddings/main.go)

Run them from the monorepo:

```bash
../scripts/link_dev_lib.sh c-sdk-v0.9.0
cd ../../../examples/go
go run ./basic
```

## Integration tests

Live tests are skipped unless both of these are set:

```bash
export MOSS_TEST_PROJECT_ID=...
export MOSS_TEST_PROJECT_KEY=...
```

Then run:

```bash
cd sdks/go/sdk
go test ./...

# Live integration (requires credentials + native lib from link_dev_lib.sh):
CGO_ENABLED=1 go test ./...
```
