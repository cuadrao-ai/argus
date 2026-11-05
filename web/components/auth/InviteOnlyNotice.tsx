"use client";

import { useTranslation } from "react-i18next";

const CONTACT_PAGE_URL = {
  "es-419": "https://cuadrao.ai/contacto",
  en: "https://cuadrao.ai/en/contact",
} as const;

export function contactPageHref(language: string | undefined): string {
  return language?.toLowerCase().startsWith("en")
    ? CONTACT_PAGE_URL.en
    : CONTACT_PAGE_URL["es-419"];
}

export function InviteOnlyNotice({ linkClassName }: { linkClassName: string }) {
  const { t, i18n } = useTranslation();
  return (
    <>
      {t("auth.invite_only.body", "Cuadrao is in early access, by invitation only.")}{" "}
      <a href={contactPageHref(i18n.resolvedLanguage ?? i18n.language)} className={linkClassName}>
        {t("auth.invite_only.request_access", "Request access")}
      </a>
    </>
  );
}
