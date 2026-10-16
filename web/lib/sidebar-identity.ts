export function identityInitials(name: string | null | undefined): string {
  const words = name?.trim().split(/\s+/).filter(Boolean) ?? [];
  return words.length ? [words[0], ...(words.length > 1 ? [words[words.length - 1]] : [])].map((word) => Array.from(word)[0]).join("").toLocaleUpperCase() : "·";
}
