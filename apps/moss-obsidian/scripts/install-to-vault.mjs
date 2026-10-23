#!/usr/bin/env node
/**
 * Build the plugin and copy it into a vault:
 *
 *   npm run install-to-vault -- /path/to/vault
 *
 * Copies main.js, mossWorker.js, manifest.json, styles.css and the runtime
 * dependency (`node_modules/@moss-dev/*`, which contains the native Moss
 * core) into `<vault>/.obsidian/plugins/moss-search/`. Existing settings
 * (`data.json`) and the index cache are left untouched.
 */
import { execSync } from "node:child_process";
import { cpSync, existsSync, mkdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
const vault = process.argv[2];

if (!vault) {
  console.error("Usage: npm run install-to-vault -- /path/to/vault");
  process.exit(1);
}
if (!existsSync(path.join(vault, ".obsidian"))) {
  console.error(`Not an Obsidian vault (no .obsidian folder): ${vault}`);
  process.exit(1);
}

const manifest = JSON.parse(readFileSync(path.join(root, "manifest.json"), "utf8"));
const dest = path.join(vault, ".obsidian", "plugins", manifest.id);

// Validate everything BEFORE touching the vault, so a failed precondition
// can't leave a half-installed plugin behind.
const depSrc = path.join(root, "node_modules", "@moss-dev");
if (!existsSync(depSrc)) {
  console.error("node_modules/@moss-dev missing — run `npm install` first.");
  process.exit(1);
}

execSync("npm run build", { cwd: root, stdio: "inherit" });

for (const file of ["main.js", "mossWorker.js", "manifest.json", "styles.css"]) {
  if (!existsSync(path.join(root, file))) {
    console.error(`Build output missing: ${file}`);
    process.exit(1);
  }
}

mkdirSync(dest, { recursive: true });
for (const file of ["main.js", "mossWorker.js", "manifest.json", "styles.css"]) {
  cpSync(path.join(root, file), path.join(dest, file));
}
cpSync(depSrc, path.join(dest, "node_modules", "@moss-dev"), { recursive: true });

console.log(`Installed ${manifest.name} v${manifest.version} → ${dest}`);
console.log("Enable it under Settings → Community plugins, then add your Moss project ID/key.");
