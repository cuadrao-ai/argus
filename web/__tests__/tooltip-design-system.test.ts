import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { join } from "node:path";

const root = join(import.meta.dir, "..");

describe("shared tooltip design system", () => {
  test("uses flat Argus styling and exposes tooltip semantics", () => {
    const tooltip = readFileSync(join(root, "components/ui/Tooltip.tsx"), "utf-8");

    expect(tooltip).toContain('role="tooltip"');
    expect(tooltip).toContain("id={tooltipId}");
    expect(tooltip).toContain("aria-describedby");
    expect(tooltip).not.toContain("shadow-[");
  });
});

describe("tooltip placement", () => {
  const viewport = { width: 1000, height: 800 };
  const tip = { width: 200, height: 40 };

  test("stays on its side when it fits, with the tail at the trigger's centre", async () => {
    const { placeTooltip } = await import("../components/ui/Tooltip");
    const placed = placeTooltip({ left: 400, top: 400, width: 100, height: 40 }, tip, viewport, "top");
    expect(placed.side).toBe("top");
    expect(placed.left + placed.arrow).toBe(450);
  });

  test("flips to the other side near the screen edge", async () => {
    const { placeTooltip } = await import("../components/ui/Tooltip");
    expect(placeTooltip({ left: 400, top: 10, width: 100, height: 40 }, tip, viewport, "top").side).toBe("bottom");
    expect(placeTooltip({ left: 900, top: 400, width: 60, height: 40 }, tip, viewport, "right").side).toBe("left");
  });

  test("shifts along the edge to stay on screen, and the tail still points at the trigger", async () => {
    const { placeTooltip } = await import("../components/ui/Tooltip");
    const placed = placeTooltip({ left: 960, top: 400, width: 30, height: 30 }, tip, viewport, "bottom");
    expect(placed.left + tip.width).toBeLessThanOrEqual(viewport.width - 8);
    expect(placed.left).toBeGreaterThanOrEqual(8);
    expect(placed.arrow).toBeGreaterThan(tip.width / 2);
    expect(placed.arrow).toBeLessThanOrEqual(tip.width - 12);
  });

  test("waits 300ms and is never wider than 300px", async () => {
    const { TOOLTIP_DELAY_MS, TOOLTIP_MAX_WIDTH_PX } = await import("../components/ui/Tooltip");
    expect(TOOLTIP_DELAY_MS).toBe(300);
    expect(TOOLTIP_MAX_WIDTH_PX).toBe(300);
    const callers = readFileSync(join(root, "components/sidebar/SidebarNavButton.tsx"), "utf-8");
    expect(callers).not.toMatch(/<Tooltip[^>]*delay=/);
  });
});
