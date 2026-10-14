import assert from "node:assert/strict";
import { afterAll, beforeAll, describe, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { ReceiptDetail } from "@/lib/business-api";

// A real DOM for mount and unmount; registered for this file only.
beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => {
  await GlobalRegistrator.unregister();
});

/** A hand-driven clock: nothing fires until the test advances it. */
function fakeClock() {
  const due: { at: number; fn: () => void; live: boolean }[] = [];
  let now = 0;
  return {
    clock: (fn: () => void, ms: number) => {
      const entry = { at: now + ms, fn, live: true };
      due.push(entry);
      return () => {
        entry.live = false;
      };
    },
    pending: () => due.filter((e) => e.live && e.at > now).length,
    advance: (ms: number) => {
      now += ms;
      for (const entry of due.filter((e) => e.live && e.at <= now)) {
        entry.live = false;
        entry.fn();
      }
    },
  };
}

const receipt = (over: Partial<ReceiptDetail>): ReceiptDetail =>
  ({ id: "r1", status: "queued", read_pending: true, version: 1, merchant: null, amount: null, ...over } as unknown as ReceiptDetail);

async function mount(answers: (() => Promise<ReceiptDetail>)[], initialPending = true) {
  const { act, useState } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { useReceiptReadPoll, READ_POLL_MS, READ_POLL_LIMIT } = await import("../components/business-app/receipt-read-poll");
  const timer = fakeClock();
  let asked = 0;
  const source = { receipt: async () => { const answer = answers[Math.min(asked, answers.length - 1)]; asked += 1; return answer(); } };
  const seen: { settled: ReceiptDetail[]; stalled: number } = { settled: [], stalled: 0 };
  let setPendingOutside: (value: boolean) => void = () => {};
  function Harness() {
    const [pending, setPending] = useState(initialPending);
    setPendingOutside = setPending;
    useReceiptReadPoll({
      source,
      receiptId: "r1",
      pending,
      onSettled: (next) => { seen.settled.push(next); setPending(next.read_pending === true); },
      onStalled: () => { seen.stalled += 1; },
      clock: timer.clock,
    });
    return <p data-pending={String(pending)} />;
  }
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => { root.render(<Harness />); });
  const tick = () => act(async () => { timer.advance(READ_POLL_MS); await Promise.resolve(); await Promise.resolve(); });
  return { act, root, host, timer, tick, seen, asked: () => asked, setPending: (v: boolean) => act(async () => setPendingOutside(v)), READ_POLL_LIMIT };
}

describe("the review page while a read is pending", () => {
  test("asks again every interval and fills in the moment the server says the read settled", async () => {
    const page = await mount([
      () => Promise.resolve(receipt({ read_pending: true })),
      () => Promise.resolve(receipt({ read_pending: true })),
      () => Promise.resolve({ ...receipt({}), read_pending: false, status: "review_ready", merchant: "Hotel Brisa" } as ReceiptDetail),
    ]);
    assert.equal(page.asked(), 0);
    await page.tick();
    await page.tick();
    assert.equal(page.asked(), 2);
    assert.deepEqual(page.seen.settled, []);
    await page.tick();
    assert.equal(page.asked(), 3);
    assert.equal(page.seen.settled.length, 1);
    assert.equal(page.seen.settled[0].merchant, "Hotel Brisa");
    assert.equal(page.host.querySelector("p")!.getAttribute("data-pending"), "false");
    // Settled: nothing else scheduled, no further asks however long we wait.
    assert.equal(page.timer.pending(), 0);
    await page.tick();
    assert.equal(page.asked(), 3);
    await page.act(async () => page.root.unmount());
  });

  test("a failed ask counts as one ask and the next still happens", async () => {
    const page = await mount([
      () => Promise.reject(new Error("network")),
      () => Promise.resolve({ ...receipt({}), read_pending: false, status: "saved" } as ReceiptDetail),
    ]);
    await page.tick();
    assert.equal(page.seen.settled.length, 0);
    await page.tick();
    assert.equal(page.seen.settled.length, 1);
    await page.act(async () => page.root.unmount());
  });

  test("stops after the bound and says so once; never decides on its own that the read finished", async () => {
    const page = await mount([() => Promise.resolve(receipt({ read_pending: true }))]);
    for (let i = 0; i < page.READ_POLL_LIMIT; i += 1) await page.tick();
    assert.equal(page.asked(), page.READ_POLL_LIMIT);
    assert.equal(page.seen.stalled, 1);
    assert.equal(page.seen.settled.length, 0);
    assert.equal(page.timer.pending(), 0);
    await page.tick();
    assert.equal(page.asked(), page.READ_POLL_LIMIT);
    assert.equal(page.host.querySelector("p")!.getAttribute("data-pending"), "true");
    await page.act(async () => page.root.unmount());
  });

  test("nothing is asked while no read is pending, and unmount cancels a scheduled ask", async () => {
    const quiet = await mount([() => Promise.resolve(receipt({ read_pending: true }))], false);
    await quiet.tick();
    assert.equal(quiet.asked(), 0);
    await quiet.setPending(true);
    assert.equal(quiet.timer.pending(), 1);
    await quiet.act(async () => quiet.root.unmount());
    await quiet.tick();
    assert.equal(quiet.asked(), 0);
  });
});
