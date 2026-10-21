import { expect, test, type Page } from "@playwright/test";
import spanish from "../content/legal-es.json";
import english from "../content/legal-en.json";
import { legalSections } from "../lib/legal-sections";

const PAGES = [
  { path: "/privacidad", label: "En esta página", document: spanish.privacidad },
  { path: "/terminos", label: "En esta página", document: spanish.terminos },
  { path: "/en/privacy", label: "On this page", document: english.privacidad },
  { path: "/en/terms", label: "On this page", document: english.terminos },
];

const isPhone = () => test.info().project.name === "mobile";

async function stickyBottom(page: Page): Promise<number> {
  const box = await (isPhone() ? page.locator("main aside") : page.locator("header").first()).boundingBox();
  return box!.y + box!.height;
}

async function expectBelowSticky(page: Page, id: string) {
  await expect.poll(async () => {
    const top = await page.locator(`h2#${id}`).evaluate((node) => node.getBoundingClientRect().top);
    const bottom = await stickyBottom(page);
    return top >= bottom && top <= bottom + 48;
  }).toBe(true);
}

function currentSection(page: Page, label: string): () => Promise<string | undefined> {
  if (isPhone()) return () => page.getByRole("combobox", { name: label }).inputValue();
  const link = page.getByRole("navigation", { name: label }).locator('a[aria-current="location"]');
  return async () => (await link.count()) === 1 ? (await link.getAttribute("href"))?.slice(1) : undefined;
}

test.beforeEach(async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
});

for (const { path, label, document } of PAGES) {
  const sections = legalSections(document.blocks);
  const middle = sections[Math.floor(sections.length / 2)];

  test(`${path} lists every section heading with a working anchor`, async ({ page }) => {
    await page.goto(path);
    const ids = await page.locator("main h2").evaluateAll((nodes) => nodes.map((node) => node.id));
    expect(ids).toEqual(sections.map((section) => section.id));
    const allIds = await page.locator("[id]").evaluateAll((nodes) => nodes.map((node) => node.id));
    expect(new Set(allIds).size).toBe(allIds.length);
    const index = page.getByRole("navigation", { name: label });
    const select = page.getByRole("combobox", { name: label });
    if (isPhone()) {
      await expect(index).toBeHidden();
      await expect(select).toBeVisible();
      expect(await select.locator("option").allTextContents()).toEqual(sections.map((section) => section.title));
    } else {
      await expect(select).toBeHidden();
      await expect(index).toBeVisible();
      const links = index.getByRole("link");
      expect(await links.evaluateAll((nodes) => nodes.map((node) => node.getAttribute("href")))).toEqual(sections.map((section) => `#${section.id}`));
      expect(await links.allTextContents()).toEqual(sections.map((section) => section.title));
      for (const box of await links.evaluateAll((nodes) => nodes.map((node) => node.getBoundingClientRect().height))) expect(box).toBeGreaterThanOrEqual(44);
      expect(await index.evaluate((node) => getComputedStyle(node).boxShadow)).toBe("none");
      await links.first().focus();
      expect(await links.first().evaluate((node) => getComputedStyle(node).outlineStyle)).not.toBe("none");
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });

  test(`${path} marks the current section while scrolling`, async ({ page }) => {
    await page.goto(path);
    const current = currentSection(page, label);
    await expect.poll(current).toBe(sections[0].id);
    for (const section of [middle, sections[2]]) {
      await page.locator(`h2#${section.id}`).evaluate((node) => window.scrollTo(0, node.getBoundingClientRect().top + window.scrollY - parseFloat(getComputedStyle(node).scrollMarginTop)));
      await expect.poll(current).toBe(section.id);
    }
  });

  test(`${path} jumps to a section below the sticky header`, async ({ page }) => {
    await page.goto(path);
    for (const section of [middle, sections.at(-1)!]) {
      if (isPhone()) await page.getByRole("combobox", { name: label }).selectOption(section.id);
      else await page.getByRole("navigation", { name: label }).getByRole("link", { name: section.title, exact: true }).click();
      await expect(page).toHaveURL(new RegExp(`#${section.id}$`));
      await expectBelowSticky(page, section.id);
      await expect.poll(currentSection(page, label)).toBe(section.id);
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });

  test(`${path} deep link lands below the sticky header`, async ({ page }) => {
    await page.goto(`${path}#${middle.id}`);
    await expectBelowSticky(page, middle.id);
  });
}

test("/privacidad without JavaScript keeps the index as plain links", async ({ browser }, info) => {
  const context = await browser.newContext({ ...info.project.use, javaScriptEnabled: false });
  const page = await context.newPage();
  await page.goto("/privacidad");
  const index = page.getByRole("navigation", { name: "En esta página" });
  await expect(index).toBeVisible();
  await expect(page.getByRole("combobox", { name: "En esta página" })).toBeHidden();
  await expect(index.locator("a[aria-current]")).toHaveCount(0);
  await index.getByRole("link", { name: "8. Cómo borrar tus datos", exact: true }).click();
  await expect(page).toHaveURL(/#como-borrar-tus-datos$/);
  const top = await page.locator("h2#como-borrar-tus-datos").evaluate((node) => node.getBoundingClientRect().top);
  const header = await page.locator("header").first().boundingBox();
  expect(top).toBeGreaterThanOrEqual(header!.y + header!.height);
  await context.close();
});
