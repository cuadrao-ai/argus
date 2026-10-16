export const EXPENSE_METHODS = [
  "No los llevo",
  "En una libreta o notas",
  "En Excel o Google Sheets",
  "En otra app",
  "Otra forma",
] as const;

export type ExpenseMethod = (typeof EXPENSE_METHODS)[number];

export type PersonalWaitlistInput = {
  email: string;
  expenseMethod: ExpenseMethod | null;
  wish: string | null;
  captchaToken: string;
};

export function containsSensitiveDigits(value: string): boolean {
  return /(?:\p{Nd}[\s().-]*){7}/u.test(value.normalize("NFKC"));
}

export function plainWish(value: string): string | null {
  if (containsSensitiveDigits(value)) return null;
  const plain = value
    .replace(/<(script|style)\b[^>]*>[\s\S]*?(?:<\/\1\s*>|$)/gi, "")
    .replace(/<[^>]*(?:>|$)/g, "")
    .replace(/(?:https?:\/\/|www\.)\S+/gi, "")
    .replace(/\b[\p{L}\p{N}-]+(?:\.[\p{L}\p{N}-]+)+\/?\S*/gu, "")
    .replace(/[\u0000-\u001f\u007f]/g, " ")
    .trim();
  return plain ? Array.from(plain).slice(0, 280).join("") : null;
}

export function parsePersonalWaitlist(body: unknown): PersonalWaitlistInput | null {
  if (!body || typeof body !== "object" || Array.isArray(body)) return null;
  const fields = body as Record<string, unknown>;
  const email = typeof fields.email === "string" ? fields.email.trim().toLowerCase() : "";
  if (email.length > 254 || !/^[^\s@]{1,64}@[^\s@]+\.[^\s@]{2,}$/.test(email)) return null;
  const expenseMethod = EXPENSE_METHODS.find((method) => method === fields.expenseMethod) ?? null;
  if (fields.expenseMethod && !expenseMethod) return null;
  const captchaToken = typeof fields.captchaToken === "string" ? fields.captchaToken : "";
  if (captchaToken.length > 2048) return null;
  return {
    email,
    expenseMethod,
    wish: typeof fields.wish === "string" ? plainWish(fields.wish) : null,
    captchaToken,
  };
}
