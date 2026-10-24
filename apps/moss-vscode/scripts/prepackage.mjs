import { execSync } from "node:child_process";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const extensionRoot = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
const lockPath = path.join(extensionRoot, "package-lock.json");
const lock = JSON.parse(readFileSync(lockPath, "utf8"));
// Require the locked moss-core version — do not fall back to @moss-dev/moss,
// since the JS wrapper and native core versions are not guaranteed to match.
const mossCoreVersion = lock.packages?.["node_modules/@moss-dev/moss-core"]?.version;

if (!mossCoreVersion) {
  throw new Error(
    "Could not resolve @moss-dev/moss-core version from package-lock.json. " +
      "Run npm install in apps/moss-vscode before packaging.",
  );
}

const platformPackages = [
  "@moss-dev/moss-core-darwin-arm64",
  "@moss-dev/moss-core-darwin-x64",
  "@moss-dev/moss-core-linux-arm64-gnu",
  "@moss-dev/moss-core-linux-x64-gnu",
  "@moss-dev/moss-core-win32-x64-msvc",
];

const specs = platformPackages.map((pkg) => `${pkg}@${mossCoreVersion}`).join(" ");

console.log(`Installing Moss native binaries for all platforms (${mossCoreVersion})…`);
execSync(`npm install --no-save --force ${specs}`, {
  cwd: extensionRoot,
  stdio: "inherit",
});
