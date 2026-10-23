/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // livekit-server-sdk relies on Node.js built-ins; keep it external to the bundle.
  serverExternalPackages: ["livekit-server-sdk"],
};

export default nextConfig;
