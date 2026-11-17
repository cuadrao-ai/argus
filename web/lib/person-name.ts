import type { TFunction } from "i18next";

/** A person as the server reads them now: the profile name, else null; the email only while they hold access to the Business. */
export type PersonName = { display_name: string | null; email?: string | null };

/** The name the server gives an account the departure flow erased. */
const ERASED_NAME = "Exmiembro";

/** The person left the Business or was erased: no name and no email to show. */
export function personGone(person: PersonName | null | undefined): boolean {
  const name = person?.display_name?.trim();
  return name === ERASED_NAME || (!name && !person?.email);
}

/** The words for a person: their name, else their email, else the former-member word for someone who left or was erased. */
export function personName(t: TFunction, person: PersonName | null | undefined): string {
  if (personGone(person)) return t("business.activity_feed.former_member");
  return person?.display_name?.trim() || person?.email || "";
}
