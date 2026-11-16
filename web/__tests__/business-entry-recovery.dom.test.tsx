import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, beforeEach, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act, type ReactNode } from "react";
import i18next from "i18next";
import { I18nextProvider } from "react-i18next";
import * as navigation from "next/navigation";
import * as flags from "@/lib/private-alpha-flags";
import english from "@/public/locales/en/common.json";
import spanish from "@/public/locales/es-419/common.json";
import { createServerClient } from "@supabase/ssr";
import { isAuthSessionMissingError } from "@supabase/supabase-js";

type Identity = { data: { user: { id: string; is_anonymous?: boolean } | null }; error: Error | null };
let check: () => Promise<Identity>;
let checks = 0;
let refresh = () => {};
const originalMockAuth = process.env.NEXT_PUBLIC_MOCK_AUTH;
const identity = (user: Identity["data"]["user"] = null, error: Error | null = null): Identity => ({ data: { user }, error });

mock.module("next/navigation", () => ({ ...navigation, useRouter: () => ({ refresh: () => refresh() }) }));
mock.module("@/lib/private-alpha-flags", () => ({ ...flags, businessOnlyWebEnabled: true }));
mock.module("@/lib/supabase-server", () => ({ createClient: async () => ({ auth: { getUser: () => { checks += 1; return check(); } } }) }));
mock.module("@/components/business-app/BusinessApp", () => ({ default: () => <div data-private-workspace>Private workspace</div> }));

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
beforeEach(() => {
  process.env.NEXT_PUBLIC_MOCK_AUTH = "false";
  checks = 0;
  refresh = () => {};
  check = async () => identity();
});
afterEach(() => {
  if (originalMockAuth === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH;
  else process.env.NEXT_PUBLIC_MOCK_AUTH = originalMockAuth;
});
afterAll(async () => { await GlobalRegistrator.unregister(); });

async function entry(search: Record<string, string | string[]> = {}) {
  const { default: BusinessPage } = await import("@/app/biz/page");
  return BusinessPage({ searchParams: Promise.resolve(search) });
}

async function mount(node: ReactNode, lng: "es-419" | "en" = "es-419") {
  const { createRoot } = await import("react-dom/client");
  const i18n = i18next.createInstance();
  await i18n.init({ lng, resources: { "es-419": { translation: spanish }, en: { translation: english } } });
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  const render = async (next: ReactNode) => act(async () => root.render(<I18nextProvider i18n={i18n}>{next}</I18nextProvider>));
  await render(node);
  return { host, render, close: async () => { await act(async () => root.unmount()); host.remove(); } };
}

for (const failure of ["returned", "thrown"] as const) {
  for (const lng of ["es-419", "en"] as const) {
    test(`${failure} identity error shows only existing ${lng} recovery and retries the server`, async () => {
      check = async () => {
        if (failure === "thrown") throw new Error("identity unavailable");
        return identity(null, new Error("identity unavailable"));
      };
      const page = await mount(await entry(), lng);
      try {
        const copy = lng === "en" ? english : spanish;
        assert.equal(page.host.querySelector("h1")?.textContent, copy.auth.session_recovery.error_title);
        assert.equal(page.host.querySelector("a, [data-private-workspace]"), null);
        assert.equal(checks, 1);
        refresh = () => { void entry(); };
        await act(async () => page.host.querySelector<HTMLButtonElement>("button")!.click());
        assert.equal(checks, 2);
        assert.equal(page.host.querySelector("a, [data-private-workspace]"), null);
      } finally { await page.close(); }
    });
  }
}

for (const [label, user] of [["missing", null], ["anonymous", { id: "anonymous-owner", is_anonymous: true }]] as const) {
  test(`settled ${label} identity still redirects to login`, async () => {
    check = async () => identity(user);
    await assert.rejects(entry(), (error: unknown) => {
      assert.match((error as { digest: string }).digest, /NEXT_REDIRECT;replace;\/\?return_to=%2Fbiz&auth=login;307;/);
      return true;
    });
    assert.equal(checks, 1);
  });
}

test("authenticated entry admits the workspace after the server check", async () => {
  check = async () => identity({ id: "owner" });
  const page = await mount(await entry());
  try {
    assert.ok(page.host.querySelector("[data-private-workspace]"));
    assert.equal(page.host.querySelector('[data-testid="session-recovery-screen"]'), null);
    assert.equal(checks, 1);
  } finally { await page.close(); }
});

test("the real SDK response with an empty cookie store redirects a signed-out visitor to login", async () => {
  let requests = 0;
  const client = createServerClient("http://127.0.0.1:54321", "placeholder", {
    cookies: { getAll: () => [], setAll: () => {} },
    global: { fetch: async () => { requests += 1; throw new Error("Unexpected network request"); } },
  });
  const response = await client.auth.getUser();
  assert.equal(response.data.user, null);
  assert.ok(isAuthSessionMissingError(response.error));
  check = async () => response;
  await assert.rejects(entry({ receipt: "receipt_1" }), (error: unknown) => {
    assert.match((error as { digest: string }).digest, /return_to=%2Fbiz%3Freceipt%3Dreceipt_1&auth=login/);
    return true;
  });
  assert.equal(checks, 1);
  assert.equal(requests, 0);
});

test("login keeps only the safe Business destination and allowed state", async () => {
  await assert.rejects(entry({ return_to: "https://outside.invalid", next: "//outside.invalid", receipt: "receipt_1", view: "inbox", business: "//outside.invalid", transfer: ["transfer_1", "transfer_2"] }), (error: unknown) => {
    const destination = (error as { digest: string }).digest.split(";")[2];
    const url = new URL(destination, "http://localhost");
    assert.equal(url.pathname, "/");
    assert.equal(url.searchParams.get("auth"), "login");
    assert.equal(url.searchParams.get("return_to"), "/biz?view=inbox&receipt=receipt_1&transfer=transfer_1");
    assert.equal(url.searchParams.has("next"), false);
    return true;
  });
});

for (const outcome of ["missing", "authenticated"] as const) {
  test(`retry rechecks before ${outcome === "missing" ? "offering login" : "admitting private content"}`, async () => {
    check = async () => identity(null, new Error("identity unavailable"));
    const page = await mount(await entry({ receipt: "receipt_1" }));
    let retry: Promise<ReactNode> | undefined;
    let settle!: (result: Identity) => void;
    try {
      check = () => new Promise(resolve => { settle = resolve; });
      refresh = () => { retry = entry({ receipt: "receipt_1" }); };
      await act(async () => page.host.querySelector<HTMLButtonElement>("button")!.click());
      assert.equal(checks, 2);
      assert.equal(page.host.querySelector("a, [data-private-workspace]"), null);
      assert.ok(retry);
      if (outcome === "missing") {
        const rejected = assert.rejects(retry, (error: unknown) => {
          assert.match((error as { digest: string }).digest, /return_to=%2Fbiz%3Freceipt%3Dreceipt_1&auth=login/);
          return true;
        });
        settle(identity());
        await rejected;
      } else {
        settle(identity({ id: "owner" }));
        await page.render(await retry);
        assert.ok(page.host.querySelector("[data-private-workspace]"));
      }
    } finally { await page.close(); }
  });
}
