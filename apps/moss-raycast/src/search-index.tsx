import { useRef, useState } from "react";
import {
  Action,
  ActionPanel,
  List,
  getPreferenceValues,
  showToast,
  Toast,
} from "@raycast/api";
import { useCachedPromise } from "@raycast/utils";
import { MossClient } from "@moss-dev/moss";

interface Preferences {
  projectId: string;
  projectKey: string;
  indexName: string;
}

export default function SearchIndex() {
  const preferences = getPreferenceValues<Preferences>();
  const [searchText, setSearchText] = useState("");
  const clientRef = useRef<MossClient | null>(null);
  const loadedRef = useRef(false);

  const { data, isLoading } = useCachedPromise(
    async (query: string) => {
      if (!query.trim()) {
        return [];
      }

      if (!clientRef.current) {
        clientRef.current = new MossClient(
          preferences.projectId,
          preferences.projectKey,
        );
      }
      const client = clientRef.current;

      if (!loadedRef.current) {
        await client.loadIndex(preferences.indexName);
        loadedRef.current = true;
      }

      const result = await client.query(preferences.indexName, query, {
        topK: 10,
      });
      return result.docs;
    },
    [searchText],
    {
      onError(error) {
        showToast({
          style: Toast.Style.Failure,
          title: "Moss query failed",
          message: error.message,
        });
      },
    },
  );

  return (
    <List
      isLoading={isLoading}
      onSearchTextChange={setSearchText}
      searchBarPlaceholder={`Search "${preferences.indexName}"...`}
      throttle
    >
      {(data ?? []).map((doc) => (
        <List.Item
          key={doc.id}
          title={doc.text}
          subtitle={`Score: ${doc.score.toFixed(3)}`}
          actions={
            <ActionPanel>
              <Action.CopyToClipboard title="Copy Text" content={doc.text} />
            </ActionPanel>
          }
        />
      ))}
    </List>
  );
}
