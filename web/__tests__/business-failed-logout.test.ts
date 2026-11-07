import { expect, test } from "bun:test";

test("Business session recovery keeps the selected client for the same account", () => {
  const result = Bun.spawnSync([process.execPath, "test", `${import.meta.dir}/fixtures/auth-account-transition/failed-business-logout.tsx`], {
    cwd: `${import.meta.dir}/..`,
  });
  expect(result.exitCode, result.stderr.toString()).toBe(0);
}, 25_000);
