import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { chromium, expect } from "@playwright/test";
import es from "../public/locales/es-419/common.json";

const fixtureDir = resolve("app/desktop-modals-evidence-fixture");
const fixtureFile = resolve(fixtureDir, "page.tsx");
const marker = "DESKTOP_MODALS_SYNTHETIC_FIXTURE_1775";
const files = ["business-app/BusinessInvitationForm.tsx", "business-app/transacciones/RecordsAnnotationsPreview.tsx", "business-app/recepcion/ReceptionOriginal.tsx", "business-app/invoicing/ConnectedInvoicingWorkspace.tsx", "business-app/invoicing/InvoiceEditor.tsx", "business-app/BusinessTransferDialog.tsx", "ui/ConfirmDialog.tsx", "ui/AdaptivePanel.tsx"];
const fixture = `"use client";
// ${marker}: generated for local evidence, never shipped.
import { useEffect, useState } from "react";
import { BusinessContext, type BusinessContextValue } from "@/components/business-app/BusinessWorkspace";
import { createFixtureBusinessDataSource } from "@/components/business-app/fixture-data";
import BusinessInvitationForm from "@/components/business-app/BusinessInvitationForm";
import { RecordsAnnotationsPreview, RecordAttachmentPreview } from "@/components/business-app/transacciones/RecordsAnnotationsPreview";
import ReceptionOriginal from "@/components/business-app/recepcion/ReceptionOriginal";
import ConnectedInvoicingWorkspace, { type InvoiceWorkspaceTransport } from "@/components/business-app/invoicing/ConnectedInvoicingWorkspace";
import InvoiceEditor from "@/components/business-app/invoicing/InvoiceEditor";
import { blankInvoiceDraft, invoiceForEditor } from "@/components/business-app/invoicing/invoice-editor-adapter";
import BusinessTransferDialog, { useBusinessTransferCopy } from "@/components/business-app/BusinessTransferDialog";
import { setChosenGrant } from "@/lib/business-grant";
import type { RecordRow } from "@/components/business-app/transacciones/transacciones-model";

const source = createFixtureBusinessDataSource({ chatAvailable: false });
const noop = () => {};
const scope = { userId: "fixture-user", businessId: "39d12d09-bebe-4992-b6dc-cb1a84d52438", grantId: "af2d018e-6e6c-4fc7-9602-9b0b31ff9bc0" };
const chosen = { space_id: scope.businessId, grant_id: scope.grantId, name: "Colmado Rosa", role: "owner" as const, capabilities: ["read", "prepare", "approve"] as const, access_seen: true };
const row: RecordRow = { id: "fixture-record", kind: "gasto", occurredOn: "2026-10-21", counterparty: "Colmado Rosa", money: { amount: "-1250.00", currency: "DOP" }, categoryId: null, account: null, hasProof: false, marks: { personal: false, markedBy: null, fiscal: null }, opens: null };
const invoice = invoiceForEditor({ ...blankInvoiceDraft(), customer_input: { name: "Rosa Pérez", email: "rosa@example.invalid", tax_id: "", address: "Santo Domingo", phone: "", notes: "" }, issued_on: "2026-10-21", due_on: "2026-10-28", items: [{ id: "fixture-item", description: "Servicio", quantity: "1", price: "1250.00", tax: "0", discount: "0", classification: null, tax_treatment: null }] }, "fixture-invoice");
const unused = async (): Promise<never> => { throw new Error("Evidence must not submit"); };
const transport: InvoiceWorkspaceTransport = { listInvoices: async () => ({ items: [], total: 0, page: 1, page_size: 25, stage_counts: {}, summaries: [], query_version: "fixture", issuance_available: false }), listCustomers: async () => ({ items: [], total: 0, page: 1, page_size: 25 }), getInvoice: unused, getCustomer: unused, saveInvoice: unused, saveCustomer: unused, prepareInvoice: unused, submitInvoice: unused, getInvoiceOperation: unused, downloadInvoiceArtifact: unused };

export default function ModalEvidenceFixture() {
  const [scenario, setScenario] = useState("");
  const [data, setData] = useState<Awaited<ReturnType<typeof source.workspace>> | null>(null);
  const [receipt, setReceipt] = useState<Awaited<ReturnType<typeof source.receipts>>[number] | null>(null);
  const [closed, setClosed] = useState(false);
  const [requests, setRequests] = useState(0);
  const copy = useBusinessTransferCopy();
  useEffect(() => { setChosenGrant(scope.grantId); setScenario(new URLSearchParams(window.location.search).get("case") ?? "invite"); void source.workspace().then(setData); void source.receipts("all").then(items => setReceipt({ ...items[0], filename: "comprobante-" + "1234567890".repeat(12) + ".png", received_at: "2026-10-21T12:00:00Z" })); }, []);
  if (!data || !receipt) return null;
  const context = { source, chosen: { ...chosen, capabilities: [...chosen.capabilities] }, records: { workspace: data, overview: null, inbox: [], notes: [], notesTruncated: false, emails: [], error: false }, openPanel: noop, bridge: null } as BusinessContextValue;
  return <BusinessContext.Provider value={context}>
    <main className="min-h-screen bg-[#fafbf8] p-8 text-[#172b26]"><p data-fixture-marker className="text-xs">SYNTHETIC COMPONENT EVIDENCE</p><h1 className="mt-6 font-display text-2xl">{chosen.name}</h1><output data-requests className="sr-only">{requests}</output>
      {!closed && scenario === "invite" ? <BusinessInvitationForm onClose={() => setClosed(true)} /> : null}
      {scenario === "annotations" ? <RecordsAnnotationsPreview><RecordAttachmentPreview row={row} /></RecordsAnnotationsPreview> : null}
      {scenario === "original" ? <ReceptionOriginal receipt={receipt} /> : null}
      {scenario === "customer" ? <ConnectedInvoicingWorkspace scope={scope} business={chosen.name} capabilities={{ prepare: true, issue: false, download: false }} transport={transport} /> : null}
      {!closed && scenario === "invoice" ? <InvoiceEditor initial={invoice} business={chosen.name} customers={[]} onAddCustomer={noop} onSave={noop} onClose={() => setClosed(true)} connection={{ busy: false, blocked: false, amounts: null, fieldErrors: {}, savedInput: invoice, status: null }} /> : null}
      {!closed && scenario === "transfer" ? <BusinessTransferDialog businessName={chosen.name} copy={copy} view={{ kind: "request", members: [{ grant_id: "fixture-member", name: "Rosa Pérez", eligible: true, reason: null }], onRequest: () => setRequests(value => value + 1) }} state={{ kind: "idle" }} onDismiss={() => setClosed(true)} /> : null}
    </main>
  </BusinessContext.Provider>;
}
`;

function prepare() {
  assert.equal(process.env.NEXT_PUBLIC_MOCK_AUTH, "true");
  assert.ok(!existsSync(fixtureDir), "fixture already exists");
  mkdirSync(fixtureDir);
  writeFileSync(fixtureFile, fixture);
}
function cleanup() {
  if (!existsSync(fixtureDir)) return;
  assert.ok(readFileSync(fixtureFile, "utf8").includes(marker));
  rmSync(fixtureDir, { recursive: true });
}
async function capture() {
  const phase = process.env.EVIDENCE_PHASE ?? "after";
  assert.ok(["before", "after"].includes(phase));
  const baseURL = process.env.EVIDENCE_BASE_URL ?? "http://127.0.0.1:3197";
  assert.ok(["127.0.0.1", "localhost"].includes(new URL(baseURL).hostname));
  const output = resolve(process.env.EVIDENCE_OUTPUT ?? "../temp/desktop-modals-evidence", phase);
  mkdirSync(output, { recursive: true });
  const head = execFileSync("git", ["rev-parse", "HEAD"], { encoding: "utf8" }).trim();
  if (process.env.CI) execFileSync("git", ["diff", "--exit-code", "HEAD", "--", ...files.map(file => `components/${file}`)]);
  const trackedChanges = execFileSync("git", ["status", "--porcelain", "--untracked-files=no"], { encoding: "utf8" }).trim();
  const sourceHashes = Object.fromEntries(files.map(file => [file, createHash("sha256").update(readFileSync(resolve("components", file))).digest("hex")]));
  const captures: object[] = [];
  const browser = await chromium.launch();
  try {
    for (const width of [1440, 390]) for (const scenario of ["invite", "annotations", "original", "customer", "invoice", "transfer"]) {
      const page = await browser.newPage({ viewport: { width, height: 900 }, colorScheme: "light", reducedMotion: "reduce" });
      page.setDefaultTimeout(15000);
      page.setDefaultNavigationTimeout(120000);
      await page.clock.setFixedTime(new Date("2026-11-04T12:00:00Z"));
      const errors: string[] = [], blocked: string[] = [];
      page.on("pageerror", error => errors.push(error.message));
      await page.addInitScript(() => { localStorage.setItem("i18nextLng", "es-419"); localStorage.setItem("argus-theme", "light"); });
      await page.route("**/*", route => {
        const url = new URL(route.request().url());
        if (url.origin !== new URL(baseURL).origin) { blocked.push(url.origin); return route.abort(); }
        if (url.pathname.startsWith("/api/")) return route.fulfill({ status: 200, json: {} });
        return route.continue();
      });
      await page.goto(`${baseURL}/desktop-modals-evidence-fixture?case=${scenario}`);
      await expect(page.locator("[data-fixture-marker]")).toBeAttached();
      await page.addStyleTag({ content: "*,*::before,*::after{animation:none!important;transition:none!important;caret-color:transparent!important}nextjs-portal{display:none!important}" });
      if (scenario === "annotations") await page.locator("[data-record-attachment]").click();
      if (scenario === "original") { await page.getByTestId("reception-original").click(); await expect(page.getByTestId("receipt-original-source").locator("img")).toBeVisible(); }
      if (scenario === "customer") {
        await page.getByRole("radio", { name: es.business.invoicing_preview.customers_tab, exact: true }).click();
        await page.getByRole("button", { name: es.business.invoicing_preview.customers_add, exact: true }).click();
        await page.locator("#customer-name").fill("Rosa Pérez");
        await page.getByRole("button", { name: es.common.close, exact: true }).last().click();
      }
      if (scenario === "invoice") {
        await page.locator("#invoice-customer-search").fill("Rosa Pérez editada");
        await page.locator("#invoice-customer-search").press("Tab");
        await page.getByRole("button", { name: es.common.close, exact: true }).last().click();
      }
      if (scenario === "transfer") {
        await page.getByRole("radio", { name: /Rosa Pérez/ }).check();
        await page.getByRole("textbox").fill("Colmado Rosa");
        if (phase === "after" && width === 1440) {
          await page.getByRole("button", { name: es.business.lifecycle.transfer.request, exact: true }).click();
          await expect(page.getByRole("alertdialog")).toBeVisible();
          await expect(page.locator("[data-requests]")).toHaveText("0");
        }
      }
      const surface = scenario === "invite" && width === 1440 ? page.locator("[data-invitation-modal]") : phase === "after" && width === 1440 && ["customer", "invoice", "transfer"].includes(scenario) ? page.getByRole("alertdialog") : page.getByRole("dialog").last();
      await expect(surface).toBeVisible();
      await page.evaluate(() => document.fonts.ready);
      const bounds = await surface.boundingBox();
      assert.ok(bounds);
      if (width === 1440 && phase === "after") {
        if (["annotations", "original"].includes(scenario)) {
          assert.ok(Math.abs(bounds.x + bounds.width - width) < 2, `${scenario} must meet right edge`);
          if (scenario === "original") assert.ok(await surface.evaluate(element => element.scrollWidth <= element.clientWidth), "long filename must wrap inside original panel");
        }
        else { assert.ok(Math.abs(bounds.x + bounds.width / 2 - width / 2) < 2); assert.ok(Math.abs(bounds.y + bounds.height / 2 - 450) < 2); }
      }
      const file = `${scenario}-${width}.png`;
      const pixels = await page.screenshot({ path: resolve(output, file), animations: "disabled", scale: "css" });
      captures.push({ file, width, height: 900, bounds, sha256: createHash("sha256").update(pixels).digest("hex") });
      assert.deepEqual(errors, []);
      assert.deepEqual(blocked, []);
      await page.close();
    }
    writeFileSync(resolve(output, "manifest.json"), JSON.stringify({ phase, head, trackedChanges, fixtureSha256: createHash("sha256").update(fixture).digest("hex"), sourceHashes, proof: "Synthetic local fixtures mounting actual components", captures }, null, 2));
  } finally { await browser.close(); }
}
async function comparePhones() {
  const output = resolve(process.env.EVIDENCE_OUTPUT ?? "../temp/desktop-modals-evidence");
  const before = JSON.parse(readFileSync(resolve(output, "before/manifest.json"), "utf8"));
  const after = JSON.parse(readFileSync(resolve(output, "after/manifest.json"), "utf8"));
  const browser = await chromium.launch();
  const comparisons: object[] = [];
  try {
    const page = await browser.newPage();
    for (const capture of before.captures.filter((item: { width: number }) => item.width === 390)) {
      const result = await page.evaluate(async ({ first, second }) => {
        const pixels = async (base64: string) => {
          const image = new Image(); image.src = "data:image/png;base64," + base64; await image.decode();
          const canvas = document.createElement("canvas"); canvas.width = image.width; canvas.height = image.height;
          const context = canvas.getContext("2d")!; context.drawImage(image, 0, 0);
          return { width: image.width, height: image.height, data: context.getImageData(0, 0, image.width, image.height).data };
        };
        const a = await pixels(first), b = await pixels(second);
        if (a.width !== b.width || a.height !== b.height) throw new Error("Phone dimensions changed");
        let differentPixels = 0, maxChannelDifference = 0;
        for (let i = 0; i < a.data.length; i += 4) {
          let difference = 0;
          for (let channel = 0; channel < 4; channel++) difference = Math.max(difference, Math.abs(a.data[i + channel] - b.data[i + channel]));
          if (difference) differentPixels++;
          maxChannelDifference = Math.max(maxChannelDifference, difference);
        }
        return { differentPixels, maxChannelDifference, totalPixels: a.width * a.height };
      }, { first: readFileSync(resolve(output, "before", capture.file)).toString("base64"), second: readFileSync(resolve(output, "after", capture.file)).toString("base64") });
      // Permit only tiny rasterization noise: no channel changes above 4/255, across at most 0.01% of pixels.
      assert.ok(result.maxChannelDifference <= 4 && result.differentPixels <= result.totalPixels * 0.0001, `390px changed: ${capture.file}: ${JSON.stringify(result)}`);
      comparisons.push({ file: capture.file, ...result });
    }
    writeFileSync(resolve(output, "phone-comparison.json"), JSON.stringify({ before: before.head, after: after.head, width: 390, unchangedWithinRasterTolerance: true, comparisons }, null, 2));
  } finally { await browser.close(); }
}
const command = process.argv[2];
if (command === "prepare") prepare();
else if (command === "cleanup") cleanup();
else if (command === "compare") await comparePhones();
else if (command === "capture") await capture();
else throw new Error("Use prepare, capture, compare, or cleanup");
