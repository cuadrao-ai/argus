import { describe, expect, test } from "bun:test";
import { join } from "node:path";

const webRoot = join(import.meta.dir, "..");

const probe = `
import { GlobalRegistrator } from "@happy-dom/global-registrator";
GlobalRegistrator.register({ url: "http://localhost/biz" });
const navigatorLanguage = process.env.PROBE_NAVIGATOR;
Object.defineProperty(window.navigator, "language", { configurable: true, value: navigatorLanguage });
Object.defineProperty(window.navigator, "languages", { configurable: true, value: [navigatorLanguage] });
if (process.env.PROBE_STORED) window.localStorage.setItem("i18nextLng", process.env.PROBE_STORED);
const localeFetch = async () => new Response("{}", { headers: { "content-type": "application/json" } });
globalThis.fetch = localeFetch;
window.fetch = localeFetch;
const i18n = (await import("./lib/i18n.ts")).default;
if (!i18n.isInitialized) {
  await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("i18n did not initialize in 10s")), 10000);
    i18n.on("initialized", () => {
      clearTimeout(timer);
      resolve(undefined);
    });
  });
}
console.log(JSON.stringify({ language: i18n.resolvedLanguage ?? i18n.language }));
process.exit(0);
`;

function shownLanguage(build: "business" | "consumer", navigator: string, stored: string): string {
  const result = Bun.spawnSync({
    cmd: ["bun", "-e", probe],
    cwd: webRoot,
    env: {
      ...process.env,
      NEXT_PUBLIC_ENABLE_SPANISH: "true",
      NEXT_PUBLIC_BUSINESS_PILOT_ENABLED: build === "business" ? "true" : "false",
      PROBE_NAVIGATOR: navigator,
      PROBE_STORED: stored,
    },
    stderr: "pipe",
    stdout: "pipe",
  });
  expect(result.exitCode, result.stderr.toString()).toBe(0);
  const lines = result.stdout.toString().trim().split("\n");
  return JSON.parse(lines[lines.length - 1]).language;
}

describe("the language i18n starts in, through the real wiring", () => {
  test("Business: an English browser with nothing stored starts in Spanish", () => {
    expect(shownLanguage("business", "en-US", "")).toBe("es-419");
  });

  test("Business: the device choice wins before sign-in, whatever the browser says", () => {
    expect(shownLanguage("business", "en-US", "en")).toBe("en");
    expect(shownLanguage("business", "es-MX", "en")).toBe("en");
  });

  test("Business: a stored Spanish choice stays Spanish in an English browser", () => {
    expect(shownLanguage("business", "en-US", "es-419")).toBe("es-419");
  });

  test("consumer: the browser language still decides when nothing is stored", () => {
    expect(shownLanguage("consumer", "en-US", "")).toBe("en");
    expect(shownLanguage("consumer", "es-MX", "")).toBe("es-419");
  });
});
