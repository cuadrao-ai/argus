import { expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import spanish from "../content/app-legal-es.generated.json";
import english from "../content/app-legal-en.generated.json";
import { APP_LEGAL_SLUGS } from "../lib/app-legal";
import { parseBilingualLegalMarkdown, parseLegalMarkdown } from "../lib/legal-markdown";

for (const slug of APP_LEGAL_SLUGS) {
  test(`app ${slug} pages carry the approved source word for word`, () => {
    const source = readFileSync(join(import.meta.dir, "../content/app-legal-source", `${slug}.md`), "utf8");
    const parsed = parseBilingualLegalMarkdown(source);
    expect(spanish[slug]).toEqual(parsed.es);
    expect(english[slug]).toEqual(parsed.en);
    const words = (text: string) => text.replace(/^(?:#{1,2} |- )|\*\*/gm, "").split(/\s+/).filter(Boolean);
    const rendered = (document: typeof parsed.es) =>
      [document.title, ...document.blocks.flatMap((block) => ("items" in block ? block.items : block.text))].flatMap(words);
    expect([...rendered(parsed.es), ...rendered(parsed.en)]).toEqual(words(source.replace(/^---$/m, "")));
  });
}

test("the app pages show one update line and no effective date, like the website pages", () => {
  expect(spanish.privacidad.blocks[0]).toEqual({ kind: "paragraph", text: "Última actualización: 10 de noviembre de 2026" });
  const text = JSON.stringify([spanish, english]);
  expect(text).not.toMatch(/Vigente desde|Effective:/);
});

test.each([
  ["| a | b |", "a table"],
  ["Text[^1]", "a footnote"],
  ["See [this](https://x)", "a link"],
  ["### Sub", "a third-level heading"],
  ["1. First", "a numbered list"],
])("markup the page cannot render stops the build: %p", (line, name) => {
  expect(() => parseLegalMarkdown(`# Title\n${line}\n`)).toThrow(name);
});
