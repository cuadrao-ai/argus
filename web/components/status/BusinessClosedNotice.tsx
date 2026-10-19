"use client";

import { useState } from "react";
import { useTranslation } from "react-i18next";

import { leaveSession } from "@/lib/logout-flow";
import { logoutFromApi } from "@/lib/argus-api";
import { CUADRAO_ADMIN_EMAIL } from "@/lib/failure-screen";
import { businessPilotEnabled } from "@/lib/private-alpha-flags";

function closedBody(body: string) {
  const at = body.indexOf(CUADRAO_ADMIN_EMAIL);
  if (at < 0) return body;
  return (
    <>
      {body.slice(0, at)}
      <a
        className="font-medium underline decoration-black/25 underline-offset-4 dark:decoration-white/30"
        href={`mailto:${CUADRAO_ADMIN_EMAIL}`}
      >
        {CUADRAO_ADMIN_EMAIL}
      </a>
      {body.slice(at + CUADRAO_ADMIN_EMAIL.length)}
    </>
  );
}

export function BusinessClosedNotice({
  navigate = (href) => window.location.assign(href),
}: {
  navigate?: (href: string) => void;
} = {}) {
  const { t } = useTranslation();
  const [signOutFailed, setSignOutFailed] = useState(false);
  const signOut = () => {
    setSignOutFailed(false);
    void leaveSession({
      boundary: { beginConversion() {}, finishConversion() {} },
      currentUserId: null,
      signOut: () => logoutFromApi(),
      clearLocalState() {},
      navigate,
      onFailed() {
        setSignOutFailed(true);
      },
      businessBuild: businessPilotEnabled,
    });
  };
  return (
    <div data-testid="business-home-closed" className="w-full max-w-sm text-center">
      <h2 className="text-[16px] font-medium tracking-wide">{t("auth.business_unavailable.title")}</h2>
      <p className="mt-3 text-[16px] tracking-wide">{closedBody(String(t("auth.business_unavailable.body")))}</p>
      <button
        type="button"
        className="font-display mt-6 flex w-full items-center justify-center rounded-[9999px] bg-black px-[32px] py-[14px] text-[16px] font-medium !text-[var(--cuadrao-cream)] transition-opacity hover:opacity-85 focus:outline-none focus-visible:ring-[0.125rem] focus-visible:ring-black dark:bg-white dark:focus-visible:ring-white"
        onClick={signOut}
      >
        {t("auth.business_unavailable.sign_out")}
      </button>
      {signOutFailed ? <p className="mt-3" role="alert">{t("settings.logout_error")}</p> : null}
    </div>
  );
}
