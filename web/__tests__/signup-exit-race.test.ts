import { expect, test } from "bun:test";

// The front door reads its language and Business flags once, at import, so
// the race runs in its own process with the Business build's values and no
// other NEXT_PUBLIC_ value, since an earlier file may have left mock auth on.
test("exit-race.tsx", () => {
  const inherited = Object.entries(process.env).filter(([name]) => !name.startsWith("NEXT_PUBLIC_"));
  const result = Bun.spawnSync(
    [process.execPath, "test", `${import.meta.dir}/fixtures/signup-email-code/exit-race.tsx`],
    {
      cwd: `${import.meta.dir}/..`,
      env: { ...Object.fromEntries(inherited), NEXT_PUBLIC_ENABLE_SPANISH: "true", NEXT_PUBLIC_BUSINESS_PILOT_ENABLED: "true" },
    },
  );
  expect(result.exitCode, `${result.stdout}\n${result.stderr}`).toBe(0);
});
