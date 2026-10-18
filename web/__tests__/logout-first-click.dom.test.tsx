import assert from "node:assert/strict";
import { afterAll, beforeAll, describe, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { leaveSession, signedOutLanding } from "@/lib/logout-flow";

// A real DOM: the Log out control is clicked once and the flow runs from that click.
beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => {
  await GlobalRegistrator.unregister();
});

type Log = string[];

async function mount(options: { businessBuild: boolean; revocation?: "complete" | "failed"; throws?: boolean; cookieSync?: "cleared" | "failed"; accountDeleted?: boolean }) {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const log: Log = [];
  const deps = {
    boundary: { beginConversion: () => log.push("beginConversion"), finishConversion: (id: string | null) => log.push(`finishConversion:${id}`) },
    currentUserId: "user-1",
    signOut: async () => {
      log.push("signOut");
      if (options.throws) throw new Error("network");
      return { revocation: options.revocation ?? ("complete" as const), cookieSync: options.cookieSync ?? "cleared" as const };
    },
    clearLocalState: () => log.push("clear"),
    navigate: (href: string) => log.push(`navigate:${href}`),
    onFailed: () => log.push("failed"),
    businessBuild: options.businessBuild,
    accountDeleted: options.accountDeleted,
  };
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(<button type="button" onClick={() => void leaveSession(deps)}>Cerrar sesión</button>);
  });
  const button = host.querySelector("button")!;
  const clickOnce = () => act(async () => { button.click(); await Promise.resolve(); await Promise.resolve(); await Promise.resolve(); });
  return { act, root, clickOnce, log };
}

describe("logout on the first click", () => {
  test("Business build: one click tells the boundary, signs out, clears local state and lands on login", async () => {
    const page = await mount({ businessBuild: true });
    await page.clickOnce();
    assert.deepEqual(page.log, ["beginConversion", "signOut", "clear", "navigate:/?auth=login"]);
    await page.act(async () => page.root.unmount());
  });

  test("build without the Business flag: the same click lands on the old landing page, never on /biz", async () => {
    const page = await mount({ businessBuild: false });
    await page.clickOnce();
    assert.deepEqual(page.log, ["beginConversion", "signOut", "clear", "navigate:/"]);
    assert.equal(signedOutLanding(false), "/");
    assert.equal(signedOutLanding(true), "/?auth=login");
    await page.act(async () => page.root.unmount());
  });

  test("Done after account deletion lands on the landing page on a Business build too, never on a Business login", async () => {
    const page = await mount({ businessBuild: true, accountDeleted: true });
    await page.clickOnce();
    assert.deepEqual(page.log, ["beginConversion", "signOut", "clear", "navigate:/"]);
    assert.equal(signedOutLanding(true, true), "/");
    await page.act(async () => page.root.unmount());
  });

  test("a failed revocation hands the surface back to the signed-in account, says so, clears nothing and stays", async () => {
    const page = await mount({ businessBuild: true, revocation: "failed" });
    await page.clickOnce();
    assert.deepEqual(page.log, ["beginConversion", "signOut", "finishConversion:user-1", "failed"]);
    await page.act(async () => page.root.unmount());
  });

  test("failed API cookie clearing cannot report successful logout", async () => {
    const page = await mount({ businessBuild: true, cookieSync: "failed" });
    await page.clickOnce();
    assert.deepEqual(page.log, ["beginConversion", "signOut", "finishConversion:user-1", "failed"]);
    await page.act(async () => page.root.unmount());
  });

  test("a sign-out that throws is a failed sign-out, not a half-left session", async () => {
    const page = await mount({ businessBuild: true, throws: true });
    await page.clickOnce();
    assert.deepEqual(page.log, ["beginConversion", "signOut", "finishConversion:user-1", "failed"]);
    await page.act(async () => page.root.unmount());
  });
});
