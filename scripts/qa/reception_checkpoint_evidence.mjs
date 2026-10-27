import assert from "node:assert/strict";
import { execFileSync, spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { createServer } from "node:http";
import { createWriteStream, existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { once } from "node:events";
import { join, resolve } from "node:path";
import { chromium } from "../../web/node_modules/@playwright/test/index.mjs";
import { FREEZE_CSS, installBreakpointFixture } from "../../web/e2e/support/breakpoint-fixture.ts";
import { createFixtureBusinessDataSource } from "../../web/components/business-app/fixture-data.ts";
import { createBusinessReportHttpFixture, fixtureId } from "../../web/__tests__/fixtures/business-report-http-fixture.ts";

const repository = resolve(import.meta.dirname, "../..");
const git = (...args) => execFileSync("git", args, { cwd: repository, encoding: "utf8" }).trim();
const head = git("rev-parse", "HEAD");
const tree = git("rev-parse", "HEAD^{tree}");
assert.match(process.env.EVIDENCE_EXPECTED_HEAD ?? "", /^[a-f0-9]{40}$/);
assert.equal(head, process.env.EVIDENCE_EXPECTED_HEAD);
const sourcePaths = ["web", "scripts/qa/reception_checkpoint_evidence.mjs"];
git("diff", "--exit-code", head, "--", ...sourcePaths);
assert.equal(git("ls-files", "--others", "--exclude-standard", "--", ...sourcePaths), "");
assert.ok(process.env.EVIDENCE_OUTPUT);
const output = resolve(process.env.EVIDENCE_OUTPUT);
const origin = (value) => { const url = new URL(value); assert.equal(url.protocol, "http:"); assert.equal(url.hostname, "127.0.0.1"); assert.equal(url.origin, value); return url; };
const web = origin(process.env.EVIDENCE_WEB_BASE_URL ?? "http://127.0.0.1:4421");
const fixture = origin(process.env.EVIDENCE_FIXTURE_BASE_URL ?? "http://127.0.0.1:4422");
assert.notEqual(web.port, fixture.port);
assert.equal(execFileSync(process.execPath, ["--version"], { encoding: "utf8" }).trim(), "1.3.14");
mkdirSync(output, { recursive: true });
writeFileSync(join(output, "source-sha.txt"), `${head}\n`);
const results = [], captures = [], errors = [], external = [], diagnostics = [];
const safe = value => String(value).replace(/https?:\/\/[^\s"'<>]+/g, "[URL omitted]").slice(0, 5000);
const pathname = value => { try { return new URL(value).pathname; } catch { return "[invalid URL]"; } };
const environment = {
  PATH: process.env.PATH, HOME: process.env.HOME, TMPDIR: process.env.TMPDIR,
  NEXT_PUBLIC_MOCK_AUTH: "true", NEXT_PUBLIC_APP_ENV: "local", NEXT_PUBLIC_ENABLE_SPANISH: "true",
  NEXT_PUBLIC_BUSINESS_PILOT_ENABLED: "true", NEXT_PUBLIC_CUADRAO_BUSINESS_INVOICING_ENABLED: "true",
  NEXT_PUBLIC_CUADRAO_API_URL: `${fixture.origin}/api/v1`, NEXT_TELEMETRY_DISABLED: "1",
};
const probe = createServer();
await new Promise((resolve, reject) => { probe.once("error", reject); probe.listen(Number(web.port), "127.0.0.1", resolve); });
await new Promise(resolve => probe.close(resolve));
const log = createWriteStream(join(output, "web.log"));
const app = spawn(process.execPath, ["node_modules/next/dist/bin/next", "dev", "--hostname", "127.0.0.1", "--port", web.port, "--webpack"], { cwd: join(repository, "web"), env: environment, detached: true, stdio: ["ignore", "pipe", "pipe"] });
app.stdout.pipe(log); app.stderr.pipe(log);
let exited = false;
app.once("exit", () => { exited = true; });
let browser, complete = false, originalFailure;
try {
  let ready = false;
  for (let attempt = 0; attempt < 60; attempt++) {
    assert.equal(exited, false, "owned runtime exited before readiness");
    try { const response = await fetch(`${web.origin}/biz`, { signal: AbortSignal.timeout(60000) }); if (response.ok) { ready = true; break; } } catch {}
    await new Promise(resolve => setTimeout(resolve, 500));
  }
  assert.ok(ready, "owned runtime did not become ready");
  browser = await chromium.launch({ headless: true });
  for (const width of [1440, 834, 390]) for (const language of ["es-419", "en"]) for (const theme of ["light", "dark"]) {
    const words = JSON.parse(readFileSync(join(repository, "web/public/locales", language, "common.json"), "utf8"));
    const copy = words.business.reception_preview;
    const context = await browser.newContext({ viewport: { width, height: 1000 }, hasTouch: width < 1024, locale: language === "en" ? "en-US" : "es-DO", colorScheme: theme, reducedMotion: "reduce", serviceWorkers: "block" });
    const page = await context.newPage(), requests = [], writes = [];
    const source = createFixtureBusinessDataSource({ chatAvailable: false });
    const reports = createBusinessReportHttpFixture();
    let release, sourceDenied = true, emailDenied = true, stage = "fixture setup";
    const held = new Promise(resolve => { release = resolve; });
    const capture = async name => { const filename = `${name}-${width}-${language}-${theme}.png`, path = join(output, filename); await page.screenshot({ path, fullPage: true, animations: "disabled" }); captures.push({ filename, sha256: createHash("sha256").update(readFileSync(path)).digest("hex") }); };
    try {
      page.setDefaultTimeout(15000);
      page.on("pageerror", error => errors.push(safe(error)));
      page.on("requestfailed", request => requests.push({ kind: "requestfailed", pathname: pathname(request.url()), error: safe(request.failure()?.errorText) }));
      page.on("response", response => { if (response.status() >= 400) requests.push({ kind: "http", pathname: pathname(response.url()), status: response.status() }); });
      await context.route("**/*", route => {
        const url = new URL(route.request().url());
        if ([web.origin, fixture.origin].includes(url.origin) || ["data:", "blob:"].includes(url.protocol)) return route.fallback();
        external.push(url.origin); return route.abort();
      });
      await installBreakpointFixture(page, { language, theme, emptyChat: true, consent: "accepted" });
      await page.addInitScript(({ language, theme }) => { localStorage.setItem("cuadrao-business-preview-language", language); localStorage.setItem("argus-theme", theme); }, { language, theme });
      await page.route(`${fixture.origin}/api/v1/business/**`, async route => {
        const request = route.request(), url = new URL(request.url()), path = url.pathname, method = request.method();
        const json = (value, status = 200) => route.fulfill({ json: value, status });
        if (method === "OPTIONS") return json(null);
        if (method !== "GET") writes.push({ path, method });
        if (path.endsWith("/spaces")) return json({ spaces: [{ space_id: fixtureId(3000), grant_id: fixtureId(3001), name: "Negocio sintético", role: "owner", business_role: "owner", capabilities: ["read", "prepare", "approve"], permissions: ["read", "prepare", "approve", "manage", "download", "export", "assign_owner"], access_seen: true }], closed_spaces: [] });
        if (path.endsWith("/space")) return json({ id: fixtureId(3000), name: "Negocio sintético" });
        if (path.endsWith("/space/name-prompt")) return json({ id: fixtureId(3000), name: "Negocio sintético", name_required: false, name_prompt_seen: true, show_prompt: false });
        if (path.endsWith("/workspace")) return json(await source.workspace());
        if (path.endsWith("/receipt-activity")) return json((await source.receiptPage("all")).activity);
        if (path.endsWith("/receipt-reading")) return json({ scope_version: 1, enabled: true, available: false, can_change: false, disclosure: "", disclosure_token: null, route: null, consented_at: null, revoked_at: null });
        if (path.endsWith("/receipts")) {
          if (url.searchParams.get("view") === "all") await held;
          const value = await source.receiptPage(url.searchParams.get("view") === "all" ? "all" : "inbox");
          value.items = value.items.map(item => item.id === "rcpt-ferreteria" ? { ...item, source_text: "Materiales del negocio.\nConservar este mensaje completo." } : item);
          return json(value);
        }
        if (path.endsWith("/overview")) return json(await source.overview("2026-10-01", "2026-10-31"));
        if (path.endsWith("/captures")) return json(await source.captures("", 50, "inbox"));
        if (path.endsWith("/email")) return json(await source.emailIntake());
        if (path.endsWith("/email/deliveries")) return json({ items: await source.emailDeliveries() });
        const email = path.match(/\/email\/deliveries\/([^/]+)$/);
        if (email) return emailDenied ? json({ detail: "synthetic original unavailable" }, 503) : json({ ...(await source.emailDelivery(email[1])), text_body: "Texto original sintético.\nSegunda línea sin recortar." });
        const original = path.match(/\/receipts\/([^/]+)\/source$/);
        if (original) return sourceDenied ? json({ detail: "synthetic forbidden" }, 403) : route.fulfill({ body: Buffer.from(await (await source.receiptSource(original[1])).arrayBuffer()), contentType: "image/svg+xml" });
        const receipt = path.match(/\/receipts\/([^/]+)$/);
        if (receipt) return json(await source.receipt(receipt[1]));
        if (path.endsWith("/read")) return route.fulfill({ status: 204 });
        const dossier = path.match(/\/drafts\/([^/]+)\/dossier$/);
        if (dossier) return json(await source.dossier(dossier[1]));
        if (path.endsWith("/reports/query") || path.includes("/report-views")) {
          const response = await reports.request(request.url(), { method, headers: request.headers(), body: request.postData() ?? undefined });
          return route.fulfill({ status: response.status, body: await response.text(), contentType: "application/json" });
        }
        if (path.endsWith("/invoices")) { assert.equal(method, "GET"); assert.equal(request.headers()["x-business-grant"], fixtureId(3001)); return json({ items: [], total: 0, page: 1, page_size: 25, stage_counts: { draft: 0, issued: 0, processing: 0, rejected: 0, uncertain: 0 }, summaries: [], query_version: "synthetic-query" }); }
        if (path.endsWith("/customers")) { assert.equal(method, "GET"); return json({ items: [], total: 0, page: 1, page_size: 25 }); }
        if (path.endsWith("/consent")) return route.fallback();
        throw new Error(`Unhandled synthetic Business request ${method} ${path}`);
      });
      stage = "owned runtime loading";
      await page.goto(`${web.origin}/biz?view=inbox`, { waitUntil: "domcontentloaded", timeout: 60000 });
      await page.waitForLoadState("load", { timeout: 60000 });
      const skeleton = page.getByTestId("reception-skeleton");
      await skeleton.waitFor();
      assert.equal(await skeleton.locator("li").count(), 5);
      assert.equal(await skeleton.getByRole("button").count(), 0);
      assert.equal(await page.getByRole("checkbox", { name: copy.select_page, exact: true }).isDisabled(), true);
      const shape = await skeleton.locator("li").first().evaluate(element => ({ grid: getComputedStyle(element).gridTemplateColumns, height: element.getBoundingClientRect().height, animation: getComputedStyle(element.querySelector('[class*="skeletonBar"]')).animationName }));
      assert.equal(shape.animation, "none");
      await capture("loading"); release();
      const rows = page.getByTestId("reception-row"); await rows.first().waitFor();
      await skeleton.waitFor({ state: "detached" });
      await page.addStyleTag({ content: FREEZE_CSS });
      stage = "list geometry";
      assert.equal(await rows.getByTestId("reception-amount").count(), 0);
      assert.equal(await rows.getByTestId("reception-currency").count(), 0);
      const receiptRow = rows.filter({ hasText: "Ferretería La Esquina" });
      const actual = await receiptRow.evaluate(element => ({ grid: getComputedStyle(element).gridTemplateColumns, height: element.getBoundingClientRect().height }));
      if (width >= 1024) { assert.equal(shape.grid, actual.grid); assert.equal(shape.height, actual.height); }
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
      await capture("list");
      stage = "receipt original denial and retry";
      await receiptRow.getByRole("button").first().click();
      const detail = page.getByTestId("reception-dossier");
      await detail.getByTestId("receipt-original-source").getByRole("alert").waitFor();
      assert.equal(await detail.getByTestId("reception-original-text").innerText(), "Materiales del negocio.\nConservar este mensaje completo.");
      sourceDenied = false;
      await detail.getByRole("button", { name: words.business.dossier.retry_source, exact: true }).click();
      await detail.getByTestId("receipt-original-source").locator("a[download]").waitFor();
      assert.equal(await detail.getByTestId("receipt-original-source").locator("button[aria-expanded]").getAttribute("aria-expanded"), "true");
      assert.equal(await detail.getByTestId("receipt-source-channel").count(), 0);
      await capture("receipt-dossier");
      await page.keyboard.press("Escape"); await detail.waitFor({ state: "hidden" });
      await page.waitForFunction(() => { const row = [...document.querySelectorAll('[data-testid="reception-row"]')].find(element => element.textContent.includes("Ferretería La Esquina")); return row?.querySelector("button") === document.activeElement; });
      stage = "full synthetic note";
      await page.locator('[data-testid="reception-row"][data-kind="message"]').getByRole("button", { name: copy.action_note, exact: true }).click();
      await detail.waitFor();
      assert.equal(await detail.getByTestId("reception-original-text").innerText(), copy.note_example);
      assert.equal(await detail.getByTestId("reception-detail-sender").innerText(), "+1 809 555 0147");
      assert.equal(await detail.getByTestId("receipt-original-source").count(), 0);
      await capture("note-dossier"); await page.keyboard.press("Escape"); await detail.waitFor({ state: "hidden" });
      stage = "synthetic email original failure and retry";
      await rows.filter({ hasText: "Boletín semanal" }).getByRole("button").first().click();
      await detail.getByTestId("email-detail").getByRole("alert").waitFor();
      emailDenied = false; await detail.getByRole("button", { name: words.common.retry, exact: true }).click();
      await detail.getByText("Texto original sintético.", { exact: false }).waitFor();
      assert.ok((await detail.innerText()).includes("Segunda línea sin recortar."));
      await capture("email-dossier"); await page.keyboard.press("Escape"); await detail.waitFor({ state: "hidden" });
      if (language === "es-419" && theme === "light") {
        stage = "existing receipt review route";
        await receiptRow.getByRole("button").first().click();
        await detail.getByRole("button", { name: copy.action_review, exact: true }).click();
        await page.getByTestId("business-record-review").waitFor(); assert.equal(await detail.count(), 0);
        stage = "connected Records pagination";
        await page.goto(`${web.origin}/biz?view=transactions`, { waitUntil: "load", timeout: 60000 });
        await page.getByTestId("records-count").filter({ hasText: "126" }).waitFor();
        await page.getByRole("button", { name: words.business.transactions.pagination.last, exact: true }).click();
        await page.locator('[data-testid="records-pagination"][data-page="6"]').waitFor();
        await capture("connected-records");
        stage = "connected invoice gate and real editor";
        await page.goto(`${web.origin}/biz?view=invoicing`, { waitUntil: "load", timeout: 60000 });
        await page.getByTestId("connected-invoicing-workspace").waitFor();
        assert.equal(await page.getByTestId("invoicing-preview").count(), 0); await capture("connected-invoices");
        await page.getByRole("button", { name: words.business.invoicing_preview.create, exact: true }).click();
        await page.getByTestId("invoice-editor").waitFor();
        assert.equal(await page.getByTestId("invoice-editor").getAttribute("data-invoice-source"), "connected");
        await capture("connected-editor");
      }
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
      assert.ok(writes.every(request => request.path.endsWith("/name-prompt") || request.path.endsWith("/reports/query") || request.path.endsWith("/read")), "preview organization never writes a new backend contract");
      results.push({ width, language, theme, startupSha: head, shape, actual, sourceDeniedThenRecovered: true, emailDeniedThenRecovered: true, requests, writes });
    } catch (error) {
      const failure = { width, language, theme, stage, message: safe(error), pathname: pathname(page.url()), requests };
      try { failure.publicUi = safe(await page.locator("body").innerText({ timeout: 2000 })); } catch (error) { diagnostics.push(safe(error)); }
      try { await capture("failure"); } catch (error) { diagnostics.push(safe(error)); }
      writeFileSync(join(output, "failure.json"), JSON.stringify(failure, null, 2));
      throw error;
    } finally { release(); await context.close(); }
  }
  assert.deepEqual(errors, []); assert.deepEqual(external, []);
  git("diff", "--exit-code", head, "--", ...sourcePaths); assert.equal(git("rev-parse", "HEAD"), head); assert.equal(git("rev-parse", "HEAD^{tree}"), tree);
  complete = true;
} catch (error) { originalFailure = error; }
finally {
  if (browser) await browser.close();
  if (!exited) { process.kill(-app.pid, "SIGTERM"); await Promise.race([once(app, "exit"), new Promise(resolve => setTimeout(resolve, 5000))]); }
  if (!exited) { process.kill(-app.pid, "SIGKILL"); await once(app, "exit"); }
  log.end();
  const compiledFiles = [".next/dev/server/app/biz/page.js", ".next/dev/server/app/biz/page_client-reference-manifest.js"].flatMap(relative => { const path = join(repository, "web", relative); return existsSync(path) ? [{ path: relative, sha256: createHash("sha256").update(readFileSync(path)).digest("hex") }] : []; });
  writeFileSync(join(output, "report.json"), JSON.stringify({ complete, identity: { head, tree, runtime: "direct owned Next child from clean exact-head checkout", pid: app.pid, cwd: join(repository, "web"), port: web.port, compiledFiles, synthetic: true, hostedAcceptance: false }, results, captures, errors, external, diagnostics, runtimeStopped: exited }, null, 2));
}
if (originalFailure) throw originalFailure;
