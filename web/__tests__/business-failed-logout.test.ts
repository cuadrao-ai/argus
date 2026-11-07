import { expect, test } from "bun:test";

test("Business operations recover only when a failed logout leaves the same session", () => {
  const result = Bun.spawnSync([process.execPath, "test", `${import.meta.dir}/fixtures/auth-account-transition/failed-business-logout.tsx`], {
    cwd: `${import.meta.dir}/..`,
  });
  expect(result.exitCode, result.stderr.toString()).toBe(0);
});
