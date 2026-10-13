# moss-core — Ruby bindings for libmoss

`moss-core` wraps the native `libmoss` runtime for Ruby via [FFI](https://github.com/ffi/ffi).

It mirrors the role of the other language bindings packages in this repository:

- native runtime access
- local index loading
- local query execution
- cloud-backed manage operations exposed through the native client
- ephemeral in-memory sessions

Most users should depend on the higher-level [`moss`](../sdk) gem instead of
using these bindings directly.

## Status

The bindings attach to `libmoss` lazily, on first client construction. If the
library cannot be found, constructing a client raises
`Moss::Core::BindingsUnavailableError` with guidance rather than crashing at
`require` time. Use `Moss::Core.available?` to probe without raising.

## Providing libmoss

Download the matching `libmoss` C SDK release archive for your platform from:

- <https://github.com/usemoss/moss/releases/tag/c-sdk-v0.9.0>

Extract it so you have:

```text
<sdk-root>/
├── include/libmoss.h
└── lib/libmoss.{dylib,so}
```

Then point the bindings at it with either environment variable:

```bash
export MOSS_LIB_DIR="<sdk-root>/lib"        # directory containing the library
# or
export MOSS_LIBRARY_PATH="<sdk-root>/lib/libmoss.dylib"  # exact file
```

The bindings `dlopen` the library by absolute path, so on macOS you do **not**
need `DYLD_LIBRARY_PATH` for the prebuilt `libmoss.dylib`.

## API surface

```ruby
require "moss/core"

Moss::Core.available?            # => true / false
Moss::Core.libmoss_sdk_version   # => "0.9.0" (or nil when unavailable)

manage = Moss::Core::ManageClient.new(project_id, project_key)
manage.create_index("docs", [Moss::Core::DocumentInfo.new(id: "1", text: "hi")], "moss-minilm")
manage.list_indexes
manage.close

index = Moss::Core::IndexManager.new(project_id, project_key)
index.load_index("docs")
index.query("docs", "hello", top_k: 5)
index.close
```

## Development

```bash
cd sdks/ruby/bindings
ruby -Itest -Ilib test/library_test.rb   # attach test auto-skips without libmoss
```
