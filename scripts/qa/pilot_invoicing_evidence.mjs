import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { chromium } from "../../web/node_modules/@playwright/test/index.mjs";
import { FREEZE_CSS, installBreakpointFixture } from "../../web/e2e/support/breakpoint-fixture.ts";
import { reportRequestSchema } from "../../web/lib/business-reports-api.ts";
import { fixtureId } from "../../web/__tests__/fixtures/business-report-http-fixture.ts";

const repository = resolve(import.meta.dirname, "../..");
const git = (...args) => execFileSync("git", args, { cwd: repository, encoding: "utf8" }).trim();
const head = git("rev-parse", "HEAD");
assert.match(process.env.EVIDENCE_EXPECTED_HEAD ?? "", /^[a-f0-9]{40}$/);
assert.equal(head, process.env.EVIDENCE_EXPECTED_HEAD);
assert.match(process.env.EVIDENCE_FROZEN_SOURCE_HEAD ?? "", /^[a-f0-9]{40}$/);
git("diff", "--exit-code", process.env.EVIDENCE_FROZEN_SOURCE_HEAD, head, "--", "web", ".agent/designs/cuadrao-business-app/DESIGN.md", "docs/handoffs/invoicing-design-checkpoint-20261026.md", "docs/reports/invoicing-preview-20261026.md");
assert.equal(process.env.NEXT_PUBLIC_MOCK_AUTH, "true");
assert.ok(process.env.EVIDENCE_OUTPUT, "EVIDENCE_OUTPUT is required");
const output = resolve(process.env.EVIDENCE_OUTPUT);
const web = process.env.EVIDENCE_WEB_BASE_URL ?? "http://127.0.0.1:4405";
const fixture = process.env.EVIDENCE_FIXTURE_BASE_URL ?? "http://127.0.0.1:4406";
for (const target of [web, fixture]) {
  const url = new URL(target);
  assert.equal(url.protocol, "http:");
  assert.equal(url.hostname, "127.0.0.1");
  assert.equal(url.origin, target);
}
assert.equal(process.env.NEXT_PUBLIC_CUADRAO_API_URL, `${fixture}/api/v1`);
const results = [];
const errors = [];
const blockedExternalRequests = [];
const captures = [];
const diagnosticFailures = [];
const safeText = value => String(value).replace(/https?:\/\/[^\s"'<>]+/g, "[URL omitted]").slice(0, 5_000);
const safeUrl = value => {
  try {
    const url = new URL(value);
    return { origin: url.origin, pathname: [web, fixture].includes(url.origin) ? url.pathname : "[external path omitted]" };
  } catch { return { origin: "[invalid URL]", pathname: "[omitted]" }; }
};
async function recordFailure(page, error, stage, sample, requests) {
  const failure = { ...sample, stage, error: { name: error?.name ?? "Error", message: safeText(error?.message ?? error) }, url: safeUrl(page.url()), requests };
  try { failure.publicUi = safeText(await page.locator("body").innerText({ timeout: 2_000 })); }
  catch (diagnosticError) { diagnosticFailures.push({ step: "public UI", message: safeText(diagnosticError) }); }
  try { await page.screenshot({ path: join(output, `failure-${sample.width}-${sample.language}-${sample.theme}.png`), fullPage: true, animations: "disabled", timeout: 3_000 }); }
  catch (diagnosticError) { diagnosticFailures.push({ step: "failure screenshot", message: safeText(diagnosticError) }); }
  try { writeFileSync(join(output, "failure.json"), `${JSON.stringify(failure, null, 2)}\n`); }
  catch (diagnosticError) { diagnosticFailures.push({ step: "failure report", message: safeText(diagnosticError) }); }
}
const identity = { frontend: head, frozenSource: process.env.EVIDENCE_FROZEN_SOURCE_HEAD, backend: "synthetic HTTP contract fixture", hostedAcceptance: false };
mkdirSync(output, { recursive: true });
writeFileSync(join(output, "source-sha.txt"), `${head}\n`);
const browser = await chromium.launch({ headless: true });
let completed = false;
let originalFailure;
try {
  for (const width of [1440, 834, 390]) {
    for (const language of ["es-419", "en"]) {
      const words = JSON.parse(readFileSync(join(repository, "web/public/locales", language, "common.json"), "utf8"));
      const invoice = words.business.invoicing_preview;
      for (const theme of ["light", "dark"]) {
        const context = await browser.newContext({
          viewport: { width, height: 1000 }, hasTouch: width < 1024,
          locale: language === "en" ? "en-US" : "es-DO", colorScheme: theme,
          reducedMotion: "reduce", serviceWorkers: "block",
        });
        const page = await context.newPage();
        const requests = [];
        let stage = "fixture setup";
        try {
          await context.route("**/*", route => {
            const url = new URL(route.request().url());
            if ([web, fixture].includes(url.origin) || ["data:", "blob:"].includes(url.protocol)) return route.fallback();
            blockedExternalRequests.push(url.origin);
            return route.abort();
          });
          page.setDefaultTimeout(15_000);
          page.on("pageerror", error => errors.push(safeText(error)));
          page.on("requestfailed", request => requests.push({ kind: "requestfailed", ...safeUrl(request.url()), method: request.method(), error: safeText(request.failure()?.errorText ?? "unknown") }));
          page.on("response", response => { if (response.status() >= 400) requests.push({ kind: "http failure", ...safeUrl(response.url()), status: response.status() }); });
          await installBreakpointFixture(page, { language, theme, emptyChat: true, consent: "accepted" });
          await page.addInitScript(({ language, theme }) => {
            localStorage.setItem("cuadrao-business-preview-language", language);
            localStorage.setItem("argus-theme", theme);
          }, { language, theme });
          await page.route(`${fixture}/api/v1/business/**`, route => route.continue());
          const capture = async name => {
            const filename = `${name}-${width}-${language}-${theme}.png`;
            const path = join(output, filename);
            await page.screenshot({ path, fullPage: true, animations: "disabled" });
            captures.push({ filename, sha256: createHash("sha256").update(readFileSync(path)).digest("hex") });
          };
          stage = "invoicing navigation";
          await page.goto(`${web}/biz?invoicePreview=seeded&view=invoicing`, { waitUntil: "domcontentloaded", timeout: 60_000 });
          stage = "invoicing client assets";
          await page.waitForLoadState("load", { timeout: 60_000 });
          stage = "invoicing readiness";
          await page.getByTestId("invoicing-preview").waitFor();
          await page.addStyleTag({ content: FREEZE_CSS });
          await page.getByRole("button", { name: invoice.create, exact: true }).waitFor();
          const dimensions = await page.evaluate(() => ({ width: innerWidth, scroll: document.documentElement.scrollWidth, dark: document.documentElement.classList.contains("dark"), language: document.documentElement.lang }));
          assert.ok(dimensions.scroll <= width);
          assert.equal(dimensions.dark, theme === "dark");
          assert.equal(dimensions.language, language === "en" ? "en" : "es");
          await capture("invoicing");
          stage = "editor";
          await page.getByRole("button", { name: invoice.create, exact: true }).click();
          await page.getByTestId("invoice-editor").waitFor();
          await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
          const collapse = page.getByRole("button", { name: invoice.collapse_editor, exact: true });
          if (width >= 1024) {
            assert.equal(await collapse.count(), 1);
            await collapse.click();
            await page.getByRole("button", { name: invoice.expand_editor, exact: true }).click();
          } else assert.equal(await collapse.count(), 0);
          await capture("invoice-editor");
          const report = reportRequestSchema.parse({ schema_version: 2, filters: { period: { kind: "all" } }, sort: "date_asc" });
          const url = new URL(`${web}/biz?view=transactions`);
          url.searchParams.set("report", JSON.stringify(report));
          url.searchParams.set("report_scope", `breakpoint-user:${fixtureId(3000)}`);
          stage = "connected records";
          await page.goto(url.href, { waitUntil: "domcontentloaded" });
          await page.locator('[data-report-schema="2"] [data-testid="records-count"]').waitFor();
          await page.addStyleTag({ content: FREEZE_CSS });
          assert.ok((await page.getByTestId("transacciones-records").innerText()).includes("9,007,199,254,740,993.01"));
          const recordsWidth = await page.evaluate(() => document.documentElement.scrollWidth);
          assert.ok(recordsWidth <= width);
          await capture("connected-records");
          results.push({ ...identity, width, language, theme, dimensions, recordsWidth, editorExpansion: width >= 1024, invoicing: "local preview only" });
        } catch (error) {
          await recordFailure(page, error, stage, { width, language, theme }, requests).catch(diagnosticError => diagnosticFailures.push({ step: "failure diagnostics", message: safeText(diagnosticError) }));
          throw error;
        } finally {
          await context.close().catch(error => diagnosticFailures.push({ step: "context close", message: safeText(error) }));
        }
      }
    }
  }
  assert.equal(results.length, 12);
  assert.equal(captures.length, 36);
  assert.deepEqual(errors, []);
  assert.deepEqual(blockedExternalRequests, []);
  completed = true;
} catch (error) {
  originalFailure = error;
  throw error;
} finally {
  await browser.close().catch(error => diagnosticFailures.push({ step: "browser close", message: safeText(error) }));
  try { writeFileSync(join(output, "browser-proof.json"), `${JSON.stringify({ ...identity, completed, results, captures, errors, blockedExternalRequests, diagnosticFailures }, null, 2)}\n`); }
  catch (error) { if (!originalFailure) throw error; }
}
