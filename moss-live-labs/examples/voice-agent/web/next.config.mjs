import { dirname } from "node:path";
import { fileURLToPath } from "node:url";

// Node 18 doesn't provide import.meta.dirname; derive it from import.meta.url.
const rootDir = dirname(fileURLToPath(import.meta.url));

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // This app lives in a monorepo with other lockfiles; pin the tracing root here.
  outputFileTracingRoot: rootDir,
};

export default nextConfig;
