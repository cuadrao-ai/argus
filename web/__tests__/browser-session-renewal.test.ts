import { expect, test } from "bun:test";

test("real browser SDK renews persisted expired session before API dispatch after restart", () => {
  const result = Bun.spawnSync([process.execPath, `${import.meta.dir}/fixtures/browser-session-renewal/transport.ts`], { cwd: `${import.meta.dir}/..` });
  expect(result.exitCode, result.stderr.toString()).toBe(0);
});
