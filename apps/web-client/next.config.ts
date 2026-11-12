import type { NextConfig } from "next";

const tailnetHost = process.env.VED_TAILNET_HOST;
const backendInternalUrl = process.env.VED_BACKEND_INTERNAL_URL ?? "http://backend:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  compress: false,
  allowedDevOrigins: tailnetHost ? [tailnetHost] : [],
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${backendInternalUrl}/:path*`,
      },
    ];
  },
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
        ],
      },
      {
        source: "/sw.js",
        headers: [
          { key: "Content-Type", value: "application/javascript; charset=utf-8" },
          { key: "Cache-Control", value: "no-cache, no-store, must-revalidate" },
        ],
      },
    ];
  },
};

export default nextConfig;
