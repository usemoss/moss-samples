import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  serverExternalPackages: ["@moss-dev/moss", "better-sqlite3"],
  eslint: {
    ignoreDuringBuilds: true,
  },
  experimental: {
    optimizePackageImports: ["lucide-react"],
  },
};

export default nextConfig;
