import { describe, expect, test } from "bun:test";

import { withBusinessSession, withBusinessSpace, type BusinessDataSource } from "@/components/business-app/business-data";
import { createFixtureBusinessDataSource } from "@/components/business-app/fixture-data";
import { LISTO_LIMIT, listoBatches, runListoBatches } from "@/components/business-app/recepcion/reception-approval";
import { browserAuthGeneration, observeBrowserAuth } from "@/lib/browser-auth-generation";

function recording(startFails: number) {
  const base = createFixtureBusinessDataSource();
  const log: string[] = [];
  let release: () => void = () => {};
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  let failures = startFails;
  const source: BusinessDataSource = {
    ...base,
    ensureSpace: async (language) => {
      log.push(`start:${language}`);
      await gate;
      if (failures > 0) {
        failures -= 1;
        throw new Error("start failed");
      }
      log.push("started");
      return { id: "space-1", name: "Mi negocio" };
    },
    expenses: async (from, to) => {
      log.push("expenses");
      return base.expenses(from, to);
    },
    workspace: async () => {
      log.push("workspace");
      return base.workspace();
    },
  };
  return { source, log, release };
}

describe("Business calls wait for the space", () => {
  test("a panel opened before the space exists waits instead of failing", async () => {
    const { source, log, release } = recording(0);
    const spaced = withBusinessSpace(source, () => "es-419");
    const reads = Promise.all([spaced.expenses("2026-10-01", "2026-10-31"), spaced.workspace()]);
    await Promise.resolve();
    expect(log).toEqual(["start:es-419"]);
    release();
    await reads;
    expect(log).toEqual(["start:es-419", "started", "expenses", "workspace"]);
  });

  test("the space starts once for every later call", async () => {
    const { source, log, release } = recording(0);
    release();
    const spaced = withBusinessSpace(source, () => "en");
    await spaced.workspace();
    await spaced.workspace();
    expect(log).toEqual(["start:en", "started", "workspace", "workspace"]);
  });

  test("a failed start is retried by the next call", async () => {
    const { source, log, release } = recording(1);
    release();
    const spaced = withBusinessSpace(source, () => "es-419");
    await expect(spaced.workspace()).rejects.toThrow("start failed");
    expect(log).not.toContain("workspace");
    await spaced.workspace();
    expect(log).toEqual(["start:es-419", "start:es-419", "started", "workspace"]);
  });
});


test("an old bootstrap cannot dispatch after logout and the new session starts again", async () => {
  const { invalidateBrowserAuth } = await import("@/lib/browser-auth-generation");
  const { source, release } = recording(0);
  let reads = 0;
  const spaced = withBusinessSpace({ ...source, workspace: async () => { reads++; return source.workspace(); } }, () => "en");
  const pending = spaced.workspace();
  await Promise.resolve();
  expect(reads).toBe(0);
  invalidateBrowserAuth();
  release();
  await expect(pending).rejects.toThrow("Browser session changed");
  expect(reads).toBe(0);
  await spaced.workspace();
  expect(reads).toBe(1);
});

test("retiring the workspace session stops the next approval batch", async () => {
  const { source } = recording(0);
  const reply = Promise.withResolvers<Awaited<ReturnType<BusinessDataSource["approveListos"]>>>();
  const sent: number[] = [];
  const live: BusinessDataSource = { ...source, mode: "live", approveListos: async (items) => {
    sent.push(items.length);
    return sent.length === 1 ? reply.promise : { results: [] };
  } };
  observeBrowserAuth("test-approval-owner");
  try {
    const previous = withBusinessSession(live, browserAuthGeneration());
    const targets = Array.from({ length: LISTO_LIMIT + 1 }, (_, index) => ({
      draft_id: `draft-${index}`, version: 1, rowId: `receipt-${index}`, title: "Synthetic receipt",
    }));
    let nextKey = 0;
    const pending = runListoBatches(previous.approveListos, listoBatches(targets, () => `key-${++nextKey}`));
    expect(sent).toEqual([LISTO_LIMIT]);

    observeBrowserAuth(null);
    observeBrowserAuth("test-approval-owner");
    reply.resolve({ results: [] });
    await pending;
    expect(sent).toEqual([LISTO_LIMIT]);

    const current = withBusinessSession(live, browserAuthGeneration());
    await current.approveListos([{ draft_id: "new-draft", version: 1 }], "new-key");
    expect(sent).toEqual([LISTO_LIMIT, 1]);
  } finally {
    observeBrowserAuth(null);
  }
});
