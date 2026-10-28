"use client";

import { useTranslation } from "react-i18next";

import { BrandedStatusScreen } from "@/components/status/BrandedStatusScreen";
import { ReferenceCode } from "@/components/status/ReferenceCode";
import { useSessionEntry } from "@/components/status/useCuadraoEntryHref";
import { requestHrefFor, type AuthLinkErrorView } from "@/lib/auth-link-error";

export function AuthLinkErrorScreen({
  view,
  reference,
  homeHref,
}: {
  view: AuthLinkErrorView;
  /** The id support finds in the server logs when the confirm route refused the link. */
  reference: string;
  homeHref?: string;
}) {
  const { t } = useTranslation();
  const session = useSessionEntry();
  const expired = view.problem === "expired";
  const title = expired
    ? t("auth.screen.link_expired_title", "This link expired or was already used.")
    : t("auth.confirm.error_title", "This link didn’t work");
  const detail = view.problem === "malformed"
    ? t("auth.confirm.malformed_body", "The link is missing a part or was copied wrong. Open it from the email or request a new one.")
    : view.problem === "rejected"
      ? t("auth.confirm.rejected_body", "We could not verify this link. Request a new one and try again.")
      : view.kind === "invite"
        ? t("auth.screen.invite_line", "Ask the person who invited you to send another invitation.")
        : undefined;
  const code = <ReferenceCode reference={reference} />;

  if (view.kind === "invite") {
    return (
      <BrandedStatusScreen
        title={title}
        detail={detail}
        reference={code}
        actionLabel={t("auth.screen.go_to_cuadrao", "Go to Cuadrao")}
        actionHref={homeHref ?? session.homeHref}
      />
    );
  }

  const email = view.email ?? (session.email || null);
  return (
    <BrandedStatusScreen
      title={title}
      detail={detail}
      reference={code}
      actionLabel={t("auth.screen.request_new_link", "Request a new link")}
      actionHref={requestHrefFor(view.flow, email)}
    />
  );
}
