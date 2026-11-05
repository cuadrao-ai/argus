import { expect, test } from "@playwright/test";
import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import en from "../public/locales/en/common.json";
import es from "../public/locales/es-419/common.json";
import { openFixture, openSettings, auditTag, type Cell } from "./support/menu-settings-fixture";

const cells: Cell[] = [
  ...[375, 390, 720, 1024].map((width): Cell => ({ width, account: "registered", language: "en", theme: "dark", motion: "on" })),
  { width: 390, account: "registered", language: "es-419", theme: "light", motion: "on" },
];
const surfaces = [
  { name: "country", section: "preferences", key: "app.home_country", sheet: true },
  { name: "usage", section: "data", key: "data.usage", sheet: true },
  { name: "archived", section: "data", key: "data.archived_chats", sheet: true },
  { name: "deleted", section: "data", key: "data.recently_deleted", sheet: true },
  { name: "profile", key: "profile.title", sheet: false },
  { name: "delete-account", section: "data", key: "profile.delete_account", sheet: false },
];
const evidence = process.env.ARGUS_OVERLAY_EVIDENCE_DIR;

for (const cell of cells) {
  for (const surface of surfaces.filter((s) => cell.width < 720 || ["usage", "profile"].includes(s.name))) {
    test(`${auditTag(cell)} motion-on ${surface.name}`, async ({ page }) => {
      const copy = cell.language === "en" ? en : es;
      const label = (key: string): string => key.split(".").reduce<unknown>((v, k) => (v as Record<string, unknown>)[k], copy.settings) as string;
      await openFixture(page, cell);
      await openSettings(page, cell);
      if (surface.section) await page.getByRole("button", { name: label(`${surface.section}.title`), exact: true }).last().click();
      await page.getByRole("button", {
        name: surface.name === "delete-account" ? new RegExp(`^${label(surface.key)}`) : label(surface.key),
        exact: surface.name !== "delete-account",
      }).last().click();
      const panel = page.getByRole("dialog").last();
      await expect(panel).toBeVisible();
      await page.evaluate(async () => {
        await Promise.all(document.getAnimations().filter((a) => a.effect?.getComputedTiming().iterations !== Infinity).map((a) => a.finished.catch(() => {})));
      });
      const box = await panel.boundingBox();
      expect(box).not.toBeNull();
      const geometry = { ...cell, surface: surface.name, box, reducedMotion: await page.evaluate(() => matchMedia("(prefers-reduced-motion: reduce)").matches) };
      if (evidence) {
        mkdirSync(evidence, { recursive: true });
        const stem = path.join(evidence, `${auditTag(cell)}-${surface.name}`);
        await page.screenshot({ path: `${stem}.png`, animations: "allow", scale: "css" });
        writeFileSync(`${stem}.json`, JSON.stringify(geometry, null, 2));
      }
      expect(geometry.reducedMotion).toBe(false);
      if (surface.sheet && cell.width < 1024) {
        expect(box!.x).toBeCloseTo(0, 0);
        expect(box!.width).toBeCloseTo(cell.width, 0);
        expect(box!.y + box!.height).toBeCloseTo(900, 0);
        const targets = await panel.locator("button:visible, input:visible, select:visible").evaluateAll((elements) => elements.map((el) => ({ label: el.getAttribute("aria-label") ?? el.textContent, height: el.getBoundingClientRect().height })));
        expect(targets.filter((target) => target.height < 44)).toEqual([]);
      } else {
        expect(box!.x + box!.width / 2).toBeCloseTo(cell.width / 2, 0);
        expect(box!.y + box!.height / 2).toBeCloseTo(450, 0);
      }
      if (cell.width < 720) {
        const drawer = page.locator(".argus-drawer-panel");
        await expect(drawer).toHaveCSS("transform", "none");
        // Prove the portal independently of the animation fix, including while
        // an ancestor is transformed by a drag or future visual treatment.
        for (const trap of ["transform: translateX(24px)", "filter: blur(0px)", "will-change: transform", "contain: paint"]) {
          await drawer.evaluate((node, style) => node.setAttribute("style", style), trap);
          expect(await panel.boundingBox(), trap).toEqual(box);
        }
        await drawer.evaluate((node) => node.removeAttribute("style"));
      }
      // Portal placement must preserve the shared focus and Escape ownership.
      for (let index = 0; index < 3; index += 1) {
        await page.keyboard.press("Tab");
        await expect.poll(() => panel.evaluate((node) => node.contains(document.activeElement))).toBe(true);
      }
      const openedPanel = await panel.elementHandle();
      await page.keyboard.press("Escape");
      await expect.poll(() => openedPanel!.evaluate((node) => node.isConnected)).toBe(false);
    });
  }
}
