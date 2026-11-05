import { normalizeSearchText } from "@/lib/search-text";

/** The words of a text without accents or case, for matching what was typed against what is listed. */
export function foldedWords(value: string): string[] {
  const text = normalizeSearchText(value.normalize("NFD").replace(/\p{M}/gu, ""));
  return text ? text.split(" ") : [];
}
