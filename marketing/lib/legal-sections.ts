export type LegalSection = { id: string; title: string };

type LegalBlock = { kind: string; text?: string };

// Drops the section number so renumbering a heading keeps its deep link.
export function sectionId(heading: string): string {
  return heading
    .replace(/^\d+\.\s*/, "")
    .normalize("NFD")
    .replace(/\p{M}/gu, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

export function legalSections(blocks: readonly LegalBlock[]): LegalSection[] {
  const sections = blocks
    .filter((block) => block.kind === "heading" && block.text)
    .map((block) => ({ id: sectionId(block.text!), title: block.text! }));
  const ids = new Set(sections.map((section) => section.id));
  if (ids.size !== sections.length) throw new Error("Two legal headings share one section id.");
  return sections;
}
