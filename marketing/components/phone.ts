import { CONTACT_PHONE_AREA_CODES } from "../lib/contact-phone-area-codes";

export type PhoneErrorReason = "empty" | "length" | "format" | "region";

export type PhoneCheck =
  | { status: "empty" }
  | { status: "invalid"; reason: Exclude<PhoneErrorReason, "empty"> }
  | { status: "valid"; display: string };

/** Keeps what a phone number can contain, so pasted "(809) 555-0123" and stray letters both work. */
export function cleanPhoneInput(raw: string): string {
  const plus = raw.trimStart().startsWith("+") ? "+" : "";
  return plus + raw.replace(/\D/g, "");
}

/**
 * Accepts Dominican Republic and United States numbers in national or +1 form.
 */
export function checkPhone(raw: string): PhoneCheck {
  const cleaned = cleanPhoneInput(raw);
  const digits = cleaned.replace(/\D/g, "");
  if (digits === "") return { status: "empty" };
  if (cleaned.startsWith("+") && !digits.startsWith("1")) {
    return { status: "invalid", reason: "region" };
  }
  const national =
    digits.length === 10 && !cleaned.startsWith("+")
      ? digits
      : digits.length === 11 && digits.startsWith("1")
        ? digits.slice(1)
        : null;
  if (national) {
    if (!/^[2-9]\d{2}[2-9]\d{6}$/.test(national)) return { status: "invalid", reason: "format" };
    if (!CONTACT_PHONE_AREA_CODES.has(national.slice(0, 3))) return { status: "invalid", reason: "region" };
    return {
      status: "valid",
      display: `+1 ${national.slice(0, 3)} ${national.slice(3, 6)} ${national.slice(6)}`,
    };
  }
  return { status: "invalid", reason: "length" };
}
