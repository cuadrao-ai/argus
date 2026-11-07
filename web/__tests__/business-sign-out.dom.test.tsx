import { expect, test } from "bun:test";

test("Business distinguishes explicit sign-out, missing identity, and a different account", () => {
  const result = Bun.spawnSync([process.execPath, "test", `${import.meta.dir}/fixtures/auth-account-transition/business-sign-out.tsx`], { cwd: `${import.meta.dir}/..` });
  expect(result.exitCode, result.stderr.toString()).toBe(0);
});
