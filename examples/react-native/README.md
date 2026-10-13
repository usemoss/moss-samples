# React Native / Expo example (Moss)

Minimal usage sketch for [`@moss-dev/moss-react-native`](../../sdks/react-native/).

This is not a full Expo app (no `node_modules` committed). Scaffold your own with:

```bash
npx create-expo-app moss-rn-demo
cd moss-rn-demo
npx expo install @moss-dev/moss-react-native
```

Add the plugin in `app.json`:

```json
{
  "expo": {
    "plugins": ["@moss-dev/moss-react-native"]
  }
}
```

Then:

```bash
npx expo prebuild
npx expo run:ios
```

## Example screen

```tsx
import { useEffect, useState } from 'react';
import { Button, ScrollView, Text, View } from 'react-native';
import { MossClient, type SearchResult } from '@moss-dev/moss-react-native';

// Development build only. `EXPO_PUBLIC_*` values are inlined into the shipped JS
// bundle, so a project key set this way is readable by anyone with the app and
// grants mutating access (createIndex / addDocs / deleteIndex). Do not ship it
// in a production app — see the package README's "Credentials" section.
const PROJECT_ID = process.env.EXPO_PUBLIC_MOSS_PROJECT_ID!;
const PROJECT_KEY = process.env.EXPO_PUBLIC_MOSS_PROJECT_KEY!;

export default function App() {
  const [result, setResult] = useState<SearchResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const client = new MossClient(PROJECT_ID, PROJECT_KEY);
    let cancelled = false;

    (async () => {
      try {
        await client.createIndex('rn-demo', [
          { id: '1', text: 'Refunds are processed within 3-5 business days.' },
          { id: '2', text: 'Shipping usually takes 2 business days.' },
        ]);
        await client.loadIndex('rn-demo');
        const search = await client.query('rn-demo', 'how long do refunds take?');
        if (!cancelled) setResult(search);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      } finally {
        client.close();
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <ScrollView contentContainerStyle={{ padding: 24, gap: 12 }}>
      <Text style={{ fontSize: 22, fontWeight: '600' }}>Moss RN demo</Text>
      {error ? <Text style={{ color: 'crimson' }}>{error}</Text> : null}
      {result?.docs.map((doc) => (
        <View key={doc.id}>
          <Text>
            [{doc.score.toFixed(3)}] {doc.text}
          </Text>
        </View>
      ))}
      <Button title={`SDK ${MossClient.sdkVersion}`} onPress={() => {}} />
    </ScrollView>
  );
}
```

## Notes

- iOS only for on-device query today. Android throws until [#411](https://github.com/usemoss/moss/issues/411) lands.
- Requires a development build — Expo Go cannot load custom native modules.
