"use client";

import { useEffect, useRef, useState, type CSSProperties, type MouseEvent } from "react";
import { useTranslation } from "react-i18next";
import { ArrowUpRight, ChevronDown, ChevronRight, ChevronUp, CircleAlert, CircleCheck } from "lucide-react";
import { dangerButtonClass, quietButtonClass, secondaryButtonClass } from "@/components/business-app/business-ui";
import { formatBusinessName } from "@/components/business-app/business-format";
import { useConversationSurface } from "@/components/chat/ChatWorkspace";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import AccountDeletionConfirm from "@/components/settings/AccountDeletionConfirm";
import SettingsSurface from "@/components/settings/SettingsSurface";
import ProfileAvatar from "@/components/sidebar/ProfileAvatar";
import { ReferenceCode } from "@/components/status/ReferenceCode";
import { requestSupportDeletion, type AccountDeletionBlocker, type AccountDeletionNotice } from "@/lib/account-deletion-api";
import { previewLifecycleControls, previewSupportRequest } from "@/lib/account-deletion-preview";
import type { ApiUser } from "@/lib/argus-api";
import { setChosenGrant } from "@/lib/business-grant";
import { getOwnedBusinessSpaces } from "@/lib/business-lifecycle-api";
import { businessLifecycleControlsEnabled } from "@/lib/private-alpha-flags";
import { useAccountDeletionEligibility, type AccountDeletionCheck } from "@/lib/use-account-deletion-eligibility";

/**
 * Ajustes › Cuenta (#1495): who is signed in, Seguridad, and Eliminar cuenta
 * last. Opening it asks the server whether this account may be deleted
 * (`GET /account/deletion`) and draws only that answer: an open Business the
 * person owns blocks it, and each one links to its own Negocio settings.
 * Confirming happens in the pane, as a second step, never in an alert.
 */

/** What Ajustes hands Cuenta: the account's look and the ways out of the window. */
export type AccountActions = {
  avatar: { className: string; style: CSSProperties | undefined };
  /** The deletion command's language, as the account menu reads it. */
  profileLanguage: string;
  onLogout: () => void;
  /** Closes Ajustes and goes to `href`. */
  onLeave: (href: string) => void;
  /** The account is gone or locked: sign out now and keep Cuenta up. */
  onAccountDeleted: () => void;
};

/** Cuenta draws through SettingsSurface, so it needs the panel's close. */
type AccountSettingsProps = AccountActions & {
  profile: ApiUser | null;
  onClose: () => void;
  /** Whether Transferir and Cerrar exist in Negocio; without them support is the way out. */
  lifecycleControls?: boolean;
};

type OwnedBusiness = Extract<AccountDeletionBlocker, { kind: "business_owner" }>;

/** The server's answer, as the section draws it. */
type DeletionView =
  | { kind: "loading" }
  | { kind: "failed"; reference: string | null }
  | { kind: "clear"; notices: AccountDeletionNotice[] }
  | { kind: "blocked"; businesses: OwnedBusiness[] }
  | { kind: "not_allowed" };

function deletionView({ answer, error }: AccountDeletionCheck): DeletionView {
  if (error) return { kind: "failed", reference: error.reference };
  if (!answer) return { kind: "loading" };
  // Off here (404): the command files a support ticket, so Eliminar cuenta stays.
  if ("off" in answer) return { kind: "clear", notices: [] };
  if (answer.allowed) return { kind: "clear", notices: answer.notices };
  const businesses = answer.blockers.flatMap((blocker) => (blocker.kind === "business_owner" ? [blocker] : []));
  return businesses.length ? { kind: "blocked", businesses } : { kind: "not_allowed" };
}

const NEGOCIO_HREF = "/biz?view=business&tab=datos";
const VISIBLE_ROWS = 3;
const muted = "text-[#56635e] dark:text-white/70";
const iconMuted = "text-[#56635e] dark:text-white/60";
const group = "overflow-hidden rounded-surface bg-[#F7F5EE] dark:bg-[#1f2225]";
const divided = "relative before:absolute before:left-4 before:right-0 before:top-0 before:border-t before:border-[#172b26]/12 dark:before:border-white/10";
const rowBase =
  "flex min-h-11 w-full items-center gap-3 pl-4 pr-3.5 text-left text-[16px] transition-colors hover:bg-black/[0.04] active:bg-black/[0.08] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-[var(--cuadrao-green)] dark:hover:bg-white/[0.05] dark:active:bg-white/10";
const rowClass = `${rowBase} text-[#172b26] dark:text-white`;
const headingClass = "text-[16px] font-medium leading-6 text-[#9e2f39] dark:text-[#ec9aa0]";

function leaveWith(onLeave: (href: string) => void) {
  return (event: MouseEvent<HTMLAnchorElement>) => {
    event.preventDefault();
    onLeave(event.currentTarget.getAttribute("href") ?? "");
  };
}

export default function AccountSettings({
  profile,
  avatar,
  profileLanguage,
  onLogout,
  onLeave,
  onAccountDeleted,
  onClose,
  lifecycleControls = previewLifecycleControls() ?? businessLifecycleControlsEnabled(),
}: AccountSettingsProps) {
  const { t } = useTranslation();
  const { isBelowDesktop } = useResponsiveLayout();
  const check = useAccountDeletionEligibility();
  const view = deletionView(check);
  const [confirming, setConfirming] = useState(false);
  const deleteRef = useRef<HTMLButtonElement>(null);
  const returning = useRef(false);

  useEffect(() => {
    if (confirming || !returning.current) return;
    returning.current = false;
    deleteRef.current?.focus();
  }, [confirming]);

  if (confirming) {
    return (
      <AccountDeletionConfirm
        notices={view.kind === "clear" ? view.notices : []}
        profileLanguage={profileLanguage}
        onBack={() => {
          returning.current = true;
          setConfirming(false);
        }}
        onAccountDeleted={onAccountDeleted}
        onClose={onClose}
      />
    );
  }

  return (
    <SettingsSurface title={t("settings.account.title")} closeLabel={t("common.close", "Close")} onClose={onClose} width="sm">
      <div className="flex flex-col gap-6 p-5" data-testid="account-settings">
        <div className={`flex gap-4 rounded-surface bg-[#F7F5EE] p-4 dark:bg-[#1f2225] ${isBelowDesktop ? "flex-col items-stretch gap-[13px]" : "items-center"}`}>
          <div className="flex min-w-0 flex-1 items-center gap-4">
            <ProfileAvatar profile={profile} className={avatar.className} style={avatar.style} />
            <div className="min-w-0 flex-1">
              <p className="truncate text-[16px] font-medium leading-6">{profile?.display_name || t("settings.profile.default_user", "User")}</p>
              <p className={`truncate text-[14px] leading-5 ${muted}`}>{profile?.email ?? ""}</p>
            </div>
          </div>
          <button type="button" className={secondaryButtonClass} onClick={onLogout}>
            {t("settings.logout", "Log out")}
          </button>
        </div>

        <ul className={group}>
          <li>
            <a href="/account/security" onClick={leaveWith(onLeave)} className={`${rowClass} min-h-16 py-2.5`}>
              <span className="min-w-0 flex-1">
                <span className="block text-[16px] font-medium leading-6">{t("settings.data.security", "Security")}</span>
                <span className={`mt-0.5 block text-[14px] leading-5 ${muted}`}>{t("account_security.description")}</span>
              </span>
              <ArrowUpRight className={`h-[18px] w-[18px] shrink-0 ${iconMuted}`} aria-hidden="true" />
            </a>
          </li>
        </ul>

        <DeletionSection
          view={view}
          onRetry={check.refresh}
          lifecycleControls={lifecycleControls}
          fullWidthAction={isBelowDesktop}
          deleteRef={deleteRef}
          onDelete={() => setConfirming(true)}
          onLeave={onLeave}
        />
      </div>
    </SettingsSurface>
  );
}

function DeletionSection({
  view,
  onRetry,
  lifecycleControls,
  fullWidthAction,
  deleteRef,
  onDelete,
  onLeave,
}: {
  view: DeletionView;
  onRetry: () => void;
  lifecycleControls: boolean;
  fullWidthAction: boolean;
  deleteRef: React.RefObject<HTMLButtonElement | null>;
  onDelete: () => void;
  onLeave: (href: string) => void;
}) {
  const { t } = useTranslation();
  const isBusiness = useConversationSurface() === "business";
  const heading = <h4 id="account-deletion-heading" className={headingClass}>{t("settings.profile.delete_account", "Delete account")}</h4>;

  if (view.kind === "blocked") {
    return (
      <section aria-labelledby="account-deletion-heading">
        <div className="flex items-baseline justify-between gap-3 px-4">
          {heading}
          <p data-testid="account-deletion-pending" className={`flex items-baseline gap-2 whitespace-nowrap text-[14px] leading-5 ${muted}`}>
            <CircleAlert className="h-4 w-4 self-center" aria-hidden="true" />
            {t("settings.profile.request_deletion.pending", { count: view.businesses.length })}
          </p>
        </div>
        <p className={`mt-0.5 px-4 text-[14px] leading-5 ${muted}`}>{t("settings.profile.request_deletion.business_owner")}</p>
        <OwnedBusinesses businesses={view.businesses} onLeave={onLeave} />
        {lifecycleControls ? null : <SupportRequest fullWidth={fullWidthAction} />}
      </section>
    );
  }

  return (
    <section aria-labelledby="account-deletion-heading" aria-busy={view.kind === "loading" || undefined} className="px-4">
      {heading}
      {view.kind === "clear" ? (
        <div className="mt-0.5 flex items-center gap-3">
          <p className={`min-w-0 flex-1 text-[14px] leading-5 ${muted}`}>{t("settings.profile.delete_account_note")}</p>
          <button ref={deleteRef} type="button" className={dangerButtonClass} onClick={onDelete}>
            {t("settings.profile.request_deletion.confirm", "Delete account")}
          </button>
        </div>
      ) : view.kind === "failed" ? (
        <div className="mt-0.5 space-y-2">
          <p role="alert" className={`text-[14px] leading-5 ${muted}`}>
            {/* Business names its businesses; outside one the line stays neutral. */}
            {isBusiness ? t("business.lifecycle.deletion.failed") : t("settings.profile.request_deletion.check_failed")}
          </p>
          {view.reference ? <ReferenceCode reference={view.reference} /> : null}
          <button type="button" className={quietButtonClass} onClick={onRetry}>{t("common.retry")}</button>
        </div>
      ) : view.kind === "not_allowed" ? (
        <p className={`mt-0.5 text-[14px] leading-5 ${muted}`}>{t("settings.profile.request_deletion.unavailable")}</p>
      ) : null}
    </section>
  );
}

function OwnedBusinesses({ businesses, onLeave }: { businesses: OwnedBusiness[]; onLeave: (href: string) => void }) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const [openFailed, setOpenFailed] = useState(false);
  const opening = useRef(false);
  const shown = expanded ? businesses : businesses.slice(0, VISIBLE_ROWS);
  const hasMore = businesses.length > VISIBLE_ROWS;

  // /biz has no Business in its address: choose this one first, as the lifecycle entry does.
  const open = async (event: MouseEvent<HTMLAnchorElement>, businessId: string) => {
    event.preventDefault();
    if (opening.current) return;
    opening.current = true;
    setOpenFailed(false);
    try {
      const grant = (await getOwnedBusinessSpaces()).find((space) => space.space_id === businessId)?.grant_id;
      if (!grant) throw new Error("business_unavailable");
      setChosenGrant(grant);
      onLeave(NEGOCIO_HREF);
    } catch {
      setOpenFailed(true);
    } finally {
      opening.current = false;
    }
  };

  return (
    <>
      <ul id="account-owned-businesses" className={`mt-3 ${group}`}>
        {shown.map((business, index) => (
          <li key={business.business_id} className={index > 0 ? divided : undefined}>
            <a href={NEGOCIO_HREF} data-testid="account-owned-business" onClick={(event) => void open(event, business.business_id)} className={rowClass}>
              <span className="min-w-0 flex-1 truncate">{formatBusinessName(business.business_name, t("business.overview.title", "My business"))}</span>
              <ChevronRight className={`h-[18px] w-[18px] shrink-0 ${iconMuted}`} aria-hidden="true" />
            </a>
          </li>
        ))}
        {hasMore ? (
          <li className={divided}>
            <button
              type="button"
              aria-expanded={expanded}
              aria-controls="account-owned-businesses"
              onClick={() => setExpanded((value) => !value)}
              className={`${rowBase} font-medium text-[var(--cuadrao-green)]`}
            >
              <span className="min-w-0 flex-1">
                {expanded ? t("settings.profile.request_deletion.show_less") : t("settings.profile.request_deletion.show_all", { total: businesses.length })}
              </span>
              {expanded ? <ChevronUp className="h-[18px] w-[18px] shrink-0" aria-hidden="true" /> : <ChevronDown className="h-[18px] w-[18px] shrink-0" aria-hidden="true" />}
            </button>
          </li>
        ) : null}
      </ul>
      {openFailed ? <p role="alert" className={`mt-2 px-4 text-[14px] leading-5 ${muted}`}>{t("business.lifecycle.errors.discovery")}</p> : null}
    </>
  );
}

function SupportRequest({ fullWidth }: { fullWidth: boolean }) {
  const { t } = useTranslation();
  const [state, setState] = useState<"idle" | "sending" | "requested" | "failed">("idle");
  const [send] = useState(() => previewSupportRequest() ?? requestSupportDeletion);

  if (state === "requested") {
    return (
      <p role="status" className="mt-3 flex items-start gap-2.5 px-4 text-[14px] leading-[21px]">
        <CircleCheck className="mt-px h-[18px] w-[18px] shrink-0 text-[var(--cuadrao-green)]" aria-hidden="true" />
        {t("settings.profile.request_deletion.requested")}
      </p>
    );
  }
  return (
    <>
      <div className={`mt-3 flex justify-end ${fullWidth ? "" : "pr-4"}`}>
        <button
          type="button"
          className={`${secondaryButtonClass} ${fullWidth ? "w-full" : ""}`}
          disabled={state === "sending"}
          onClick={async () => {
            setState("sending");
            try {
              await send();
              setState("requested");
            } catch {
              setState("failed");
            }
          }}
        >
          {t("settings.profile.request_deletion.request_support")}
        </button>
      </div>
      {state === "failed" ? <p role="alert" className={`mt-2 px-4 text-[14px] leading-5 ${muted}`}>{t("common.error_occurred")}</p> : null}
    </>
  );
}
