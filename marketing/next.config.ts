import type { NextConfig } from "next";
import { nextRedirects, nextRewrites } from "./lib/site-routes";

const nextConfig: NextConfig = {
  poweredByHeader: false,
  experimental: { globalNotFound: true },
  async redirects() {
    return nextRedirects();
  },
  async rewrites() {
    return nextRewrites();
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Content-Security-Policy", value: "img-src 'self' data:;" },
        ],
      },
    ];
  },
};

export default nextConfig;
