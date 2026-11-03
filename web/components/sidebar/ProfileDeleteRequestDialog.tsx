"use client";

import { withViewportPortal } from "@/components/ui/withViewportPortal";

import { useCallback, useId, useRef, type RefObject } from "react";
import { dangerConfirmButtonClass, quietButtonClass, secondaryButtonClass } from "@/components/business-app/business-ui";
import type { AccountDeletionEligibility } from "@/lib/account-deletion-api";
import { previewLifecycleControls } from "@/lib/account-deletion-preview";
import { useAccountDeletionEligibility, type AccountDeletionCheck } from "@/lib/use-account-deletion-eligibility";
import { businessDeadlineParts, businessLifecycleHref } from "@/lib/business-lifecycle-api";
import { ReferenceCode } from "@/components/status/ReferenceCode";
import { businessLifecycleControlsEnabled } from "@/lib/private-alpha-flags";
import { X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useConversationSurface } from "@/components/chat/ChatWorkspace";
import { useModalSurface } from "../layout/useModalSurface";

/**
 * In-app account deletion (Lane 6), lifted out of the profile menu.
 *
 * Confirming runs the deletion command. Once it succeeds, or the account is
 * locked while it finishes (in_progress), the session is dead, so the browser
 * signs out on that result (the one logout call) and this dialog stays as
 * the signed-out confirmation; Done only cleans up and leaves. When the
 * command is switched off on this server (404), support gets a ticket instead
 * (requested), or by email if that fails too, so the confirmation never says
 * the account is deleted "now".
 *
 * Before it offers Eliminar it asks the server whether this account may be
 * deleted, and renders only that answer: the web never works out ownership.
 * An open Business the person owns blocks it, named one by one.
 *
 * It portals to the body, outside the menu it opens from, so the menu's focus
 * trap never contained it and system back dismissed the menu or the drawer
 * underneath instead of this dialog. Owning its own registration is the only
 * way a portaled `aria-modal` surface gets that right.
 */

export type DeleteRequestState =
  | "idle"
  | "submitting"
  | "success"
  | "in_progress"
  | "requested"
  | "error"
  | "unavailable";

function ProfileDeleteRequestDialogSurface({
  state,
  supportMailto,
  onClose,
  onSubmit,
  returnFocusRef,
  check,
  readEligibility,
  lifecycleControls = previewLifecycleControls() ?? businessLifecycleControlsEnabled(),
}: {
  state: DeleteRequestState;
  supportMailto: string;
  onClose: () => void;
  onSubmit: () => void | Promise<void>;
  returnFocusRef?: RefObject<HTMLElement | null>;
  /** The answer the opener already holds, so the alert opens with it in place. */
  check?: AccountDeletionCheck;
  /** Without a check, the alert reads the server's delete rule itself; a test passes its own. */
  readEligibility?: () => Promise<AccountDeletionEligibility>;
  /** Whether Transferir and Cerrar exist to link to. */
  lifecycleControls?: boolean;
}) {
  const { t, i18n } = useTranslation();
  const isBusiness = useConversationSurface() === "business";
  const ownCheck = useAccountDeletionEligibility(!check, readEligibility);
  const { answer: eligibility, error: readError, refresh } = check ?? ownCheck;
  // Off here (404) keeps the old path: the button files a support request.
  const allowed = eligibility !== null && ("off" in eligibility || eligibility.allowed);
  const blockers = eligibility && "blockers" in eligibility && !eligibility.allowed ? eligibility.blockers : [];
  const ownedBusinesses = blockers.flatMap(blocker => blocker.kind === "business_owner" ? [blocker] : []);
  const notAllowed = blockers.length > 0 && ownedBusinesses.length === 0;
  const notices = eligibility && "notices" in eligibility ? eligibility.notices : [];
  const overlayId = useId();
  const panelRef = useRef<HTMLDivElement>(null);

  // A submission in flight owns the dialog until it settles. This is answered
  // before the history entry is spent, not inside onDismiss, so a refused press
  // leaves the entry intact and back still works once the request lands.
  const canDismiss = useCallback(() => state !== "submitting", [state]);

  useModalSurface({
    isOpen: true,
    overlayId,
    // The panel, not the full-screen wrapper. The wrapper's first focusable
    // child is the transparent backdrop, so trapping there opened keyboard
    // users on an undisclosed control where Enter dismissed the dialog.
    containerRef: panelRef,
    onDismiss: onClose,
    canDismiss,
    returnFocusRef,
    // Routed to the topmost layer, so opening this from a submenu no longer
    // depends on some other component happening to answer for it.
    onEscape: () => {
      if (canDismiss()) onClose();
    },
  });

  const bodyText = "text-[14px] leading-relaxed text-[#56635e] dark:text-white/70";
  const supportLink = (
    <a className={`${quietButtonClass} text-[14px]`} href={supportMailto}>
      {t("settings.profile.request_deletion.email_fallback", "Email support")}
    </a>
  );

  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/40 p-4 dark:bg-black/60">
      <button
        tabIndex={-1}
        className="absolute inset-0"
        onClick={() => {
          if (state !== "submitting") {
            onClose();
          }
        }}
        aria-label={t(
          "settings.profile.request_deletion.close",
          "Close account deletion",
        )}
      />
      <div
        ref={panelRef}
        className="relative max-h-[calc(100dvh-2rem)] w-full max-w-[420px] overflow-y-auto overscroll-contain rounded-surface border border-[#DCE0DA] bg-white p-6 text-[#172b26] dark:border-white/10 dark:bg-[#1b1d20] dark:text-white"
        role="dialog"
        aria-modal="true"
        aria-labelledby="argus-delete-request-title"
        data-testid="delete-account-alert"
      >
        <h3
          id="argus-delete-request-title"
          className="mb-[13px] font-display text-[21px] font-medium"
        >
          {t(
            "settings.profile.request_deletion.title",
            "Delete your account?",
          )}
        </h3>

        {state === "success" || state === "in_progress" || state === "requested" ? (
          <>
            <p
              className={bodyText}
              data-testid={`argus-delete-account-${state}`}
            >
              {state === "success"
                ? t(
                    "settings.profile.request_deletion.success",
                    "Your account is deleted. You're signed out.",
                  )
                : state === "in_progress"
                  ? t(
                      "settings.profile.request_deletion.in_progress",
                      "Your account is being deleted. You're signed out now, and we'll finish removing it within a few days. You don't need to do anything.",
                    )
                  : t(
                      "settings.profile.request_deletion.requested",
                      "Request sent. Support will delete your account and follow up by email.",
                    )}
            </p>
            <div className="mt-[21px] flex justify-end">
              <button type="button" onClick={() => onClose()} className={secondaryButtonClass}>
                {t("common.done", "Done")}
              </button>
            </div>
          </>
        ) : (
          <>
            {eligibility === null ? (
              <div className="space-y-2" data-testid="delete-account-checking">
                <p role={readError ? "alert" : "status"} className={bodyText}>
                  {/* Business names its businesses; Personal stays neutral. */}
                  {isBusiness
                    ? t(readError ? "business.lifecycle.deletion.failed" : "business.lifecycle.deletion.checking")
                    : t(readError ? "settings.profile.request_deletion.check_failed" : "settings.profile.request_deletion.checking")}
                </p>
                {readError?.reference ? <ReferenceCode reference={readError.reference} /> : null}
                {readError ? <button type="button" className={quietButtonClass} onClick={refresh}>{t("common.retry")}</button> : null}
              </div>
            ) : ownedBusinesses.length ? (
              <div data-testid="delete-account-business-owner">
                <p className={bodyText}>
                  {t("settings.profile.request_deletion.business_owner", "Before you delete your account, each Business you own needs a new owner or must be closed.")}
                </p>
                <ul className="mt-[13px] divide-y divide-[#DCE0DA] rounded-item border border-[#DCE0DA] dark:divide-white/10 dark:border-white/10">
                  {ownedBusinesses.map(business => (
                    <li key={business.business_id} className="flex flex-wrap items-center justify-between gap-x-3 px-3 py-1">
                      <span className="py-2 text-[16px] font-medium">{business.business_name}</span>
                      {lifecycleControls ? (
                        <span className="flex gap-3">
                          <a className={`${quietButtonClass} text-[14px]`} href={businessLifecycleHref(business.business_id, "transfer")}>{t("business.lifecycle.transfer.title")}</a>
                          <a className={`${quietButtonClass} text-[14px]`} href={businessLifecycleHref(business.business_id, "close")}>{t("business.lifecycle.close.action")}</a>
                        </span>
                      ) : null}
                    </li>
                  ))}
                </ul>
                {lifecycleControls ? null : <p className="mt-2">{supportLink}</p>}
              </div>
            ) : notAllowed ? (
              <p className={bodyText} data-testid="delete-account-not-allowed">
                {t(
                  "settings.profile.request_deletion.unavailable",
                  "Deleting in the app isn't available here yet. Support can delete your account for you.",
                )}{" "}
                {supportLink}
              </p>
            ) : (
              <>
                <p className={bodyText} data-testid="delete-account-allowed">
                  {isBusiness
                    ? t("settings.profile.request_deletion.body", "We delete your account and your personal data. This can't be undone.")
                    : t("settings.profile.request_deletion.body_personal", "Your account and your data will be deleted, and this can't be undone. Households you run pass to the longest-standing member, or close if you're the only one.")}
                </p>
                {/* The personal app's shared plans; Business has none. */}
                {isBusiness ? null : <p
                  className={`mt-2 ${bodyText}`}
                  data-testid="argus-delete-account-shared-plans"
                >
                  {t(
                    "settings.profile.request_deletion.shared_plans",
                    "In plans you share, your amounts stay so everyone else's numbers still add up, but without your name: you'll show as \"Former member.\" Your receipts and notes are deleted. Anything you owe or are owed is closed in the app, not marked as paid. Plans you created pass to whoever has been in each one longest, except shared debt plans, which are closed and stay view-only.",
                  )}
                </p>}
                {/* The server names the date; the web only formats it for the reader. */}
                {notices.map(notice => (
                  <p key={notice.business_id} className={`mt-[13px] ${bodyText}`} data-testid="delete-account-closed-business">
                    {t("business.lifecycle.deletion.closed_warning", { businessName: notice.business_name, ...businessDeadlineParts(notice.purge_at, i18n.resolvedLanguage ?? "es-419") })}
                  </p>
                ))}
              </>
            )}
            {state === "error" && (
              <p role="alert" className="mt-3 text-[14px] leading-relaxed text-[#9e2f39] dark:text-[#ec9aa0]">
                {t(
                  "settings.profile.request_deletion.error",
                  "We couldn't delete your account just now. Try again.",
                )}{" "}
                {supportLink}
              </p>
            )}
            {state === "unavailable" && (
              <p role="alert" className="mt-3 text-[14px] leading-relaxed text-[#9e2f39] dark:text-[#ec9aa0]">
                {t(
                  "settings.profile.request_deletion.unavailable",
                  "Deleting in the app isn't available here yet. Support can delete your account for you.",
                )}{" "}
                {supportLink}
              </p>
            )}
            <div className="mt-[21px] flex justify-end gap-2">
              <button
                type="button"
                onClick={() => onClose()}
                disabled={state === "submitting"}
                className={secondaryButtonClass}
              >
                {t("common.cancel", "Cancel")}
              </button>
              {/* Only once the server has said yes: never while it is still asking. */}
              {allowed ? (
                <button
                  type="button"
                  data-testid="delete-account-confirm"
                  onClick={() => void onSubmit()}
                  disabled={state === "submitting" || state === "unavailable"}
                  className={`${dangerConfirmButtonClass} disabled:cursor-wait disabled:opacity-60`}
                >
                  {state === "submitting"
                    ? t(
                        "settings.profile.request_deletion.submitting",
                        "Deleting...",
                      )
                    : t(
                        "settings.profile.request_deletion.confirm",
                        "Delete account",
                      )}
                </button>
              ) : null}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

export default withViewportPortal(ProfileDeleteRequestDialogSurface);
