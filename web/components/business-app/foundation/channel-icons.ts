import { EnvelopeSimple, NotePencil, UploadSimple, WhatsappLogo, type Icon } from "@phosphor-icons/react";

/**
 * The one icon for each way a document reaches the Business, wherever a channel shows:
 * a Bandeja row and its filters, the arrival dossier, and Negocio > Recepción. Monochrome in the
 * surrounding text color, never a brand color.
 */
export const CHANNEL_ICON: Record<"whatsapp" | "email" | "web" | "note", Icon> = {
  whatsapp: WhatsappLogo,
  email: EnvelopeSimple,
  web: UploadSimple,
  note: NotePencil,
};
