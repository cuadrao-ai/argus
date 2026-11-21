import type { TFunction } from "i18next";
import { personName, type PersonName } from "./person-name";

/** Who brought a Bandeja row in, as the server says; `kind` names the one field that is set, and `id` is the same for the same sender on every row. */
export type SentBy = { id: string; kind: "member" | "email" | "whatsapp"; person?: PersonName | null; address?: string | null; phone_last4?: string | null };

/** The words for a sender: the member as `personName` reads them, the email address, or WhatsApp with the number's last digits. */
export function sentByName(t: TFunction, sender: SentBy): string {
  if (sender.kind === "whatsapp") return t("business.reception_preview.sent_by_whatsapp", { last4: sender.phone_last4 ?? "" });
  return sender.kind === "email" ? sender.address ?? "" : personName(t, sender.person);
}
