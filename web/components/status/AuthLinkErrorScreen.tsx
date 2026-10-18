"use client";

import { useTranslation } from "react-i18next";

import { BrandedStatusScreen } from "@/components/status/BrandedStatusScreen";
import { useSessionEntry } from "@/components/status/useCuadraoEntryHref";
import { requestHrefFor, type AuthLinkErrorView } from "@/lib/auth-link-error";

export function AuthLinkErrorScreen({
  view,
  homeHref,
}: {
  view: AuthLinkErrorView;
  homeHref?: string;
}) {
  const { t } = useTranslation();
  const session = useSessionEntry();
  const title = t("auth.screen.link_expired_title", "This link expired or was already used.");

  if (view.kind === "invite") {
    return (
      <BrandedStatusScreen
        title={title}
        detail={t(
          "auth.screen.invite_line",
          "Ask the person who invited you to send another invitation.",
        )}
        actionLabel={t("auth.screen.go_to_cuadrao", "Go to Cuadrao")}
        actionHref={homeHref ?? session.homeHref}
      />
    );
  }

  const email = view.email ?? (session.email || null);
  return (
    <BrandedStatusScreen
      title={title}
      actionLabel={t("auth.screen.request_new_link", "Request a new link")}
      actionHref={requestHrefFor(view.flow, email)}
    />
  );
}
