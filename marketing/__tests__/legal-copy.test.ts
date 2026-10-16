import { createHash } from "node:crypto";
import { expect, test } from "bun:test";
import documents from "../content/legal-es.json";

const approved = {
  privacidad: "967ef49a948378c47bb1bac29bafa6042618a4b1f0f4476a3ca57bdd5a28dcdc",
  terminos: "f5bbbe97b5a6496e576e1f2d244a424c0e4a87ed602677287a328477ab3d5045",
  "eliminar-datos": "5b29aab4b58e4cdc457f0d070b35d49ef6cd8d5e8acc05b4995d9ca1db6a507e",
};

for (const slug of Object.keys(documents) as (keyof typeof documents)[]) {
  test(`${slug} preserves the cleared Spanish words`, () => {
    const document = documents[slug];
    const text = [document.title, ...document.blocks.flatMap((block) =>
      "items" in block && block.items ? block.items : block.text,
    )].join(" ").replaceAll("**", "").replace(/\s+/g, " ").trim();
    expect(createHash("sha256").update(text).digest("hex")).toBe(approved[slug]);
    expect(text).not.toContain("<!--");
    expect(text).not.toMatch(/revisión|Lourdes|Eleanor/);
  });
}
