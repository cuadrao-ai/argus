import assert from "node:assert/strict";
import { afterAll, beforeAll, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import i18next from "i18next";
import { I18nextProvider } from "react-i18next";
import spanish from "@/public/locales/es-419/common.json";
import { getBusinessDirectory, getBusinessSpaces } from "@/lib/business-api";
import { liveBusinessDataSource } from "@/components/business-app/business-data";

let workspaceMounts = 0;
mock.module("@/components/business-app/BusinessWorkspace", () => ({ BusinessWorkspaceProvider: ({ children }: { children: ReactNode }) => { workspaceMounts += 1; return children; } }));
mock.module("@/components/business-app/BusinessNamingProvider", () => ({ default: ({ children }: { children: ReactNode }) => children }));
mock.module("@/components/chat/ChatInterface", () => ({ default: () => <input aria-label="Live workspace" /> }));
mock.module("@/components/chat/ConversationShellGuard", () => ({ default: () => null }));
mock.module("@/components/business-app/ConversationUnavailableNotice", () => ({ default: () => null }));
const original = { fetch: globalThis.fetch, auth: process.env.NEXT_PUBLIC_MOCK_AUTH, consent: liveBusinessDataSource.consent };
const closed = { space_id: "39d12d09-bebe-4992-b6dc-cb1a84d52438", name: "Colmado Rosa", grant_id: "af2d018e-6e6c-4fc7-9602-9b0b31ff9bc0", role: "accountant", closed_at: "2026-10-21T17:45:00Z", reopen_until: "2026-11-20T17:45:00Z" };
beforeAll(() => { GlobalRegistrator.register({ url: "http://localhost/biz" }); Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true }); process.env.NEXT_PUBLIC_MOCK_AUTH = "true"; });
afterAll(async () => { globalThis.fetch = original.fetch; if (original.auth === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH; else process.env.NEXT_PUBLIC_MOCK_AUTH = original.auth; Object.assign(liveBusinessDataSource, { consent: original.consent }); await GlobalRegistrator.unregister(); });

test("directory retains closed grants while the legacy list exposes only live grants", async () => {
  const answer = { spaces: [], closed_spaces: [closed] };
  globalThis.fetch = async () => Response.json(answer);
  assert.deepEqual(await getBusinessDirectory(), answer);
  assert.deepEqual(await getBusinessSpaces(), []);
});

test("a closed-only member sees the server reason without mounting or creating a workspace", async () => {
  const calls: string[] = [];
  workspaceMounts = 0;
  globalThis.fetch = async (url, init) => {
    const path = new URL(String(url)).pathname;
    calls.push(`${init?.method ?? "GET"} ${path}`);
    return Response.json(path.endsWith("/spaces") ? { spaces: [], closed_spaces: [closed] } : { spaces: [] });
  };
  Object.assign(liveBusinessDataSource, { consent: async (version: string) => ({ version, accepted_at: "2026-10-21T00:00:00Z" }) });
  const { default: BusinessApp } = await import("@/components/business-app/BusinessApp");
  const i18n = i18next.createInstance(); await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } } });
  const host = document.createElement("div"); document.body.append(host); const root = createRoot(host);
  try {
    await act(async () => root.render(<I18nextProvider i18n={i18n}><BusinessApp /></I18nextProvider>));
    assert.ok(document.body.textContent?.includes("Colmado Rosa está cerrado."));
    assert.equal(workspaceMounts, 0);
    assert.equal(host.querySelector("input"), null);
    assert.ok(calls.every(call => call === "GET /api/v1/business/spaces"));
    assert.equal(document.body.textContent?.includes("Ya no tienes acceso"), false);
  } finally { await act(async () => root.unmount()); host.remove(); }
});


test("account deletion retries failed discovery and warns about a closed owner without blocking", async () => {
  const { default: DeleteDialog } = await import("@/components/sidebar/ProfileDeleteRequestDialog");
  const i18n = i18next.createInstance(); await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  let reads = 0; let deleted = 0;
  const discoverDirectory = async () => {
    reads += 1;
    if (reads === 1) throw new Error("offline");
    return { spaces: [], closed_spaces: [{ ...closed, role: "owner" as const }] };
  };
  const host = document.createElement("div"); document.body.append(host); const root = createRoot(host);
  try {
    await act(async () => root.render(<I18nextProvider i18n={i18n}><DeleteDialog state="idle" supportMailto="mailto:test@example.invalid" onClose={() => undefined} onSubmit={() => { deleted += 1; }} discoverDirectory={discoverDirectory} /></I18nextProvider>));
    const submit = () => [...document.querySelectorAll<HTMLButtonElement>("button")].find(button => button.textContent === spanish.settings.profile.request_deletion.confirm)!;
    assert.equal(submit().disabled, true, "failed ownership discovery cannot enable deletion");
    assert.ok(document.body.textContent?.includes(spanish.business.lifecycle.deletion.failed));
    const retry = [...document.querySelectorAll<HTMLButtonElement>("button")].find(button => button.textContent === spanish.common.retry)!;
    assert.ok(retry);
    await act(async () => retry.click());
    assert.equal(reads, 2);
    assert.equal(submit().disabled, false, "a closed business does not block deletion");
    assert.ok(document.body.textContent?.includes("Colmado Rosa está cerrado. Si borras tu cuenta, nadie podrá reabrirlo"));
    assert.ok(document.body.textContent?.includes("hora de RD"));
    assert.equal(document.body.textContent?.includes(spanish.business.lifecycle.deletion.blocked), false);
    await act(async () => submit().click());
    assert.equal(deleted, 1);
  } finally { await act(async () => root.unmount()); host.remove(); }
});
