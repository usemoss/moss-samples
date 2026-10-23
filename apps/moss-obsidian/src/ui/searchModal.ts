import { Keymap, Notice, SuggestModal, TFile, type App } from "obsidian";
import { previewText, type SearchHit } from "../search/search";

export interface SearchModalCallbacks {
  search: (query: string) => Promise<SearchHit[]>;
  statusLine: () => string;
}

/**
 * Quick-switcher style semantic search. Typing triggers a debounced query
 * against the local Moss session; choosing a result opens the note at the
 * matching section.
 */
export class MossSearchModal extends SuggestModal<SearchHit> {
  private latestQuery = "";
  private lastHits: SearchHit[] = [];
  private pendingTimer: ReturnType<typeof setTimeout> | undefined;
  private pendingResolve: (() => void) | undefined;

  constructor(
    app: App,
    private readonly callbacks: SearchModalCallbacks,
  ) {
    super(app);
    this.setPlaceholder("Search your vault by meaning…");
    this.setInstructions([
      { command: "↑↓", purpose: "navigate" },
      { command: "↵", purpose: "open note at section" },
      { command: "mod ↵", purpose: "open in new tab" },
      { command: "esc", purpose: "dismiss" },
    ]);
    // Bare Enter is bound by SuggestModal; Mod+Enter needs its own binding.
    this.scope.register(["Mod"], "Enter", (evt) => {
      this.selectActiveSuggestion(evt);
      return false;
    });
    this.emptyStateText = "No matches yet.";
    this.limit = 50;
  }

  onOpen(): void {
    super.onOpen();
    this.modalEl.addClass("moss-search-modal");
    this.updateStatus();
  }

  onClose(): void {
    if (this.pendingTimer) {
      clearTimeout(this.pendingTimer);
    }
    this.pendingResolve?.();
    this.pendingResolve = undefined;
    super.onClose();
  }

  private updateStatus(): void {
    this.modalEl.querySelector(".moss-search-status")?.remove();
    const status = this.callbacks.statusLine();
    if (status) {
      this.modalEl.createDiv({ cls: "moss-search-status", text: status });
    }
  }

  /**
   * Debounce without leaving earlier calls hanging: a superseded call is
   * resolved immediately and answers with the last known hits, so Obsidian
   * never awaits a promise that will not settle.
   */
  private settle(): Promise<void> {
    if (this.pendingTimer) {
      clearTimeout(this.pendingTimer);
    }
    this.pendingResolve?.();
    return new Promise<void>((resolve) => {
      this.pendingResolve = resolve;
      this.pendingTimer = setTimeout(() => {
        this.pendingResolve = undefined;
        resolve();
      }, 180);
    });
  }

  async getSuggestions(query: string): Promise<SearchHit[]> {
    const trimmed = query.trim();
    this.latestQuery = trimmed;
    this.emptyStateText = "No matches yet.";
    this.updateStatus();
    if (trimmed.length < 2) {
      this.lastHits = [];
      return [];
    }
    await this.settle();
    if (trimmed !== this.latestQuery) {
      return this.lastHits;
    }
    try {
      const hits = await this.callbacks.search(trimmed);
      if (trimmed !== this.latestQuery) {
        return this.lastHits;
      }
      this.lastHits = hits;
      return hits;
    } catch (err) {
      console.error("[moss] search failed", err);
      // Only surface the failure if it belongs to the query still on screen.
      if (trimmed === this.latestQuery) {
        this.emptyStateText = `Search failed: ${err instanceof Error ? err.message : String(err)}`;
        return [];
      }
      return this.lastHits;
    }
  }

  renderSuggestion(hit: SearchHit, el: HTMLElement): void {
    el.addClass("moss-search-hit");
    const header = el.createDiv({ cls: "moss-search-hit-header" });
    header.createSpan({ cls: "moss-search-hit-title", text: hit.title });
    header.createSpan({ cls: "moss-search-hit-score", text: hit.score.toFixed(2) });

    const crumb = hit.headingPath.split(" > ").slice(1).join(" › ");
    if (crumb) {
      el.createDiv({ cls: "moss-search-hit-heading", text: crumb });
    }
    el.createDiv({ cls: "moss-search-hit-preview", text: previewText(hit.text) });
    el.createDiv({
      cls: "moss-search-hit-path",
      text: `${hit.filePath} · L${hit.startLine}`,
    });
  }

  async onChooseSuggestion(hit: SearchHit, evt: MouseEvent | KeyboardEvent): Promise<void> {
    const file = this.app.vault.getAbstractFileByPath(hit.filePath);
    if (!(file instanceof TFile)) {
      new Notice(`Moss: “${hit.filePath}” no longer exists — rebuild the index to drop stale results.`);
      return;
    }
    const leaf = this.app.workspace.getLeaf(Keymap.isModEvent(evt));
    await leaf.openFile(file, {
      eState: { line: Math.max(0, hit.startLine - 1) },
    });
  }
}
