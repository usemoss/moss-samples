import { Notice, PluginSettingTab, Setting, type App } from "obsidian";
import type { MossModelId } from "./moss/client";
import type MossSearchPlugin from "./main";

export interface MossSearchSettings {
  projectId: string;
  projectKey: string;
  model: MossModelId;
  /** One vault-relative folder per line. */
  excludedFolders: string;
  topK: number;
  /** Hybrid blend: 1.0 = pure semantic, 0.0 = pure keyword. */
  alpha: number;
  /** Show only the best chunk per note. */
  onePerNote: boolean;
  /** Push the index to Moss Cloud after indexing. Off by default: notes stay local. */
  cloudSync: boolean;
  /** Optional absolute path to a Node 20+ binary for the worker. */
  nodePath: string;
  /** Chunk size in characters. */
  maxCharsPerChunk: number;
  /** Random per-vault id (generated on first load); names the cloud index. */
  vaultId: string;
}

export const DEFAULT_SETTINGS: MossSearchSettings = {
  projectId: "",
  projectKey: "",
  model: "moss-minilm",
  excludedFolders: "templates\n",
  topK: 20,
  alpha: 0.7,
  onePerNote: false,
  cloudSync: false,
  nodePath: "",
  maxCharsPerChunk: 1600,
  vaultId: "",
};

export class MossSettingTab extends PluginSettingTab {
  constructor(
    app: App,
    private readonly plugin: MossSearchPlugin,
  ) {
    super(app, plugin);
  }

  display(): void {
    const { containerEl } = this;
    containerEl.empty();

    new Setting(containerEl).setName("Moss project").setHeading();

    new Setting(containerEl)
      .setName("Project ID")
      .setDesc("From the Moss portal (moss.dev). Needed to open a SessionIndex; your notes are embedded locally.")
      .addText((text) =>
        text
          .setPlaceholder("proj_…")
          .setValue(this.plugin.settings.projectId)
          .onChange(async (value) => {
            const changed = value.trim() !== this.plugin.settings.projectId;
            this.plugin.settings.projectId = value.trim();
            await this.plugin.saveSettings();
            if (changed) this.plugin.noteSessionSettingsChanged();
          }),
      );

    new Setting(containerEl)
      .setName("Project key")
      .setDesc("Stored in this plugin's data.json inside your vault's .obsidian folder. Exclude it from sync if you share the vault.")
      .addText((text) => {
        text.inputEl.type = "password";
        text.inputEl.autocomplete = "off";
        text
          .setPlaceholder("••••••••")
          .setValue(this.plugin.settings.projectKey)
          .onChange(async (value) => {
            const changed = value.trim() !== this.plugin.settings.projectKey;
            this.plugin.settings.projectKey = value.trim();
            await this.plugin.saveSettings();
            if (changed) this.plugin.noteSessionSettingsChanged();
          });
      });

    new Setting(containerEl)
      .setName("Embedding model")
      .setDesc("moss-minilm is fast and fine for most vaults. Changing this requires a rebuild.")
      .addDropdown((dropdown) =>
        dropdown
          .addOption("moss-minilm", "moss-minilm (default)")
          .addOption("moss-mediumlm", "moss-mediumlm")
          .setValue(this.plugin.settings.model)
          .onChange(async (value) => {
            const next = value === "moss-mediumlm" ? "moss-mediumlm" : "moss-minilm";
            const changed = next !== this.plugin.settings.model;
            this.plugin.settings.model = next;
            await this.plugin.saveSettings();
            if (changed) this.plugin.noteSessionSettingsChanged();
          }),
      );

    new Setting(containerEl).setName("Indexing").setHeading();

    new Setting(containerEl)
      .setName("Excluded folders")
      .setDesc("One vault-relative folder per line. .obsidian, .trash and .git are always skipped. Takes effect on the next rebuild.")
      .addTextArea((area) => {
        area.inputEl.rows = 4;
        area.inputEl.cols = 40;
        area.setValue(this.plugin.settings.excludedFolders).onChange(async (value) => {
          this.plugin.settings.excludedFolders = value;
          await this.plugin.saveSettings();
        });
      });

    new Setting(containerEl)
      .setName("Chunk size (characters)")
      .setDesc("Sections longer than this are split into overlapping windows. Default 1600.")
      .addText((text) =>
        text.setValue(String(this.plugin.settings.maxCharsPerChunk)).onChange(async (value) => {
          const n = Number.parseInt(value, 10);
          if (!Number.isFinite(n) || n < 200 || n > 8000) {
            new Notice("Moss: chunk size must be between 200 and 8000 characters.");
            text.setValue(String(this.plugin.settings.maxCharsPerChunk));
            return;
          }
          if (n !== this.plugin.settings.maxCharsPerChunk) {
            this.plugin.settings.maxCharsPerChunk = n;
            await this.plugin.saveSettings();
            new Notice("Moss: chunk size changed — run “Moss: Rebuild index” to apply.");
          }
        }),
      );

    new Setting(containerEl).setName("Search").setHeading();

    new Setting(containerEl)
      .setName("Results")
      .setDesc("Maximum number of chunks returned per query.")
      .addSlider((slider) =>
        slider
          .setLimits(5, 50, 5)
          .setValue(this.plugin.settings.topK)
          .setDynamicTooltip()
          .onChange(async (value) => {
            this.plugin.settings.topK = value;
            await this.plugin.saveSettings();
          }),
      );

    new Setting(containerEl)
      .setName("Semantic weight (alpha)")
      .setDesc("1.0 = pure semantic, 0.0 = pure keyword (BM25). Default 0.7.")
      .addSlider((slider) =>
        slider
          .setLimits(0, 1, 0.1)
          .setValue(this.plugin.settings.alpha)
          .setDynamicTooltip()
          .onChange(async (value) => {
            this.plugin.settings.alpha = Math.round(value * 10) / 10;
            await this.plugin.saveSettings();
          }),
      );

    new Setting(containerEl)
      .setName("One result per note")
      .setDesc("Collapse multiple matching sections of the same note into its best match.")
      .addToggle((toggle) =>
        toggle.setValue(this.plugin.settings.onePerNote).onChange(async (value) => {
          this.plugin.settings.onePerNote = value;
          await this.plugin.saveSettings();
        }),
      );

    new Setting(containerEl).setName("Cloud").setHeading();

    new Setting(containerEl)
      .setName("Sync index to Moss Cloud")
      .setDesc(
        "Off by default. When on, the index (note text, headings, line numbers and locally computed embeddings) " +
          "is uploaded to your Moss project after indexing so another device can restore it.",
      )
      .addToggle((toggle) =>
        toggle.setValue(this.plugin.settings.cloudSync).onChange(async (value) => {
          this.plugin.settings.cloudSync = value;
          await this.plugin.saveSettings();
        }),
      );

    new Setting(containerEl).setName("Advanced").setHeading();

    new Setting(containerEl)
      .setName("Node binary path")
      .setDesc("Optional. Absolute path to a Node 20+ binary for the Moss worker. Leave blank to auto-detect (falls back to Obsidian's runtime).")
      .addText((text) =>
        text
          .setPlaceholder("/opt/homebrew/bin/node")
          .setValue(this.plugin.settings.nodePath)
          .onChange(async (value) => {
            const changed = value.trim() !== this.plugin.settings.nodePath;
            this.plugin.settings.nodePath = value.trim();
            await this.plugin.saveSettings();
            if (changed) {
              new Notice("Moss: Node path changed — run “Moss: Restart Moss worker” to apply.");
            }
          }),
      );

    new Setting(containerEl)
      .setName("Rebuild index")
      .setDesc("Re-scan and re-embed every note. Use after changing the model or exclusions.")
      .addButton((button) =>
        button.setButtonText("Rebuild").onClick(() => {
          void this.plugin.rebuildIndex();
        }),
      );
  }
}
