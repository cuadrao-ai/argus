"use client";

import { useState } from "react";
import { useTranslation } from "react-i18next";

import { CuadraoLockup } from "@/components/CuadraoLockup";
import { primaryButtonClass } from "@/components/business-app/business-ui";
import { FOCUS_RING } from "@/components/business-app/foundation/presentation";
import { leaveSession } from "@/lib/logout-flow";
import { logoutFromApi } from "@/lib/argus-api";
import { businessPilotEnabled } from "@/lib/private-alpha-flags";
import { supportEmail } from "@/lib/support-email";

function closedBody(body: string) {
  const at = body.indexOf(supportEmail);
  if (at < 0) return body;
  return (
    <>
      {body.slice(0, at)}
      <a
        className={`rounded-mark font-medium underline decoration-black/25 underline-offset-4 dark:decoration-white/30 ${FOCUS_RING}`}
        href={`mailto:${supportEmail}`}
      >
        {supportEmail}
      </a>
      {body.slice(at + supportEmail.length)}
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
    <div data-testid="business-home-closed" className="w-full max-w-md text-center text-[var(--segment-text-strong)]">
      <h1 className="mb-[34px] select-none" aria-label="Cuadrao">
        <CuadraoLockup width={268} className="max-w-full align-top" />
      </h1>
      <h2 className="font-display text-[26px] font-medium leading-tight tracking-tight">{t("auth.business_unavailable.title")}</h2>
      <p className="mt-[13px] text-[16px] leading-relaxed text-[var(--segment-text)]">{closedBody(String(t("auth.business_unavailable.body", { supportEmail })))}</p>
      <button
        type="button"
        className={`${primaryButtonClass} mt-[21px] w-full`}
        onClick={signOut}
      >
        {t("auth.business_unavailable.sign_out")}
      </button>
      {signOutFailed ? <p className="mt-[13px] text-[16px] leading-relaxed" role="alert">{t("settings.logout_error")}</p> : null}
    </div>
  );
}
