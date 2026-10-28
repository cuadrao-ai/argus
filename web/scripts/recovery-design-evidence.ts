import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { chromium, expect } from "@playwright/test";
import { installBreakpointFixture } from "../e2e/support/breakpoint-fixture";
import en from "../public/locales/en/common.json";
import es from "../public/locales/es-419/common.json";

const baseURL = process.env.EVIDENCE_BASE_URL ?? "http://127.0.0.1:3199";
const address = new URL(baseURL);
assert.equal(address.protocol, "http:");
assert.ok(["127.0.0.1", "localhost"].includes(address.hostname));
assert.equal(process.env.NEXT_PUBLIC_MOCK_AUTH, "true");
const fixtureDir = resolve("app/recovery-evidence-fixture");
const fixtureFile = resolve(fixtureDir, "page.tsx");
const marker = "RECOVERY_EVIDENCE_MOCK_FIXTURE_20261023";

const fixtureSource = `"use client";
// ${marker}: generated only inside the local evidence run.
import { useEffect, useState } from "react";
import { RecoveryRequest } from "@/components/auth/RecoveryRequest";
import { RecoveryReset } from "@/components/auth/RecoveryReset";
import { AccountSecurity } from "@/components/auth/AccountSecurity";
import { RecoveryRequestError, type SessionActionResult, type getAuthSecurityActions } from "@/lib/auth-security";

const complete: SessionActionResult = { currentSessionPreserved: false, freshLoginRequired: true, revocation: "complete", cookieSync: "cleared" };
const failed = (authority: "absent" | "unknown"): SessionActionResult => ({
  currentSessionPreserved: "unknown", freshLoginRequired: false, revocation: "failed",
  cookieSync: "not_required", revocationAuthority: authority,
});
const loadSession = async () => ({ id: "synthetic-person" });

export default function RecoveryEvidenceFixture() {
  const [scenario, setScenario] = useState("loading");
  useEffect(() => { setScenario(new URLSearchParams(window.location.search).get("scenario") ?? "request"); }, []);
  const result = scenario === "reset-absent" ? failed("absent") : scenario === "reset-unknown" ? failed("unknown") : complete;
  const actions = (() => ({
    hasRecoverySession: async () => true,
    exchangeRecoveryCode: async () => undefined,
    acceptRecoveryProof: async () => undefined,
    resetRecoveredPassword: async () => result,
    signOutAllSessions: async () => complete,
    changePassword: async () => complete,
    signOutThisBrowser: async () => complete,
    signOutOtherSessions: async () => complete,
    retryCookieCleanup: async () => "cleared",
  })) as typeof getAuthSecurityActions;
  const request = async (_email: string): Promise<void> => {
    if (scenario === "request-limited") throw new RecoveryRequestError(429, 45);
    if (scenario === "request-error") throw new Error("synthetic request refused");
  };
  return <>
    <div style={{ position: "fixed", top: 8, left: 8, zIndex: 9999, padding: "4px 8px", background: "#ffda80", color: "#172b26", borderRadius: 4, font: "bold 12px sans-serif" }}>MOCK COMPONENT FIXTURE</div>
    {scenario.startsWith("request") ? <RecoveryRequest request={request} />
      : scenario.startsWith("reset") ? <RecoveryReset actions={actions} />
      : scenario === "account" ? <AccountSecurity actions={actions} loadSession={loadSession} />
      : null}
  </>;
}
`;

function prepare() {
  assert.equal(existsSync(fixtureDir), false, "evidence route already exists");
  mkdirSync(fixtureDir);
  writeFileSync(fixtureFile, fixtureSource);
  console.log("RECOVERY_EVIDENCE_FIXTURE_PREPARED");
}

function cleanup() {
  if (!existsSync(fixtureDir)) return;
  assert.ok(readFileSync(fixtureFile, "utf8").includes(marker), "refusing to remove a non-evidence route");
  rmSync(fixtureDir, { recursive: true });
  console.log("RECOVERY_EVIDENCE_FIXTURE_REMOVED");
}

async function capture() {
  assert.ok(existsSync(fixtureFile));
  assert.ok(readFileSync(fixtureFile, "utf8").includes(marker));
  const head = execFileSync("git", ["rev-parse", "HEAD"], { encoding: "utf8" }).trim();
  const output = resolve(process.env.EVIDENCE_OUTPUT ?? "../temp/auth-design-evidence", "recovery");
  mkdirSync(output, { recursive: true });
  const sourceFiles = [
    "components/auth/RecoveryRequest.tsx", "components/auth/RecoveryReset.tsx", "components/auth/RecoveryShell.tsx",
    "components/auth/AccountSecurity.tsx", "components/auth/recovery.module.css", "components/auth/account-security.module.css",
    "lib/auth-security.ts", "public/locales/es-419/common.json", "public/locales/en/common.json",
  ];
  const sourceHashes = Object.fromEntries(sourceFiles.map(file => [file, createHash("sha256").update(readFileSync(resolve(file))).digest("hex")]));
  const browser = await chromium.launch({ headless: true });
  const captures: object[] = [];
  try {
    for (const width of [320, 390, 1440]) for (const language of ["es-419", "en"] as const) for (const theme of ["light", "dark"] as const) {
      const height = width < 768 ? 844 : 900;
      const page = await browser.newPage({ viewport: { width, height }, colorScheme: theme, reducedMotion: "reduce" });
      const errors: string[] = [];
      const blocked: string[] = [];
      page.on("pageerror", error => errors.push(error.message));
      await installBreakpointFixture(page, { language, theme, emptyChat: true });
      await page.route("**/*", route => {
        if (!["127.0.0.1", "localhost"].includes(new URL(route.request().url()).hostname)) {
          blocked.push(new URL(route.request().url()).pathname);
          return route.abort();
        }
        return route.fallback();
      });
      const copy = language === "en" ? en : es;
      const snap = async (surface: string, state: string, fixture: boolean) => {
        await page.evaluate(() => document.fonts.ready);
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, `${width} ${language} ${surface} overflow`);
        if (!fixture) await page.evaluate(() => {
          const mark = document.createElement("div");
          mark.dataset.recoveryEvidenceWatermark = "true";
          mark.textContent = "MOCK AUTH CAPTURE";
          Object.assign(mark.style, { position: "fixed", top: "8px", left: "8px", zIndex: "9999", padding: "4px 8px",
            background: "#ffda80", color: "#172b26", borderRadius: "4px", font: "bold 12px sans-serif" });
          document.body.append(mark);
        });
        const file = `${language}-${theme}-${width}-${surface}-${state}.png`;
        const pixels = await page.screenshot({ path: resolve(output, file), fullPage: true, animations: "disabled", scale: "css" });
        if (!fixture) await page.locator('[data-recovery-evidence-watermark="true"]').evaluate(node => node.remove());
        captures.push({ file, head, sha256: createHash("sha256").update(pixels).digest("hex"), width, height, language, theme, surface, state,
          proof: fixture ? "MOCK component fixture" : "actual app route with mock auth" });
      };
      await page.goto(`${baseURL}/auth/forgot-password`, { waitUntil: "networkidle" });
      await expect(page.getByRole("heading", { name: copy.auth.recovery.title })).toBeVisible();
      await snap("request", "initial", false);
      await page.goto(`${baseURL}/auth/recovery`, { waitUntil: "networkidle" });
      await expect(page.locator('p[role="alert"]')).toContainText(copy.auth.recovery.invalid_link);
      await snap("reset", "invalid", false);

      for (const scenario of ["reset-complete", "reset-absent", "reset-unknown"] as const) {
          await page.goto(`${baseURL}/recovery-evidence-fixture?scenario=${scenario}`, { waitUntil: "networkidle" });
          await expect(page.getByText("MOCK COMPONENT FIXTURE")).toBeVisible();
          const password = page.locator('#recovery-password');
          await expect(password).toBeVisible();
          if (scenario === "reset-complete") await snap("reset", "ready", true);
          await password.fill("synthetic long password");
          await page.locator('form button[type="submit"]').click();
          await expect(page.getByRole("heading", { name: copy.auth.recovery.success_title })).toBeVisible();
          if (scenario === "reset-absent") {
            await expect(page.locator('p[role="alert"]')).toContainText(copy.auth.recovery.revocation_authority_missing);
            await expect(page.locator('a[href="/?auth=login"].auth-primary')).toBeVisible();
          }
          if (scenario === "reset-unknown") await expect(page.getByRole("button", { name: copy.auth.recovery.retry_revocation })).toBeVisible();
          await snap("reset", scenario.replace("reset-", ""), true);
      }
      await page.goto(`${baseURL}/recovery-evidence-fixture?scenario=account`, { waitUntil: "networkidle" });
      await expect(page.getByRole("heading", { name: copy.account_security.title })).toBeVisible();
      await snap("account", "initial", true);
      await page.locator('[data-scope="global"] button').click();
      await expect(page.getByRole("alertdialog")).toBeVisible();
      await snap("account", "global-confirm", true);
      if (width === 390) {
        for (const scenario of ["request", "request-error", "request-limited"] as const) {
          await page.goto(`${baseURL}/recovery-evidence-fixture?scenario=${scenario}`, { waitUntil: "networkidle" });
          await expect(page.getByText("MOCK COMPONENT FIXTURE")).toBeVisible();
          await page.locator('#recovery-email').fill("synthetic@example.test");
          await page.locator('form button[type="submit"]').click();
          if (scenario === "request") await expect(page.getByRole("heading", { name: copy.auth.recovery.inbox_title })).toBeVisible();
          else if (scenario === "request-error") await expect(page.locator('p[role="alert"]')).toContainText(copy.auth.recovery.request_error);
          else await expect(page.locator('form button[type="submit"]')).toBeDisabled();
          await snap("request", scenario === "request" ? "inbox" : scenario.replace("request-", ""), true);
        }
      }
      if (width === 320) {
        await page.goto(`${baseURL}/recovery-evidence-fixture?scenario=request-error`, { waitUntil: "networkidle" });
        const email = page.locator('#recovery-email');
        await email.fill("bad");
        await page.locator('form button[type="submit"]').click();
        await expect(email).toBeFocused();
        await snap("request", "keyboard-invalid", true);
      }
      assert.deepEqual(errors, [], `${language} ${theme} ${width} page errors`);
      assert.deepEqual(blocked, [], `${language} ${theme} ${width} external requests`);
      await page.close();
    }
  } finally {
    await browser.close();
    writeFileSync(resolve(output, "manifest.json"), JSON.stringify({ head, synthetic: true, mockFixtureMarker: marker,
      providerProof: "Separate local synthetic GoTrue run; these captures do not prove hosted auth or email.", sourceHashes, captures }, null, 2));
  }
  console.log(JSON.stringify({ head, captures: captures.length, output }));
}

const mode = process.argv[2];
if (mode === "prepare") prepare();
else if (mode === "capture") await capture();
else if (mode === "cleanup") cleanup();
else throw new Error("Choose prepare, capture, or cleanup.");
