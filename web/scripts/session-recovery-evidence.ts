import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, rmdirSync, unlinkSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { chromium, expect } from "@playwright/test";

const fixture = resolve("app/session-recovery-evidence");
const fixtureFile = resolve(fixture, "page.tsx");
const marker = "// Temporary session recovery evidence fixture.";
const command = process.argv[2];

if (command === "prepare") {
  assert.ok(!existsSync(fixture), "Do not replace an existing route");
  mkdirSync(fixture);
  writeFileSync(fixtureFile, `${marker}
import Preview from "@/app/dev/error-screen/ErrorScreenPreview";
export const dynamic = "force-dynamic";
export default async function Page({ searchParams }: {
  searchParams: Promise<{ screen?: string; language?: string; theme?: string }>;
}) {
  const params = await searchParams;
  return <Preview screen={params.screen ?? "session-missing"} language={params.language} theme={params.theme} />;
}
`, { flag: "wx" });
} else if (command === "cleanup") {
  if (existsSync(fixtureFile)) {
    assert.ok(readFileSync(fixtureFile, "utf8").startsWith(marker));
    unlinkSync(fixtureFile);
    rmdirSync(fixture);
  }
} else if (command === "capture") {
  const baseURL = process.env.EVIDENCE_BASE_URL ?? "http://127.0.0.1:3199";
  assert.ok(["127.0.0.1", "localhost"].includes(new URL(baseURL).hostname));
  execFileSync("git", ["diff", "--quiet", "HEAD"]);
  const head = execFileSync("git", ["rev-parse", "HEAD"], { encoding: "utf8" }).trim();
  const output = resolve(process.env.EVIDENCE_OUTPUT ?? "../temp/auth-design-evidence/session-recovery");
  mkdirSync(output, { recursive: true });
  const captures: object[] = [];
  const browser = await chromium.launch({ headless: true });
  try {
    for (const language of ["es-419", "en"] as const) {
      for (const theme of ["light", "dark"] as const) {
        for (const width of [390, 1440]) {
          const page = await browser.newPage({ viewport: { width, height: width === 390 ? 844 : 1024 }, reducedMotion: "reduce" });
          const errors: string[] = [];
          const blocked: string[] = [];
          page.on("pageerror", error => errors.push(error.message));
          await page.route("**/*", route => {
            const url = new URL(route.request().url());
            if (!["127.0.0.1", "localhost"].includes(url.hostname)) {
              blocked.push(url.pathname);
              return route.abort();
            }
            if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/auth/v1/")) {
              return route.fulfill({ status: 401, json: { code: "synthetic_session_missing" } });
            }
            return route.continue();
          });
          for (const state of ["missing", "error", "changed", "busy"]) {
            await page.goto(`${baseURL}/session-recovery-evidence?screen=session-${state}&language=${language}&theme=${theme}`);
            await page.evaluate(() => document.fonts.ready);
            await page.addStyleTag({ content: "nextjs-portal { display: none; }" });
            const heading = page.getByRole("heading", { level: 1 });
            await expect(heading).toBeVisible();
            if (state !== "busy") await expect(heading).toBeFocused();
            assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
            assert.equal(await page.locator("main").count(), 1);
            assert.equal(await page.locator("aside").count(), 0);
            if (state === "missing") {
              await expect(heading).toHaveText(language === "en" ? "Sign in to continue" : "Inicia sesión para continuar");
              const link = page.getByRole("link");
              await expect(link).toHaveAttribute("href", "/?auth=login");
              await expect(page.locator('img[src="/brand/session-door.png"]')).toBeVisible();
              assert.ok((await link.boundingBox())!.height >= 44);
            }
            const file = `${language}-${theme}-${width}-${state}.png`;
            const bytes = await page.screenshot({ path: resolve(output, file), fullPage: true, animations: "disabled" });
            captures.push({ file, head, language, theme, width, state, sha256: createHash("sha256").update(bytes).digest("hex"), synthetic: true });
            if (state === "error") {
              const button = page.getByRole("button", { name: language === "en" ? "Retry" : "Reintentar", exact: true });
              await button.click();
              await expect(page.getByTestId("session-recovery-screen").getByRole("button")).toBeDisabled();
              await expect(button).toBeEnabled();
              await expect(heading).not.toBeFocused();
            }
            assert.equal(await page.title(), "Cuadrao");
            assert.deepEqual(errors, []);
            assert.deepEqual(blocked, []);
          }
          await page.close();
        }
      }
    }
  } finally {
    await browser.close();
    writeFileSync(resolve(output, "manifest.json"), JSON.stringify({ head, synthetic: true, captures }, null, 2));
  }
  console.log(`Session recovery: ${captures.length} synthetic captures at ${head}`);
} else {
  throw new Error("Use prepare, capture, or cleanup");
}
