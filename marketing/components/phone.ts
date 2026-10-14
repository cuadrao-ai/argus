export type PhoneCheck =
  | { status: "empty" }
  | { status: "invalid" }
  | { status: "valid"; display: string };

/** Keeps what a phone number can contain, so pasted "(809) 555-0123" and stray letters both work. */
export function cleanPhoneInput(raw: string): string {
  const plus = raw.trimStart().startsWith("+") ? "+" : "";
  return plus + raw.replace(/\D/g, "");
}

/**
 * A 10-digit number, or 11 starting with 1, is a North American number, which includes
 * the Dominican 809, 829 and 849 codes. Anything else needs a leading + and 8 to 15 digits.
 */
export function checkPhone(raw: string): PhoneCheck {
  const cleaned = cleanPhoneInput(raw);
  const digits = cleaned.replace(/\D/g, "");
  if (digits === "") return { status: "empty" };
  const national =
    digits.length === 10 && !cleaned.startsWith("+")
      ? digits
      : digits.length === 11 && digits.startsWith("1")
        ? digits.slice(1)
        : null;
  if (national) {
    if (!/^[2-9]\d{2}[2-9]\d{6}$/.test(national)) return { status: "invalid" };
    return {
      status: "valid",
      display: `+1 ${national.slice(0, 3)} ${national.slice(3, 6)} ${national.slice(6)}`,
    };
  }
  if (!cleaned.startsWith("+") || digits.length < 8 || digits.length > 15) {
    return { status: "invalid" };
  }
  if (digits.startsWith("1")) return { status: "invalid" };
  return { status: "valid", display: `+${digits}` };
}
