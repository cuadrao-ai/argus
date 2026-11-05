import assert from "node:assert/strict";
import { afterAll, beforeAll, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
let calls = 0;
let release!: (response: { items: never[]; next_cursor: null }) => void;
mock.module("@/lib/argus-api", () => ({ listConversations: () => { calls++; return new Promise(resolve => { release = resolve; }); } }));
mock.module("@/components/chat/ChatWorkspace", () => ({ useConversationSurface: () => "business" }));
beforeAll(() => { GlobalRegistrator.register(); (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true; });
afterAll(() => GlobalRegistrator.unregister());
test("history waits for workspace availability and stops for accountant context", async () => {
  const { act } = await import("react"); const { createRoot } = await import("react-dom/client");
  const { useRecentConversations } = await import("@/components/chat/useRecentConversations");
  let state!: ReturnType<typeof useRecentConversations>;
  function Probe({ enabled }: { enabled: boolean }) { state = useRecentConversations({ enabled }); return <p>{state.historyItems.length}</p>; }
  const host = document.createElement("div"); const root = createRoot(host);
  await act(async () => root.render(<Probe enabled={false} />));
  assert.equal(calls, 0);
  await act(async () => root.render(<Probe enabled />));
  assert.equal(calls, 1);
  await act(async () => root.render(<Probe enabled={false} />));
  await act(async () => release({ items: [], next_cursor: null }));
  await act(async () => state.refreshHistory());
  assert.equal(calls, 1);
  assert.equal(state.historyItems.length, 0);
  await act(async () => root.render(<Probe enabled />));
  assert.equal(calls, 2);
  await act(async () => release({ items: [], next_cursor: null }));
  await act(async () => root.unmount());
});
