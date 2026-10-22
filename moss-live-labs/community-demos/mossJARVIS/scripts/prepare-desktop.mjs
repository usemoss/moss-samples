import { access, chmod, copyFile, cp, mkdir, readdir, rm } from "node:fs/promises";
import path from "node:path";

const destinationDirectory = path.join(process.cwd(), "src-tauri", "resources");
const destination = path.join(destinationDirectory, "node");

await mkdir(destinationDirectory, { recursive: true });
await copyFile(process.execPath, destination);
await chmod(destination, 0o755);

const standaloneDirectory = path.join(process.cwd(), ".next", "standalone");
const packagedServerDirectory = path.join(process.cwd(), ".desktop-server");
await rm(packagedServerDirectory, { recursive: true, force: true });
await cp(standaloneDirectory, packagedServerDirectory, { recursive: true, dereference: true });

const packagedNodeModules = path.join(packagedServerDirectory, "node_modules");
const packagedPnpmStore = path.join(packagedNodeModules, ".pnpm");
const mossDestination = path.join(packagedNodeModules, "@moss-dev");
await mkdir(mossDestination, { recursive: true });
for (const storeEntry of await readdir(packagedPnpmStore)) {
  const mossPackages = path.join(packagedPnpmStore, storeEntry, "node_modules", "@moss-dev");
  try {
    for (const packageName of await readdir(mossPackages)) {
      const destinationPackage = path.join(mossDestination, packageName);
      try {
        await access(destinationPackage);
      } catch {
        await cp(path.join(mossPackages, packageName), destinationPackage, { recursive: true, dereference: true });
      }
    }
  } catch {
    // Most pnpm store entries are unrelated to Moss.
  }
}
console.log(`Prepared Node sidecar from ${process.execPath}`);
console.log(`Materialized standalone server at ${packagedServerDirectory}`);
