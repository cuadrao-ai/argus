import { expect, test } from "bun:test";
test("Business access dismissal follows the actual application account boundary", () => {
  const result = Bun.spawnSync([process.execPath, "test", `${import.meta.dir}/fixtures/business-clutter/owner-boundary.tsx`], { cwd: `${import.meta.dir}/..` });
  expect(result.exitCode, result.stderr.toString()).toBe(0);
});
