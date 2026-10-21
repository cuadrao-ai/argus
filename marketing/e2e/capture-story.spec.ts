import { expect, test, type Page } from "@playwright/test";

async function chapter(page: Page, index: number, fraction = 0.5) {
  await page.locator("#la-idea").evaluate((section, position) => {
    const frame = section.querySelector<HTMLElement>("[data-story-pin]")!;
    const runway = section.querySelector<HTMLElement>("[data-story-runway]")!;
    const before = parseFloat(getComputedStyle(section).getPropertyValue("--story-before"));
    const segment = (runway.offsetHeight - before - frame.offsetHeight) / 3;
    window.scrollTo(0, runway.getBoundingClientRect().top + window.scrollY + before - parseFloat(getComputedStyle(frame).top) + segment * (position.index + position.fraction));
  }, { index, fraction });
}

for (const path of ["/", "/en"]) {
  test(`${path} scroll advances and reverses the receipt chapters before releasing the page`, async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "no-preference" });
    await page.goto(path);
    const story = page.locator("#la-idea");
    await expect(story).toHaveAttribute("data-story-mode", "scroll");
    const labels = path === "/" ? ["Recibo recibido", "Revisión del gasto", "Registro aprobado"] : ["Receipt received", "Expense review", "Approved record"];
    for (const index of [0, 1, 2, 1, 0]) {
      await chapter(page, index);
      await expect(page.getByRole("tab").nth(index)).toHaveAttribute("aria-selected", "true");
      await expect(page.getByRole("tabpanel")).toContainText(labels[index]);
      const panel = await page.getByRole("tabpanel").boundingBox();
      const header = await page.locator("header").boundingBox();
      expect(panel!.y).toBeGreaterThanOrEqual(header!.y + header!.height);
      expect(panel!.y + panel!.height).toBeLessThanOrEqual((await page.evaluate(() => innerHeight)) - 20);
    }
    await chapter(page, 2, 0.1);
    const held = await story.locator("[data-story-pin]").boundingBox();
    await chapter(page, 2, 0.9);
    expect((await story.locator("[data-story-pin]").boundingBox())!.y).toBeCloseTo(held!.y, 0);
    await expect(page.getByRole("tabpanel")).toContainText(labels[2]);
    await chapter(page, 3, 0.5);
    expect((await story.locator("[data-story-pin]").boundingBox())!.y).toBeLessThan(held!.y - 100);
  });
}

test("scroll chapters retain click and keyboard shortcuts without moving passive-scroll focus", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await page.goto("/#la-idea");
  await expect(page.locator("#la-idea")).toHaveAttribute("data-story-mode", "scroll");
  const tabs = page.getByRole("tab");
  await tabs.nth(1).click();
  await expect(tabs.nth(1)).toHaveAttribute("aria-selected", "true");
  await expect(tabs.nth(1)).toBeFocused();
  await page.keyboard.press("ArrowRight");
  await expect(tabs.nth(2)).toHaveAttribute("aria-selected", "true");
  await expect(tabs.nth(2)).toBeFocused();
  await chapter(page, 0);
  await expect(tabs.nth(0)).toHaveAttribute("aria-selected", "true");
  await expect(tabs.nth(2)).toBeFocused();
});

for (const fallback of ["reduced motion", "short landscape"] as const) {
  test(`${fallback} keeps an ordinary manual rail with no added scroll distance`, async ({ page }) => {
    await page.emulateMedia({ reducedMotion: fallback === "reduced motion" ? "reduce" : "no-preference" });
    if (fallback === "short landscape") await page.setViewportSize({ width: 844, height: 390 });
    await page.goto("/");
    await expect(page.locator("#la-idea")).toHaveAttribute("data-story-mode", "manual");
    await expect(page.locator("[data-story-pin]")).toHaveCount(0);
    const runway = page.locator("[data-story-runway]");
    const panels = page.locator("[data-story-stage]");
    expect(await runway.evaluate(node => node.getBoundingClientRect().bottom) -
      await panels.evaluate(node => getComputedStyle(node).display === "contents"
        ? node.parentElement!.getBoundingClientRect().bottom
        : node.getBoundingClientRect().bottom)).toBeLessThanOrEqual(1);
    await page.getByRole("tab").last().click();
    await expect(page.getByRole("tabpanel")).toContainText("Registro aprobado");
    await page.keyboard.press("Home");
    await expect(page.getByRole("tabpanel")).toContainText("Recibo recibido");
  });
}

test("320px viewport keeps the rail and every receipt readable", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 740 });
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await page.goto("/");
  for (const tab of await page.getByRole("tab").all()) {
    await tab.click();
    await expect(tab).toHaveAttribute("aria-selected", "true");
    await expect(page.getByRole("tabpanel")).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1);
  }
});


test("native wheel input advances and reverses a pinned chapter", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await page.goto("/");
  await expect(page.locator("#la-idea")).toHaveAttribute("data-story-mode", "scroll");
  await chapter(page, 0);
  const frame = page.locator("[data-story-pin]");
  const before = (await frame.boundingBox())!.y;
  await page.mouse.move(150, 300);
  const distance = (await page.evaluate(() => innerHeight)) / 2;
  await page.mouse.wheel(0, distance);
  await expect(page.getByRole("tab").nth(1)).toHaveAttribute("aria-selected", "true");
  expect((await frame.boundingBox())!.y).toBeCloseTo(before, 0);
  await page.mouse.wheel(0, -distance);
  await expect(page.getByRole("tab").nth(0)).toHaveAttribute("aria-selected", "true");
  expect((await frame.boundingBox())!.y).toBeCloseTo(before, 0);
});


test("phone introduction scrolls away before the complete rail and card stay in view", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await page.goto("/#el-producto");
  await expect(page.locator("#la-idea")).toHaveAttribute("data-story-mode", "scroll");
  const title = page.locator("#capture-title");
  await expect(title).toHaveCount(1);
  const header = page.locator("header");
  await expect.poll(async () => {
    const heading = (await title.boundingBox())!;
    const navigation = (await header.boundingBox())!;
    return heading.y >= navigation.y + navigation.height && heading.y + heading.height <= 844;
  }).toBe(true);
  for (const index of [0, 1, 2]) {
    await chapter(page, index);
    const heading = (await title.boundingBox())!;
    const navigation = (await header.boundingBox())!;
    expect(heading.y + heading.height).toBeLessThanOrEqual(navigation.y + navigation.height);
    const pinned = (await page.locator("[data-story-pin]").boundingBox())!;
    expect(pinned.y).toBeGreaterThanOrEqual(navigation.y + navigation.height);
    expect(pinned.y + pinned.height).toBeLessThanOrEqual(844 - 20);
    await expect(page.getByRole("tab").nth(index)).toHaveAttribute("aria-selected", "true");
  }
  await page.setViewportSize({ width: 390, height: 850 });
  await expect(page.locator("#la-idea")).toHaveAttribute("data-story-mode", "scroll");
  await chapter(page, 2);
  await expect(page.getByRole("tab").last()).toHaveAttribute("aria-selected", "true");
});
