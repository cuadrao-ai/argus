import { expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { join } from "node:path";

const root = join(import.meta.dir, "..");

test("the profile has no retired Usage panel or request", () => {
  const panels = readFileSync(join(root, "components/sidebar/ProfileSettingsPanels.tsx"), "utf8");
  const menu = readFileSync(join(root, "components/sidebar/ProfileMenu.tsx"), "utf8");
  const api = readFileSync(join(root, "lib/argus-api.ts"), "utf8");
  expect(panels).not.toContain("UsageModal");
  expect(panels).not.toContain('"usage"');
  expect(menu).not.toContain("usage: !isBusiness");
  expect(api).not.toContain("/me/usage");
});

test("the retained transport still uses its idempotency owner", () => {
  const api = readFileSync(join(root, "lib/argus-api.ts"), "utf8");
  const helper = readFileSync(join(root, "lib/usage-allowance.ts"), "utf8");
  expect(api).toContain("runActionIdempotencyKey(input)");
  expect(helper).toContain('input.type !== "run_backtest"');
  expect(helper).toContain("confirmation_id");
});
