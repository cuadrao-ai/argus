import { createHash } from "node:crypto";
import { expect, test } from "bun:test";
import documents from "../content/legal-es.json";

const approved = {
  privacidad: "8c21adbcd7ac6ff2ab2a9e2b54b0cf74e04205a28a646050886907e46e5457f6",
  terminos: "e15f03d6849fd6c46ad68159fbe9f9091f407df6ec688b44cda1b0b10d9ecda4",
  "eliminar-datos": "8d89a035b4642bb5dadc6fe2ba5324fb493f128e3aac087123c8097d5b2da5fc",
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
