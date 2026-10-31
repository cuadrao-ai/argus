import type { NextConfig } from "next";
import { CHAT_RUNTIME_EVENT_TIMEOUT_MS } from "./lib/chat-runtime-timeout";

// Device QA runs the dev server over a LAN address, which the cross-origin dev
// guard blocks by default: the JS chunks never load and the phone shows a blank
// page with nothing in the console to explain it. Named hosts only, set locally
// for the session; nothing here reaches a deployed build.
const devOrigins = (process.env.NEXT_DEV_ALLOWED_ORIGINS ?? "")
  .split(",")
  .map((origin) => origin.trim())
  .filter(Boolean);

const nextConfig: NextConfig = {
  env: { CUADRAO_RUNTIME_EVENT_TIMEOUT_SECONDS: String(CHAT_RUNTIME_EVENT_TIMEOUT_MS / 1_000) },
  async headers() {
    return [{
      source: "/:path*",
      headers: [{ key: "Content-Security-Policy", value: "img-src 'self' data:;" }],
    }, {
      source: "/auth/native-captcha",
      headers: [
        { key: "Cache-Control", value: "no-store" },
        { key: "Referrer-Policy", value: "no-referrer" },
        { key: "X-Frame-Options", value: "DENY" },
      ],
    }];
  },
  distDir: process.env.NEXT_DIST_DIR ?? ".next",
  allowedDevOrigins: ["127.0.0.1", "localhost", ...devOrigins],
};

export default nextConfig;
