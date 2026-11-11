import { expect, test } from "bun:test";

test.each(["missing", "signed-in-then-sign-out", "startup-blip"])("Business auth startup: %s", (scenario) => {
  const result = Bun.spawnSync([process.execPath, "test", `${import.meta.dir}/fixtures/auth-account-transition/browser-auth-startup.tsx`], {
    cwd: `${import.meta.dir}/..`,
    env: { ...process.env, CUADRAO_TEST_AUTH_STARTUP: scenario },
  });
  expect(result.exitCode, result.stderr.toString()).toBe(0);
});
