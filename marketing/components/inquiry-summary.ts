export type InquiryRole = "owner" | "accountant" | "other";
export type InquiryChannel = "email" | "whatsapp";

export type InquiryProfile = {
  role: InquiryRole | "";
  channel: InquiryChannel | "";
  phone: string;
  source: string;
  pilot: boolean;
};

export const EMPTY_PROFILE: InquiryProfile = {
  role: "",
  channel: "",
  phone: "",
  source: "",
  pilot: false,
};

export const PHONE_MAX = 24;
export const SOURCE_MAX = 100;
export const NOTE_MAX = 700;

const ROLE: Record<InquiryRole, string> = {
  owner: "dueño/a de un negocio",
  accountant: "contador/a",
  other: "otro",
};
const CHANNEL: Record<InquiryChannel, string> = {
  email: "correo",
  whatsapp: "WhatsApp",
};

/** The founder reads the inquiry in Spanish, whichever language the visitor used. */
export function buildInquiryMessage(profile: InquiryProfile, note: string): string {
  const lines: string[] = [];
  if (profile.role) lines.push(`Soy: ${ROLE[profile.role]}`);
  if (profile.channel) {
    const phone = profile.channel === "whatsapp" ? profile.phone.trim() : "";
    lines.push(`Prefiere: ${CHANNEL[profile.channel]}${phone ? ` ${phone}` : ""}`);
  }
  const source = profile.source.trim();
  if (source) lines.push(`Nos conoció por: ${source}`);
  if (profile.pilot) lines.push("Piloto: quiere ver el prototipo y probarlo");
  const text = note.trim();
  return [lines.join("\n"), text].filter(Boolean).join("\n\n");
}
