import { createHash } from "node:crypto";
import { expect, test } from "bun:test";
import spanish from "../content/legal-es.json";
import english from "../content/legal-en.json";
import manifest from "../content/legal-waitlist-source/manifest.json";

for (const [locale, documents] of [["spanish", spanish], ["english", english]] as const) {
for (const slug of Object.keys(documents) as (keyof typeof documents)[]) {
  test(`${slug} preserves the cleared ${locale} words`, () => {
    const document = documents[slug];
    const text = [document.title, ...document.blocks.flatMap((block) =>
      "items" in block && block.items ? block.items : block.text,
    )].join(" ").replaceAll("**", "").replace(/\s+/g, " ").trim();
    expect(createHash("sha256").update(text).digest("hex")).toBe(manifest[slug][`${locale}_text_sha256`]);
    expect(text).not.toContain("<!--");
    expect(text).not.toMatch(/revisión|Lourdes|Eleanor/);
  });
}
}
