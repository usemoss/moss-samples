# Moss Go SDK

The Go SDK follows the same two-layer design as the other Moss SDKs:

- `sdks/go/sdk/` contains the public Go SDK
- `sdks/go/bindings/` wraps the native `libmoss` runtime via CGO

## Install

```bash
go get github.com/usemoss/moss/sdks/go/sdk
go run github.com/usemoss/moss/sdks/go/tools/install@latest --vendor
```

The install tool downloads the static `libmoss` library for your platform from
[Moss C SDK GitHub Releases](https://github.com/usemoss/moss/releases). You need
CGO and a C compiler, but not a manual C SDK download or `LD_LIBRARY_PATH`.
For external projects, the explicit `--vendor` option lets the installer vendor
the bindings before placing the library next to them, so the normal `go build`
command finds it.

Native bindings currently support Linux (`amd64`, `arm64`) and Apple Silicon
macOS (`arm64`). Other platforms, including Windows, use the
bindings-unavailable stub until a compatible native release is available.

From a checkout of the bindings package, you can instead use:

```bash
go generate github.com/usemoss/moss/sdks/go/bindings
```

## Local development

```bash
./sdks/go/scripts/link_dev_lib.sh c-sdk-v0.9.0
cd sdks/go/sdk
CGO_ENABLED=1 go test ./...
```

Unit tests run without native libraries when `CGO_ENABLED=0`.

## Publishing

See [`bindings/README.md`](./bindings/README.md) and
[`.github/workflows/publish-go-sdk.yml`](../../.github/workflows/publish-go-sdk.yml).

The public SDK module lives under [`sdk/`](./sdk/), and the native bindings module
lives under [`bindings/`](./bindings/).
