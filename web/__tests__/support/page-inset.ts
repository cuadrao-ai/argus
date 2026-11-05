import { readFileSync } from "node:fs";
import { join } from "node:path";

/**
 * The room the page gives up to the side of the viewport, read from the app's own stylesheet.
 * "0px" means an open panel lies over the page without moving it.
 */
export function pageInset(): string {
  if (!document.getElementById("globals-under-test")) {
    const sheet = document.createElement("style");
    sheet.id = "globals-under-test";
    sheet.textContent = readFileSync(join(import.meta.dir, "../../app/globals.css"), "utf8");
    document.head.append(sheet);
  }
  return getComputedStyle(document.body).paddingRight || "0px";
}
