import { describe, expect, test } from "bun:test";

import { withBusinessSpace, type BusinessDataSource } from "@/components/business-app/business-data";
import { createFixtureBusinessDataSource } from "@/components/business-app/fixture-data";

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
    updates: async () => {
      log.push("updates");
      return base.updates();
    },
  };
  return { source, log, release };
}

describe("Business calls wait for the space", () => {
  test("a panel opened before the space exists waits instead of failing", async () => {
    const { source, log, release } = recording(0);
    const spaced = withBusinessSpace(source, () => "es-419");
    const reads = Promise.all([spaced.expenses("2026-10-01", "2026-10-31"), spaced.updates()]);
    await Promise.resolve();
    expect(log).toEqual(["start:es-419"]);
    release();
    await reads;
    expect(log).toEqual(["start:es-419", "started", "expenses", "updates"]);
  });

  test("the space starts once for every later call", async () => {
    const { source, log, release } = recording(0);
    release();
    const spaced = withBusinessSpace(source, () => "en");
    await spaced.updates();
    await spaced.updates();
    expect(log).toEqual(["start:en", "started", "updates", "updates"]);
  });

  test("a failed start is retried by the next call", async () => {
    const { source, log, release } = recording(1);
    release();
    const spaced = withBusinessSpace(source, () => "es-419");
    await expect(spaced.updates()).rejects.toThrow("start failed");
    expect(log).not.toContain("updates");
    await spaced.updates();
    expect(log).toEqual(["start:es-419", "start:es-419", "started", "updates"]);
  });
});


test("an old bootstrap cannot dispatch after logout and the new session starts again", async () => {
  const { invalidateBrowserAuth } = await import("@/lib/browser-auth-generation");
  const { source, release } = recording(0);
  let reads = 0;
  const spaced = withBusinessSpace({ ...source, updates: async () => { reads++; return []; } }, () => "en");
  const pending = spaced.updates();
  await Promise.resolve();
  expect(reads).toBe(0);
  invalidateBrowserAuth();
  release();
  await expect(pending).rejects.toThrow("Browser session changed");
  expect(reads).toBe(0);
  await spaced.updates();
  expect(reads).toBe(1);
});
