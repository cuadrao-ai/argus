import { expect, test } from "bun:test";

  test("wraps keyboard focus inside a shared dialog", async () => {
    let dialogFocus: typeof import("@/lib/dialog-focus") | undefined;
    try {
      dialogFocus = await import("@/lib/dialog-focus");
    } catch {
      dialogFocus = undefined;
    }
    expect(dialogFocus).toBeDefined();
    if (!dialogFocus) return;

    const first = { id: "first" };
    const middle = { id: "middle" };
    const last = { id: "last" };
    const focusable = [first, middle, last];

    expect(dialogFocus.dialogTabTarget(focusable, last, false)).toBe(first);
    expect(dialogFocus.dialogTabTarget(focusable, first, true)).toBe(last);
    expect(
      dialogFocus.dialogTabTarget(focusable, { id: "outside" }, false),
    ).toBe(first);
    expect(dialogFocus.dialogTabTarget(focusable, middle, false)).toBeNull();

  });
