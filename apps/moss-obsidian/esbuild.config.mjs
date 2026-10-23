import * as esbuild from "esbuild";

const watch = process.argv.includes("--watch");

// Obsidian loads a single CommonJS `main.js` from the plugin folder. The
// Moss native runtime is deliberately NOT bundled: it runs in a separate
// worker process (`mossWorker.js`) that resolves `@moss-dev/moss` from the
// plugin folder's `node_modules`, mirroring apps/moss-vscode.
const external = [
  "obsidian",
  "@moss-dev/moss",
  "@moss-dev/moss-core",
  // Node built-ins are provided by Obsidian's Electron runtime.
  "fs",
  "fs/promises",
  "path",
  "child_process",
  "crypto",
];

/** @type {import('esbuild').BuildOptions} */
const shared = {
  bundle: true,
  format: "cjs",
  platform: "node",
  target: "node20",
  sourcemap: watch ? "inline" : false,
  minify: false,
  logLevel: "info",
  external,
};

const builds = [
  { ...shared, entryPoints: ["src/main.ts"], outfile: "main.js" },
  { ...shared, entryPoints: ["src/worker/mossWorker.ts"], outfile: "mossWorker.js" },
];

if (watch) {
  const contexts = await Promise.all(builds.map((b) => esbuild.context(b)));
  await Promise.all(contexts.map((c) => c.watch()));
  console.log("watching…");
} else {
  await Promise.all(builds.map((b) => esbuild.build(b)));
}
