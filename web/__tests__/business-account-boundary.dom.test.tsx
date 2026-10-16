import { expect, test } from "bun:test";
test("Business identity boundary isolates account state and late bootstrap", () => {
  const result = Bun.spawnSync([process.execPath, "test", `${import.meta.dir}/fixtures/auth-account-transition/business-boundary.tsx`], { cwd: `${import.meta.dir}/..` });
  expect(result.exitCode, result.stderr.toString()).toBe(0);
});
