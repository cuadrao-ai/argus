import { expect, test } from "bun:test";
test("generation-transport.ts", () => {
  const result = Bun.spawnSync([process.execPath, "test", `${import.meta.dir}/fixtures/auth-account-transition/generation-transport.ts`], { cwd: `${import.meta.dir}/..` });
  expect(result.exitCode, result.stderr.toString()).toBe(0);
});
