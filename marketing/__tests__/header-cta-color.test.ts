import { expect, test } from "bun:test";
import { readFileSync } from "node:fs";

const read = (name: string) => readFileSync(new URL(`../components/${name}`, import.meta.url), "utf8");
const business = read("business.module.css");
const touchup = read("touchup.module.css");

const background = (css: string, selector: string) => {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`${escaped}\\s*\\{[^}]*?background:\\s*([^;]+);`).exec(css)?.[1].trim();
};

const REST = "var(--cta-rest)";
const DEEP = "var(--cta-deep)";

test("the green pair is declared once", () => {
  expect(/--cta-rest:\s*#2f5a49;/.test(business)).toBe(true);
  expect(/--cta-deep:\s*#1d4236;/.test(business)).toBe(true);
});

test("the scrolled header button rests on the green and darkens on hover", () => {
  const selector = '.header[data-condensed="true"] .utilityNav > .buttonSmall';
  expect(background(business, selector)).toBe(REST);
  expect(background(business, `${selector}:hover`)).toBe(DEEP);
});

test("the header button at the top of the page stays light", () => {
  expect(background(business, '.header[data-condensed="false"] .utilityNav > .buttonSmall')).toBe("#e8ede3");
});

test("the hero button hover outranks its resting rule", () => {
  expect(background(touchup, ".site a.cta")).toBe(REST);
  expect(background(touchup, ".site a.cta:hover")).toBe(DEEP);
});

test("the closing and contact form buttons rest on the green and darken on hover", () => {
  expect(background(business, ".closing .button")).toBe(REST);
  expect(background(business, ".closing .button:hover")).toBe(DEEP);
  expect(background(business, ".submit")).toBe(REST);
  expect(background(business, ".submit:hover")).toBe(DEEP);
});

test("only the contact form uses the submit class", () => {
  const used = ["contact-form", "business-footer", "business-header"].filter((name) =>
    read(`${name}.tsx`).includes("styles.submit"),
  );
  expect(used).toEqual(["contact-form"]);
});
