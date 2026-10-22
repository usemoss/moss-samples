import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  serverExternalPackages: ["@moss-dev/moss", "@moss-dev/moss-core"],
};

export default nextConfig;
