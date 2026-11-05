import { chromium, webkit } from "@playwright/test"; // run from the package so this resolves
import { createHash } from "node:crypto";
import { writeFileSync } from "node:fs";
const out = process.argv[2];
const pairs = [
  ["es-home", "/business", "/"],
  ["es-personal", "/business/personal", "/personal"],
  ["es-contact", "/business/demo", "/contacto"],
  ["en-home", "/business/en", "/en"],
  ["en-personal", "/business/en/personal", "/en/personal"],
  ["en-contact", "/business/en/demo", "/en/contact"],
];
const results = [];
for (const [engineName, engine] of [["chromium", chromium], ["webkit", webkit]]) {
  const browser = await engine.launch();
  for (const [vw, vh] of [[1440, 900], [390, 844]]) {
    for (const scheme of ["light", "dark"]) {
      const ctx = await browser.newContext({ viewport: { width: vw, height: vh }, colorScheme: scheme, reducedMotion: "reduce" });
      for (const [name, oldPath, newPath] of pairs) {
        const shots = [];
        for (const [base, path] of [["http://localhost:3920", oldPath], ["http://localhost:3921", newPath]]) {
          const page = await ctx.newPage();
          await page.goto(base + path, { waitUntil: "networkidle" });
          await page.evaluate(() => document.fonts.ready);
          await page.waitForTimeout(300);
          shots.push(await page.screenshot({ fullPage: true }));
          await page.close();
        }
        const hashes = shots.map((b) => createHash("sha256").update(b).digest("hex").slice(0, 12));
        const same = hashes[0] === hashes[1];
        const tag = `${engineName}-${vw}-${scheme}-${name}`;
        if (!same) { writeFileSync(`${out}/${tag}-old.png`, shots[0]); writeFileSync(`${out}/${tag}-new.png`, shots[1]); }
        results.push({ tag, same, sizeOld: shots[0].length, sizeNew: shots[1].length });
        console.log(same ? "SAME" : "DIFF", tag, shots[0].length, shots[1].length);
      }
      await ctx.close();
    }
  }
  await browser.close();
}
writeFileSync(`${out}/results.json`, JSON.stringify(results, null, 1));
