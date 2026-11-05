import { expect, test } from "bun:test";
test("real SDK logout wins over pending login and verification session installation", () => {
  const result = Bun.spawnSync([process.execPath, `${import.meta.dir}/fixtures/auth-account-transition/sdk-logout-race.ts`], { cwd: `${import.meta.dir}/..` });
  expect(result.exitCode, result.stderr.toString()).toBe(0);
});
