import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { join } from "node:path";

const webRoot = join(import.meta.dir, "..");

describe("guest modal viewport fit", () => {
  test("keeps feedback inside the dynamic viewport with a compact desktop cap", () => {
    const source = readFileSync(
      join(webRoot, "components/feedback/FeedbackDialog.tsx"),
      "utf8",
    );

    // Height and scrolling are the shell's now: a sheet below the panel line,
    // a capped centered dialog above it. Either way the form scrolls inside itself.
    expect(source).toContain("<CenteredDialog");
    const dialog = readFileSync(join(webRoot, "components/ui/CenteredDialog.tsx"), "utf8");
    expect(dialog).toContain("max-h-[min(720px,calc(100dvh-64px))]");
    expect(dialog).toContain('<AdaptivePanel title={title}');
    expect(source).toContain("flex-1 overflow-y-auto");
    // The actions are pinned outside the scrolling body, so a long form cannot
    // push Submit off the bottom of the screen.
    expect(source).toContain("footer={");
    expect(source).toContain("form={formId}");
  });

  test("keeps both Omnisearch layouts inside a quieter viewport footprint", () => {
    const source = readFileSync(
      join(webRoot, "components/sidebar/ChatCommandPalette.tsx"),
      "utf8",
    );

    expect(source).toContain("p-3 sm:p-6");
    expect(source).toContain("max-h-[calc(100dvh-1.5rem)]");
    expect(source).toContain("h-[78dvh] w-[94vw] max-w-6xl");
    expect(source).toContain("h-[60dvh] w-full max-w-lg");
    expect(source).toContain("flex-1 overflow-y-auto");
  });
});
