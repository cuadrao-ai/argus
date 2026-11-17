import type { TFunction } from "i18next";
import { z } from "zod";

/** How the server says a person reads to this viewer: by name, by email, as a member, or as a former member. */
export const personShown = z.enum(["name", "email", "member", "former"]);
export type PersonShown = z.infer<typeof personShown>;

/** A person as the server reads them for this viewer; `display_name` is set only for `name`, `email` only for `email`. */
export type PersonName = { display_name: string | null; email?: string | null; shown_as: PersonShown };

/** The words for a person: their name, their email, the member word or the former-member word, as the server says. */
export function personName(t: TFunction, person: PersonName | null | undefined): string {
  switch (person?.shown_as) {
    case "name":
      return person.display_name ?? "";
    case "email":
      return person.email ?? "";
    case "member":
      return t("business_access.member");
    default:
      return t("business.activity_feed.former_member");
  }
}
