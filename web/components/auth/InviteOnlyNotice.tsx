"use client";

import { useTranslation } from "react-i18next";
import { contactPageHref } from "@/lib/account-access";

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
