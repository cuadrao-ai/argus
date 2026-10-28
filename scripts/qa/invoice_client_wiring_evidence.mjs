import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { chromium } from "../../web/node_modules/@playwright/test/index.mjs";
import { FREEZE_CSS, installBreakpointFixture } from "../../web/e2e/support/breakpoint-fixture.ts";
import { createFixtureBusinessDataSource } from "../../web/components/business-app/fixture-data.ts";
import { invoiceId, invoiceScope, savedInvoice, savedCustomer } from "../../web/__tests__/fixtures/business-invoice-fixture.ts";
import { invoiceDraftSchema } from "../../web/lib/business-invoices-api.ts";

const repository = resolve(import.meta.dirname, "../..");
const git = (...args) => execFileSync("git", args, { cwd: repository, encoding: "utf8" }).trim();
const head = git("rev-parse", "HEAD");
assert.match(process.env.EVIDENCE_EXPECTED_HEAD ?? "", /^[a-f0-9]{40}$/);
assert.equal(head, process.env.EVIDENCE_EXPECTED_HEAD);
git("diff", "--exit-code", head, "--", "web", "scripts/qa/invoice_client_wiring_evidence.mjs", ".github/workflows/invoice-client-wiring-evidence.yml");
assert.equal(git("ls-files", "--others", "--exclude-standard", "--", "web", "scripts/qa/invoice_client_wiring_evidence.mjs", ".github/workflows/invoice-client-wiring-evidence.yml"), "");
assert.equal(process.env.NEXT_PUBLIC_MOCK_AUTH, "true");
assert.equal(process.env.NEXT_PUBLIC_CUADRAO_BUSINESS_INVOICING_ENABLED, "true");
assert.ok(process.env.EVIDENCE_OUTPUT);
const output = resolve(process.env.EVIDENCE_OUTPUT);
const web = process.env.EVIDENCE_WEB_BASE_URL ?? "http://127.0.0.1:4415";
const fixture = process.env.EVIDENCE_FIXTURE_BASE_URL ?? "http://127.0.0.1:4416";
for (const target of [web, fixture]) { const url = new URL(target); assert.equal(url.protocol, "http:"); assert.equal(url.hostname, "127.0.0.1"); assert.equal(url.origin, target); }
assert.equal(process.env.NEXT_PUBLIC_CUADRAO_API_URL, `${fixture}/api/v1`);
const identity = { frontend: head, backend: "synthetic intercepted loopback HTTP contract fixture", hostedAcceptance: false, providerContact: false };
const results = [], captures = [], errors = [], blockedExternalRequests = [], diagnostics = [];
const safeText = value => String(value).replace(/https?:\/\/[^\s"'<>]+/g, "[URL omitted]").slice(0, 5000);
const safeUrl = value => { try { const url = new URL(value); return { origin: url.origin, pathname: [web, fixture].includes(url.origin) ? url.pathname : "[omitted]" }; } catch { return { origin: "[invalid]" }; } };
mkdirSync(output, { recursive: true });
writeFileSync(join(output, "source-sha.txt"), `${head}\n`);
const source = createFixtureBusinessDataSource({ chatAvailable: false });
const workspace = await source.workspace();
const browser = await chromium.launch({ headless: true });
let completed = false, originalFailure;
try {
  for (const width of [1440, 834, 390]) for (const language of ["es-419", "en"]) for (const theme of ["light", "dark"]) {
    const words = JSON.parse(readFileSync(join(repository, "web/public/locales", language, "common.json"), "utf8"));
    const copy = words.business.invoicing_preview, connected = words.business.invoicing;
    const context = await browser.newContext({ viewport: { width, height: 1000 }, hasTouch: width < 1024, locale: language === "en" ? "en-US" : "es-DO", colorScheme: theme, reducedMotion: "reduce", serviceWorkers: "block" });
    const page = await context.newPage(), requests = [], writes = [], customers = [], commands = new Map();
    let invoice = null, creates = 0, prepared = 0, submitted = 0, lostCreate = true, artifactReads = 0, stage = "fixture setup";
    const capture = async name => { const filename = `${name}-${width}-${language}-${theme}.png`, path = join(output, filename); await page.screenshot({ path, fullPage: true, animations: "disabled" }); captures.push({ filename, sha256: createHash("sha256").update(readFileSync(path)).digest("hex") }); };
    try {
      await context.route("**/*", route => { const url = new URL(route.request().url()); if ([web, fixture].includes(url.origin) || ["data:", "blob:"].includes(url.protocol)) return route.fallback(); blockedExternalRequests.push(url.origin); return route.abort(); });
      page.setDefaultTimeout(15000);
      page.on("pageerror", error => errors.push(safeText(error)));
      page.on("requestfailed", request => requests.push({ ...safeUrl(request.url()), method: request.method(), error: safeText(request.failure()?.errorText) }));
      page.on("response", response => { if (response.status() >= 400) requests.push({ ...safeUrl(response.url()), status: response.status() }); });
      await installBreakpointFixture(page, { language, theme, emptyChat: true, consent: "accepted" });
      await page.addInitScript(({ access }) => {
        window.__invoiceAccessClaim = false;
        new MutationObserver(() => { if (document.body?.textContent?.includes(access)) window.__invoiceAccessClaim = true; }).observe(document, { childList: true, subtree: true, characterData: true });
      }, { access: connected.access });
      await page.addInitScript(({ language, theme }) => { localStorage.setItem("cuadrao-business-preview-language", language); localStorage.setItem("argus-theme", theme); }, { language, theme });
      await page.route(`${fixture}/api/v1/business/**`, async route => {
        const request = route.request(), path = new URL(request.url()).pathname, method = request.method();
        const body = request.postDataJSON(), json = (value, status = 200) => route.fulfill({ status, json: value });
        if (method === "OPTIONS") return json(null);
        if (path.endsWith("/spaces")) { await new Promise(resolve => setTimeout(resolve, 250)); return json({ spaces: [{ space_id: invoiceScope.businessId, grant_id: invoiceScope.grantId, name: "Negocio sintético", role: "owner", business_role: "owner", capabilities: ["read", "prepare", "approve"], permissions: ["read", "prepare", "approve", "manage", "download", "export", "assign_owner"], access_seen: true }], closed_spaces: [] }); }
        if (path.endsWith("/space")) return json({ id: invoiceScope.businessId, name: "Negocio sintético" });
        if (path.endsWith("/workspace")) return json(workspace);
        if (path.endsWith("/receipt-activity")) return json(await source.receiptActivity());
        if (path.endsWith("/receipts")) return json(await source.receiptPage("inbox"));
        if (path.endsWith("/overview")) return json(await source.overview("2026-10-01", "2026-10-31"));
        if (path.endsWith("/captures") || path.endsWith("/email/deliveries")) return json({ items: [], next_cursor: null });
        if (path.endsWith("/email")) return json(await source.emailIntake());
        if (path.endsWith("/consent")) return route.fallback();
        if (path.endsWith("/invitations")) return json([]);
        assert.equal(request.headers()["x-business-grant"], invoiceScope.grantId);
        if (path.endsWith("/customers") && method === "GET") return json({ items: customers, total: customers.length, page: 1, page_size: 25 });
        if (path.endsWith("/customers") && method === "POST") { customers.push({ ...savedCustomer(), data: body.data }); return json(customers.at(-1)); }
        if (path.endsWith("/invoices") && method === "GET") return json({ items: invoice ? [invoice] : [], total: invoice ? 1 : 0, page: 1, page_size: 25, stage_counts: { draft: invoice?.operation ? 0 : invoice ? 1 : 0, issued: invoice?.operation?.state.legal === "ACCEPTED" ? 1 : 0, processing: 0, rejected: 0, uncertain: invoice?.operation?.state.submission === "unknown" ? 1 : 0 }, summaries: [], query_version: "synthetic-query", issuance_available: true });
        if (path.endsWith("/invoices") && method === "POST") {
          const key = request.headers()["idempotency-key"]; assert.ok(key); writes.push({ key, body });
          if (commands.has(key)) assert.deepEqual(commands.get(key), body); else { commands.set(key, body); invoice = savedInvoice(invoiceDraftSchema.parse(body.data)); creates++; }
          if (lostCreate) { lostCreate = false; return route.abort("failed"); }
          return json(invoice);
        }
        if (path.endsWith(`/invoices/${invoiceId}`) && method === "PUT") { assert.equal(body.expected_version, invoice.version); invoice = { ...invoice, data: invoiceDraftSchema.parse(body.data), version: invoice.version + 1, field_errors: {}, amounts: { subtotal: "100.01", discount: "0.00", tax: "0.00", total: "100.01" } }; return json(invoice); }
        if (path.endsWith("/prepare")) {
          assert.equal(body.expected_version, invoice.version); assert.equal(invoice.data.tax_inclusion, "excluded"); assert.equal(invoice.data.payment_type, "cash"); assert.equal(invoice.data.income_type, 1);
          assert.equal(invoice.data.issued_on, "2026-10-26"); assert.equal(invoice.data.due_on, "2026-10-26");
          assert.deepEqual(invoice.data.items.map(item => ({ description: item.description, quantity: item.quantity, price: item.price, classification: item.classification, tax_treatment: item.tax_treatment })), [{ description: "Servicio sintético guardado", quantity: "1", price: "100.01", classification: "services", tax_treatment: "exempt" }]); prepared++;
          invoice = { ...invoice, operation: { id: "60000000-0000-4000-8000-000000000006", invoice_id: invoice.id, invoice_revision_id: invoice.revision_id, business_id: invoice.business_id, case_id: "synthetic-immutable-revision", kind: "E32", number: "E320000000001", payload_digest: "a".repeat(64), provider_id: null, state: { submission: "prepared", processing: "unreported", legal: "unreported", xml: "unreported", pdf: "unreported", delivery: "not_requested", reconciliation: "not_needed", diagnostics: [], needs_review: false } } }; return json(invoice);
        }
        if (path.endsWith("/submit")) { assert.equal(body.payload_digest, invoice.operation.payload_digest); submitted++; invoice.operation.state = { ...invoice.operation.state, submission: "unknown", reconciliation: "pending" }; return json(invoice.operation); }
        if (path.endsWith(`/invoices/${invoiceId}`)) {
          if (submitted) invoice.operation.state = { ...invoice.operation.state, submission: "identified", processing: "FINISHED", legal: "ACCEPTED", reconciliation: "not_needed", xml: "available", pdf: "available" };
          return json(invoice);
        }
        if (path.includes("/artifacts/")) { artifactReads++; const pdf = path.endsWith("/pdf"); return route.fulfill({ contentType: pdf ? "application/pdf" : "application/xml", body: pdf ? "%PDF-1.4\n% synthetic artifact\n%%EOF" : "<synthetic-invoice/>" }); }
        if (path.includes("/fiscal-operations/")) return json(invoice.operation);
        return route.fallback();
      });
      stage = "connected entry";
      await page.goto(`${web}/biz?view=invoicing`, { waitUntil: "domcontentloaded", timeout: 60000 });
      await page.waitForLoadState("load", { timeout: 60000 });
      await page.getByTestId("connected-invoicing-workspace").waitFor();
      assert.equal(await page.getByTestId("invoicing-preview").count(), 0);
      assert.equal(await page.evaluate(() => window.__invoiceAccessClaim), false);
      await page.addStyleTag({ content: FREEZE_CSS });
      const dimensions = await page.evaluate(() => ({ width: innerWidth, scroll: document.documentElement.scrollWidth, dark: document.documentElement.classList.contains("dark"), language: document.documentElement.lang }));
      assert.ok(dimensions.scroll <= width); assert.equal(dimensions.dark, theme === "dark"); assert.equal(dimensions.language, language === "en" ? "en" : "es");
      await capture("connected-invoices");
      stage = "incomplete real editor save";
      await page.getByRole("button", { name: copy.create, exact: true }).click();
      await page.getByTestId("invoice-editor").waitFor();
      assert.equal((await page.getByTestId("invoice-editor").innerText()).includes("· new"), false);
      assert.equal(await page.getByTestId("invoice-editor").getAttribute("data-invoice-source"), "connected");
      await page.locator("#invoice-customer-search").fill("Cliente sintético parcial");
      await capture("connected-editor");
      await page.getByRole("button", { name: copy.save_draft, exact: true }).click();
      await page.getByRole("button", { name: connected.retry, exact: true }).waitFor();
      stage = "reload navigation";
      await page.reload({ waitUntil: "domcontentloaded", timeout: 60000 });
      stage = "reload client assets";
      await page.waitForLoadState("load", { timeout: 60000 });
      stage = "pending command readiness";
      assert.equal(await page.evaluate(() => window.__invoiceAccessClaim), false);
      await page.getByRole("button", { name: connected.retry, exact: true }).click();
      await page.getByRole("button", { name: copy.edit_draft, exact: true }).waitFor();
      assert.equal(creates, 1); assert.equal(customers.length, 0); assert.deepEqual(writes[1], writes[0]);
      assert.equal(invoice.data.customer_input.name, "Cliente sintético parcial"); assert.equal(invoice.data.payment_type, null); assert.deepEqual(invoice.data.items, []); assert.equal(prepared, 0); assert.equal(submitted, 0);
      await capture("connected-saved-draft");
      stage = "explicit fiscal choices";
      await page.getByRole("button", { name: copy.edit_draft, exact: true }).click();
      const choose = async (label, value) => { await page.getByRole("button", { name: new RegExp(`^${label}`) }).click(); await page.getByRole("button", { name: value, exact: true }).click(); };
      await page.getByRole("button", { name: words.common.back, exact: true }).click();
      await page.getByRole("button", { name: copy.add_item, exact: true }).click();
      await page.locator('input[id$="-description"]').fill("Servicio sintético guardado");
      await page.locator('input[id$="-price"]').fill("100.01");
      await choose(connected.classification, connected.services); await choose(connected.tax_treatment, connected.exempt);
      await page.getByRole("button", { name: copy.next, exact: true }).click();
      await page.locator("#invoice-issuedOn").fill("26/10/2026"); await page.locator("#invoice-issuedOn").blur();
      await page.locator("#invoice-dueOn").fill("26/10/2026"); await page.locator("#invoice-dueOn").blur();
      await choose(connected.payment_type, connected.cash); await choose(connected.income_type, connected.income_1); await choose(connected.tax_inclusion, connected.excluded);
      assert.equal(await page.getByText(connected.field_required, { exact: true }).count(), 0);
      await capture("connected-fiscal-terms");
      await page.getByRole("button", { name: copy.save_draft, exact: true }).click();
      await page.getByRole("button", { name: connected.prepare, exact: true }).click();
      await page.getByRole("button", { name: connected.submit, exact: true }).waitFor();
      assert.equal(prepared, 1); assert.equal(submitted, 0); assert.equal(invoice.operation.state.legal, "unreported");
      await capture("connected-prepared");
      stage = "submit and persisted fiscal states";
      await page.getByRole("button", { name: connected.submit, exact: true }).click();
      await page.getByRole("button", { name: connected.submit, exact: true }).waitFor({ state: "detached" });
      assert.equal(submitted, 1); assert.equal(invoice.operation.state.submission, "unknown");
      await capture("connected-uncertain");
      await page.getByRole("button", { name: connected.refresh_state, exact: true }).click();
      await page.getByRole("button", { name: copy.official_xml, exact: true }).waitFor({ state: "visible" });
      await page.waitForFunction(issued => [...document.querySelectorAll('[role="tab"]')].some(node => node.textContent === `${issued}1`), connected.issued);
      assert.equal(invoice.operation.state.legal, "ACCEPTED"); assert.equal(invoice.payment_state, "unknown"); assert.equal(invoice.delivery_state, "not_sent");
      for (const kind of ["xml", "pdf"]) { const download = page.waitForEvent("download"); await page.getByRole("button", { name: copy[`official_${kind}`], exact: true }).click(); await download; }
      assert.equal(artifactReads, 2); await capture("connected-accepted-artifacts");
      results.push({ ...identity, width, language, theme, dimensions, creates, customers: customers.length, prepared, submitted, artifactReads, retrySameFrozenCommand: true, payment: invoice.payment_state, delivery: invoice.delivery_state });
    } catch (error) {
      try { writeFileSync(join(output, "failure.json"), `${JSON.stringify({ width, language, theme, stage, error: safeText(error), url: safeUrl(page.url()), publicUi: safeText(await page.locator("body").innerText({ timeout: 2000 })), requests }, null, 2)}\n`); } catch (diagnostic) { diagnostics.push(safeText(diagnostic)); }
      try { await capture("failure"); } catch (diagnostic) { diagnostics.push(safeText(diagnostic)); }
      throw error;
    } finally { await context.close().catch(error => diagnostics.push(safeText(error))); }
  }
  assert.equal(results.length, 12); assert.equal(captures.length, 84); assert.deepEqual(errors, []); assert.deepEqual(blockedExternalRequests, []); completed = true;
} catch (error) { originalFailure = error; throw error; }
finally {
  await browser.close().catch(error => diagnostics.push(safeText(error)));
  try { writeFileSync(join(output, "browser-proof.json"), `${JSON.stringify({ ...identity, completed, results, captures, errors, blockedExternalRequests, diagnostics }, null, 2)}\n`); } catch (error) { if (!originalFailure) throw error; }
}
