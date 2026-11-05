import { expect, test } from "bun:test";
test("Business conversation history follows backend workspace availability", () => {
  const result = Bun.spawnSync([process.execPath, "test", `${import.meta.dir}/fixtures/auth-account-transition/history-readiness.tsx`], { cwd: `${import.meta.dir}/..` });
  expect(result.exitCode, result.stderr.toString()).toBe(0);
});
