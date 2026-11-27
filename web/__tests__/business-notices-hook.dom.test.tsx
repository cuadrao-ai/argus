import { afterAll, afterEach, beforeAll, expect, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act } from "react";
import { createRoot } from "react-dom/client";
import type { BusinessNotice } from "@/lib/business-notifications";
import type { BusinessNotices } from "@/components/business-app/foundation/useBusinessNotices";

const invitation = (index: number): BusinessNotice => ({ id: `invite-${index}`, kind: "invitation_received", business_id: `business-${index}`, business_name: `Negocio ${index}`, requested_role: "viewer", unread: false });

const originalFetch = globalThis.fetch;
const originalMockAuth = process.env.NEXT_PUBLIC_MOCK_AUTH;
const cleanups: (() => Promise<void>)[] = [];
beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
});
afterEach(async () => {
  for (const cleanup of cleanups.splice(0)) await cleanup();
  globalThis.fetch = originalFetch;
});
afterAll(async () => {
  if (originalMockAuth === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH;
  else process.env.NEXT_PUBLIC_MOCK_AUTH = originalMockAuth;
  await GlobalRegistrator.unregister();
});

/** The hook over a server whose list answers wait until the test sends each one. */
async function mount() {
  const { useBusinessNotices } = await import("@/components/business-app/foundation/useBusinessNotices");
  const asked: { answer: (items: BusinessNotice[]) => Promise<void>; fail: () => Promise<void> }[] = [];
  globalThis.fetch = (async (input: RequestInfo | URL) => {
    if (!String(input).endsWith("/business/notifications")) return Response.json({ updated: 0 });
    return new Promise<Response>((resolve) => {
      const send = (response: Response) => act(async () => { resolve(response); await new Promise((turn) => setTimeout(turn, 5)); });
      asked.push({
        answer: (items) => send(Response.json({ items, unread_count: items.filter((item) => item.unread).length })),
        fail: () => send(Response.json({ code: "unavailable" }, { status: 503 })),
      });
    });
  }) as typeof fetch;
  let notices: BusinessNotices | undefined;
  function Probe() { notices = useBusinessNotices(true); return null; }
  const root = createRoot(document.createElement("div"));
  cleanups.push(async () => { await act(async () => root.unmount()); });
  await act(async () => root.render(<Probe />));
  const settle = () => act(async () => new Promise((turn) => setTimeout(turn, 5)));
  await settle();
  return { asked, settle, notices: () => notices!, ids: () => notices!.items.map((item) => item.id) };
}

test("an answer that left before an invitation was removed does not bring it back, and the list is asked again", async () => {
  const page = await mount();
  await page.asked[0].answer([invitation(1), invitation(2)]);
  expect(page.ids()).toEqual(["invite-1", "invite-2"]);

  await act(async () => page.notices().refresh());
  await page.settle();
  expect(page.asked).toHaveLength(2);
  await act(async () => page.notices().remove("invite-1"));
  await page.asked[1].answer([invitation(1), invitation(2)]);
  expect(page.ids()).toEqual(["invite-2"]);

  await page.settle();
  expect(page.asked).toHaveLength(3);
  await page.asked[2].answer([invitation(2), invitation(3)]);
  expect(page.ids()).toEqual(["invite-2", "invite-3"]);
});

test("a failure that left before an invitation was removed does not replace the list", async () => {
  const page = await mount();
  await page.asked[0].answer([invitation(1), invitation(2)]);
  await act(async () => page.notices().refresh());
  await page.settle();
  await act(async () => page.notices().remove("invite-1"));
  await page.asked[1].fail();

  expect(page.notices().load).toBe("ready");
  expect(page.ids()).toEqual(["invite-2"]);
});

test("an answer that left after the removal replaces the list", async () => {
  const page = await mount();
  await page.asked[0].answer([invitation(1), invitation(2)]);
  await act(async () => page.notices().remove("invite-1"));
  await act(async () => page.notices().refresh());
  await page.settle();
  await page.asked[1].answer([invitation(2), invitation(3)]);

  expect(page.ids()).toEqual(["invite-2", "invite-3"]);
  expect(page.asked).toHaveLength(2);
});

test("an answer that left before a notice was read does not turn it unread again", async () => {
  const page = await mount();
  const unread = { ...invitation(1), unread: true };
  await page.asked[0].answer([unread]);
  await act(async () => page.notices().refresh());
  await page.settle();
  await act(async () => page.notices().markRead(["invite-1"]));
  await page.asked[1].answer([unread]);

  expect(page.notices().items.map((item) => item.unread)).toEqual([false]);
});
