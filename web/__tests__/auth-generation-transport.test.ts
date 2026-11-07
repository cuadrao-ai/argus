import { expect, test } from "bun:test";
test.each(["generation-transport.ts", "browser-auth-initial-event.ts"])("%s", (fixture) => {
  const result = Bun.spawnSync([process.execPath, "test", `${import.meta.dir}/fixtures/auth-account-transition/${fixture}`], { cwd: `${import.meta.dir}/..` });
  expect(result.exitCode, result.stderr.toString()).toBe(0);
});
