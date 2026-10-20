import { expect, test } from "bun:test";
import { readFileSync } from "node:fs";

const css = readFileSync(new URL("../components/business.module.css", import.meta.url), "utf8");

const background = (selector: string) => {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`${escaped}\\s*\\{[^}]*?background:\\s*([^;]+);`).exec(css)?.[1].trim();
};

test("the scrolled header button rests on the hover color", () => {
  const hover = background(".buttonSmall:hover");
  expect(hover).toBe("var(--cta-hover)");
  expect(background('.header[data-condensed="true"] .utilityNav > .buttonSmall')).toBe(hover);
  expect(/--cta-hover:\s*#30463a;/.test(css)).toBe(true);
});

test("the unscrolled header button keeps its light resting color", () => {
  expect(background('.header[data-condensed="false"] .utilityNav > .buttonSmall')).toBe("#e8ede3");
});

test("the contact form button rests on the brand green and darkens on hover", () => {
  expect(background(".submit")).toBe("#2f5a49");
  expect(background(".submit:hover")).toBe("#1d4236");
});

test("only the contact form uses the swapped button", () => {
  const used = ["contact-form", "business-footer", "business-header"].filter((name) =>
    readFileSync(new URL(`../components/${name}.tsx`, import.meta.url), "utf8").includes("styles.submit"),
  );
  expect(used).toEqual(["contact-form"]);
});
