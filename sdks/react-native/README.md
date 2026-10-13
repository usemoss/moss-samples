# @moss-dev/moss-react-native

React Native / Expo module for [Moss](https://github.com/usemoss/moss) — on-device semantic search.

Closes the gap described in [usemoss/moss#432](https://github.com/usemoss/moss/issues/432).

## Status

| Platform | Support |
|----------|---------|
| **iOS** | Native via `Moss.xcframework` (same binary as the Swift SDK, release `v0.6.2`) |
| **Android** | Stub — throws until Android native builds land ([#411](https://github.com/usemoss/moss/issues/411)) |
| **Expo Go** | Not supported (custom native code; use a [dev client](https://docs.expo.dev/develop/development-builds/introduction/) / `expo prebuild`) |

## Install

```bash
npx expo install @moss-dev/moss-react-native
```

Add the config plugin in `app.json` / `app.config.js`:

```json
{
  "expo": {
    "plugins": ["@moss-dev/moss-react-native"]
  }
}
```

Then regenerate native projects:

```bash
npx expo prebuild
npx pod-install
```

CocoaPods downloads `Moss.xcframework` during `pod install` (checksum-verified against the Swift SDK release).

## Quick start

> [!WARNING]
> The snippet below reads the project key from `EXPO_PUBLIC_*`, which is fine
> for a local dev build but **must not ship in a production app**. See
> [Credentials](#credentials) before you release.

```tsx
import { MossClient } from '@moss-dev/moss-react-native';

// Development builds only — see the Credentials section below.
const client = new MossClient(process.env.EXPO_PUBLIC_MOSS_PROJECT_ID!, process.env.EXPO_PUBLIC_MOSS_PROJECT_KEY!);

await client.createIndex('support-docs', [
  { id: '1', text: 'Refunds are processed within 3-5 business days.' },
  { id: '2', text: 'You can track your order on the dashboard.' },
]);

await client.loadIndex('support-docs');
const result = await client.query('support-docs', 'how long do refunds take?');
for (const doc of result.docs) {
  console.log(`[${doc.score.toFixed(3)}] ${doc.text}`);
}

client.close();
```

## Credentials

Anything in an `EXPO_PUBLIC_*` variable is **inlined into the JS bundle at build
time**. It is shipped to every user and can be read straight out of the app —
it is not a secret. A project key exposed that way is usable by anyone who
extracts it, and `MossClient` also exposes mutating calls (`createIndex`,
`addDocs`, `deleteIndex`), so a leaked key is not merely read access to your
project.

So:

- **Development / internal builds** — `EXPO_PUBLIC_MOSS_PROJECT_KEY` is fine.
- **Production apps** — do not embed a project key. Use the token form below.

### Short-lived tokens (production)

Pass `getAuthToken` instead of a project key. It is called whenever the native
runtime needs a bearer token, so your backend mints a short-lived, scoped one
and nothing long-lived is ever in the bundle:

```ts
const client = new MossClient({
  projectId: process.env.EXPO_PUBLIC_MOSS_PROJECT_ID!,
  getAuthToken: async () => {
    const res = await fetch('https://api.example.com/moss-token', {
      headers: { Authorization: `Bearer ${await mySessionToken()}` },
    });
    const { token } = await res.json();
    return token; // raw token — do NOT prefix with "Bearer "
  },
});
```

Notes:

- Return the **raw token**. The native side builds the
  `Authorization: Bearer <token>` header itself.
- `getAuthToken` may be called from a background thread and more than once —
  cache until expiry if the round trip is expensive.
- Throwing (or returning a non-string / empty string) fails the in-flight
  request with your error rather than hanging it.
- `projectId` is not a secret; only the key is.

This is the same mechanism as the Swift SDK's `Authenticator`, wired through
`moss_client_new_with_authenticator` in the native ABI.

## API

Mirrors the Node `@moss-dev/moss` client for the core cloud + local query loop:

- `new MossClient(projectId, projectKey)` (development builds)
- `new MossClient({ projectId, getAuthToken, baseUrl? })` (short-lived tokens; see [Credentials](#credentials))
- `createIndex(name, docs, options?)`
- `addDocs(name, docs, options?)`
- `loadIndex(name, options?)` / `unloadIndex(name)`
- `query(name, query, options?)`
- `listIndexes()` / `getIndex(name)` / `deleteIndex(name)`
- `close()`
- `MossClient.sdkVersion`
- `MossClient.setModelCacheDir(path)` (optional; iOS defaults to `Library/Caches/moss-models`)

The Swift SDK's `Authenticator` is bridged (see [Credentials](#credentials)).
Session APIs remain out of scope for this first release.

### Metadata filters

`query` takes the same `filter` shape as `@moss-dev/moss`:

```ts
await client.query('support-docs', 'refund timing', {
  filter: { field: 'locale', condition: { $eq: 'en-US' } },
});
```

Pass `filterJson` instead if you already hold the engine's serialized form.
Supplying both is an error rather than a silent precedence rule.

### Custom embeddings

Passing documents with an `embedding` makes `createIndex` select `modelId: 'custom'`,
which means there is no on-device model to embed query text with. Supply the query
vector yourself:

```ts
await client.createIndex('vectors', [
  { id: '1', text: 'Refunds take 3-5 business days.', embedding: myVector },
]);
await client.loadIndex('vectors');

const result = await client.query('vectors', 'refund timing', {
  embedding: myQueryVector, // must match the index dimensionality
});
```

## Requirements

- Expo SDK 54+ (or a React Native app with Expo Modules)
- iOS 16.4+ (Expo SDK 54+ baseline)
- Xcode 15+
- Apple Silicon Mac for the iOS Simulator (the Moss.xcframework simulator slice is arm64-only)
- A development build / `expo prebuild` — Expo Go is not supported
- Until this package is published to npm, install from a local path or git checkout (`file:…` / `github:…`)

## Development (this monorepo)

```bash
cd sdks/react-native
npm install
npm run build
```

See [`examples/react-native/`](../../examples/react-native/) for a minimal usage sketch.

## License

[BSD 2-Clause](./LICENSE)
