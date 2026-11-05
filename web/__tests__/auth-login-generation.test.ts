import { expect, test } from "bun:test";
test("login-generation.ts", () => {
  const result = Bun.spawnSync([process.execPath, "test", `${import.meta.dir}/fixtures/auth-account-transition/login-generation.ts`], { cwd: `${import.meta.dir}/..` });
  expect(result.exitCode, result.stderr.toString()).toBe(0);
});
