"use client";

import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { CircleCheck, Clock, LogOut } from "lucide-react";
import { dangerConfirmButtonClass, quietButtonClass, secondaryButtonClass } from "@/components/business-app/business-ui";
import { formatBusinessName } from "@/components/business-app/business-format";
import SettingsSurface, { useSettingsStep } from "@/components/settings/SettingsSurface";
import {
  deletionEndsSession,
  requestAccountDeletion,
  type AccountDeletionNotice,
  type AccountDeletionOutcome,
} from "@/lib/account-deletion-api";
import { businessDeadlineParts } from "@/lib/business-lifecycle-api";
import { supportEmail } from "@/lib/support-email";

/**
 * Cuenta's second step: what deleting does and when it finishes, then one
 * confirmation (#1495). Cancelar is the default and takes focus; Eliminar
 * cuenta runs the deletion command. Once the command answers, the step keeps
 * that answer in place of the buttons and has no way back.
 */

type ConfirmState = "idle" | "submitting" | "error" | AccountDeletionOutcome;

const FINISHED: readonly ConfirmState[] = ["success", "in_progress", "requested"];
const FINISHED_COPY = {
  success: "settings.profile.request_deletion.success",
  in_progress: "settings.profile.request_deletion.in_progress",
  requested: "settings.profile.request_deletion.requested",
} as const;

/** The last way out, when no in-app path can delete the account. */
export function DeletionSupportLink() {
  const { t } = useTranslation();
  const subject = encodeURIComponent(t("settings.profile.request_deletion.email_subject"));
  return (
    <a className={`${quietButtonClass} text-[14px]`} href={`mailto:${supportEmail}?subject=${subject}`}>
      {t("settings.profile.request_deletion.write_support")}
    </a>
  );
}

export default function AccountDeletionConfirm({
  notices,
  profileLanguage,
  onBack,
  onAccountDeleted,
  onClose,
}: {
  /** Closed Businesses still inside their reopen window: a warning, never a block. */
  notices: AccountDeletionNotice[];
  profileLanguage: string;
  onBack: () => void;
  onAccountDeleted: () => void;
  onClose: () => void;
}) {
  const { t, i18n } = useTranslation();
  const [state, setState] = useState<ConfirmState>("idle");
  const busy = useRef(false);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const finished = FINISHED.includes(state);
  const title = t("settings.profile.delete_account", "Delete account");
  useSettingsStep(title, finished || state === "submitting" ? undefined : onBack);

  useEffect(() => {
    cancelRef.current?.focus();
  }, []);

  const submit = async () => {
    if (busy.current) return;
    busy.current = true;
    setState("submitting");
    try {
      // 202 and a post-lock 503 are in_progress; 404 (command off here) files a support ticket.
      const outcome = await requestAccountDeletion(profileLanguage);
      setState(outcome);
      if (deletionEndsSession(outcome)) onAccountDeleted();
      else busy.current = outcome === "requested";
    } catch (err) {
      console.error("Account deletion failed", err);
      setState("error");
      busy.current = false;
    }
  };

  const footer = finished ? (
    <p role="status" className="flex items-start gap-2.5 text-[14px] leading-[21px]">
      <CircleCheck className="mt-px h-[18px] w-[18px] shrink-0 text-[var(--cuadrao-green)]" aria-hidden="true" />
      {t(FINISHED_COPY[state as keyof typeof FINISHED_COPY])}
    </p>
  ) : (
    <div className="ml-auto grid w-[348px] max-w-full grid-cols-2 gap-3">
      <button ref={cancelRef} type="button" className={secondaryButtonClass} onClick={onBack} disabled={state === "submitting"}>
        {t("common.cancel", "Cancel")}
      </button>
      <button type="button" className={dangerConfirmButtonClass} onClick={() => void submit()} disabled={state === "submitting"}>
        {state === "submitting" ? t("settings.profile.request_deletion.submitting") : t("settings.profile.request_deletion.confirm", "Delete account")}
      </button>
    </div>
  );

  const muted = "text-[#56635e] dark:text-white/70";
  return (
    <SettingsSurface title={title} closeLabel={t("common.close", "Close")} onClose={onClose} footer={footer} width="sm">
      <div className="p-5" data-testid="account-deletion-confirm">
        <p className={`text-[16px] leading-6 ${muted}`}>{t("settings.profile.request_deletion.body")}</p>
        <ul className="mt-[21px] flex flex-col gap-[13px]">
          <li className="flex items-start gap-3 text-[16px] leading-6">
            <LogOut className={`mt-[3px] h-[18px] w-[18px] shrink-0 ${muted}`} aria-hidden="true" />
            <span>{t("settings.profile.request_deletion.signs_out_now")}</span>
          </li>
          <li className="flex items-start gap-3 text-[16px] leading-6">
            <Clock className={`mt-[3px] h-[18px] w-[18px] shrink-0 ${muted}`} aria-hidden="true" />
            <span>{t("settings.profile.request_deletion.finishes_later")}</span>
          </li>
        </ul>
        {/* The server names the date; the web only formats it for the reader. */}
        {notices.map((notice) => (
          <p key={notice.business_id} className={`mt-[13px] text-[14px] leading-relaxed ${muted}`} data-testid="delete-account-closed-business">
            {t("business.lifecycle.deletion.closed_warning", { businessName: formatBusinessName(notice.business_name, t("business.overview.title", "My business")), ...businessDeadlineParts(notice.purge_at, i18n.resolvedLanguage ?? "es-419") })}
          </p>
        ))}
        {state === "error" || state === "unavailable" ? (
          <p role="alert" className="mt-3 text-[14px] leading-relaxed text-[#9e2f39] dark:text-[#ec9aa0]">
            {t(state === "error" ? "settings.profile.request_deletion.error" : "settings.profile.request_deletion.unavailable")}
          </p>
        ) : null}
        {state === "unavailable" ? <DeletionSupportLink /> : null}
      </div>
    </SettingsSurface>
  );
}
