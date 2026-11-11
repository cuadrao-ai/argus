export type LegalBlock =
  | { kind: "heading"; text: string }
  | { kind: "paragraph"; text: string }
  | { kind: "list"; items: string[] };

export type LegalDocument = { title: string; blocks: LegalBlock[] };

// The page renders headings, paragraphs, bullet lists and **bold**. Anything
// else in an approved source would be silently dropped or mangled, so it throws.
const UNSUPPORTED = [
  { pattern: /^#{3,}\s/, name: "a third-level heading" },
  { pattern: /^\s*\|/, name: "a table" },
  { pattern: /\[\^[^\]]*\]/, name: "a footnote" },
  { pattern: /\[[^\]]*\]\([^)]*\)/, name: "a link" },
  { pattern: /^\s*\d+[.)]\s/, name: "a numbered list" },
  { pattern: /^\s*[*+]\s/, name: "a non-dash bullet" },
  { pattern: /^\s+-\s/, name: "a nested bullet" },
  { pattern: /^>/, name: "a quote" },
  { pattern: /<[a-z!/]/i, name: "HTML" },
  { pattern: /`/, name: "code" },
];

// One source line is one block, so two consecutive lines stay two paragraphs.
export function parseLegalMarkdown(source: string): LegalDocument {
  let title: string | null = null;
  const blocks: LegalBlock[] = [];
  for (const [index, line] of source.split("\n").entries()) {
    if (!line.trim()) continue;
    const unsupported = UNSUPPORTED.find(({ pattern }) => pattern.test(line));
    if (unsupported) throw new Error(`Line ${index + 1} has ${unsupported.name}: ${line}`);
    if (line.startsWith("# ")) {
      if (title !== null) throw new Error(`Line ${index + 1} is a second title: ${line}`);
      title = line.slice(2).trim();
    } else if (line.startsWith("## ")) {
      blocks.push({ kind: "heading", text: line.slice(3).trim() });
    } else if (line.startsWith("- ")) {
      const last = blocks.at(-1);
      if (last?.kind === "list") last.items.push(line.slice(2).trim());
      else blocks.push({ kind: "list", items: [line.slice(2).trim()] });
    } else {
      blocks.push({ kind: "paragraph", text: line.trim() });
    }
  }
  if (title === null) throw new Error("The document has no title.");
  return { title, blocks };
}

// The approved file carries Spanish first and English after one `---` line.
export function parseBilingualLegalMarkdown(source: string): { es: LegalDocument; en: LegalDocument } {
  const parts = source.split(/^---$/m);
  if (parts.length !== 2) throw new Error(`Expected one --- separator, found ${parts.length - 1}.`);
  return { es: parseLegalMarkdown(parts[0]!), en: parseLegalMarkdown(parts[1]!) };
}
