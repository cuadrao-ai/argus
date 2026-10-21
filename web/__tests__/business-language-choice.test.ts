import { describe, expect, test } from "bun:test";
import { join } from "node:path";

const webRoot = join(import.meta.dir, "..");

/** Boots the real i18n wiring in a browser-like page and reports what the client and the server layout each resolve. */
const probe = `
import { GlobalRegistrator } from "@happy-dom/global-registrator";
const { documentLanguage, resolveLanguage } = await import("./lib/language-features.ts");
const { businessPilotEnabled } = await import("./lib/private-alpha-flags.ts");
const serverLang = documentLanguage(resolveLanguage({}), businessPilotEnabled);
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
const language = i18n.resolvedLanguage ?? i18n.language;
const clientLang = documentLanguage(resolveLanguage({ device: language }), businessPilotEnabled);
console.log(JSON.stringify({ language, serverLang, clientLang }));
process.exit(0);
`;

type Shown = { language: string; serverLang: string; clientLang: string };

function shown(build: "business" | "consumer", navigator: string, stored: string): Shown {
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
  return JSON.parse(lines[lines.length - 1]);
}

describe("the language i18n starts in, through the real wiring", () => {
  test("Business: an English browser with nothing stored starts in Spanish, and the server layout agrees", () => {
    const result = shown("business", "en-US", "");
    expect(result.language).toBe("es-419");
    expect(result.serverLang).toBe("es");
    expect(result.clientLang).toBe(result.serverLang);
  });

  test("Business: the device choice wins before sign-in, whatever the browser says", () => {
    expect(shown("business", "en-US", "en").language).toBe("en");
    expect(shown("business", "es-MX", "en").language).toBe("en");
    expect(shown("business", "en-US", "es-419").language).toBe("es-419");
  });

  test("consumer: the browser language still decides when nothing is stored, and the server layout agrees for an English browser", () => {
    const english = shown("consumer", "en-US", "");
    expect(english.language).toBe("en");
    expect(english.clientLang).toBe(english.serverLang);
    expect(shown("consumer", "es-MX", "").language).toBe("es-419");
  });
});
