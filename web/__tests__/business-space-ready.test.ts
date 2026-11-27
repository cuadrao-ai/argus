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

describe("Only an explicit start creates the person's Business", () => {
  test("reads and writes never start a Business", async () => {
    const { source, log } = recording(0);
    const spaced = withBusinessSpace(source, () => "es-419");
    await Promise.all([spaced.expenses("2026-10-01", "2026-10-31"), spaced.workspace(), spaced.captures("", 10, "inbox")]);
    expect(log).toEqual(["expenses", "workspace"]);
  });

  test("the space starts once for every later ask", async () => {
    const { source, log, release } = recording(0);
    release();
    const spaced = withBusinessSpace(source, () => "en");
    await spaced.ensureSpace("en");
    await spaced.ensureSpace("en");
    expect(log).toEqual(["start:en", "started"]);
  });

  test("a failed start is retried by the next ask", async () => {
    const { source, log, release } = recording(1);
    release();
    const spaced = withBusinessSpace(source, () => "es-419");
    await expect(spaced.ensureSpace("es-419")).rejects.toThrow("start failed");
    await spaced.ensureSpace("es-419");
    expect(log).toEqual(["start:es-419", "start:es-419", "started"]);
  });
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
