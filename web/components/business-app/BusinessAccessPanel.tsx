"use client";

import { useBusinessNaming } from "./BusinessNamingProvider";

import { useEffect, useState, type FormEvent } from "react";
import { Avatar } from "@/components/ui/Avatar";
import { useTranslation } from "react-i18next";
import type { BusinessAccess, BusinessAccessGrant, BusinessAccessInvite } from "@/lib/business-api";
import { useBusiness } from "./BusinessWorkspace";
import { EmptyState } from "./foundation/EmptyState";
import { cardClass, dangerButtonClass, PanelHeading, primaryButtonClass, secondaryButtonClass } from "./business-ui";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { Settle } from "./business-skeletons";
import { resolveLanguage } from "@/lib/language-features";


type Pending = { kind: "grant"; item: BusinessAccessGrant } | { kind: "invite"; item: BusinessAccessInvite };

function formatDay(value: string, locale: string): string {
  return new Date(value).toLocaleDateString(locale, { day: "numeric", month: "short", year: "numeric", timeZone: "America/Santo_Domingo" });
}

/**
 * The access list as the server reports it: the owner first, then each person
 * with a live grant, then pending invites. Nothing here decides who may act;
 * the grant row on the server does.
 */
export function AccessList({
  access,
  busyId,
  onRemove,
  onResend,
}: {
  access: BusinessAccess;
  busyId: string | null;
  onRemove: (target: Pending) => void;
  onResend: (invite: BusinessAccessInvite) => void;
}) {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? resolveLanguage({});
  const rowClass = "flex items-center gap-3 px-3 py-3";
  return (
    <>
      <ul className={`${cardClass} divide-y divide-black/[0.05] p-2 dark:divide-white/[0.05]`} data-testid="business-access-grants">
        {access.grants.map((grant) => (
          <li key={grant.id} className={rowClass}>
            <Avatar name={grant.display_name || grant.email} size={40} testId="access-avatar" />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-[15px] font-medium text-black dark:text-white">{grant.display_name}{grant.email ? ` · ${grant.email}` : ""}</span>
              <span className="mt-0.5 block truncate text-[13px] text-black/50 dark:text-white/50">
                {grant.owner ? t("business_access.owner", "Owner") : t("business_access.member", "Member")} · {t("business_access.since", "Since {{date}}", { date: formatDay(grant.created_at, locale) })}
              </span>
            </span>
            {grant.owner ? (
              <span className="text-[12px] text-black/40 dark:text-white/40">{t("business_access.owner_locked", "Your own access cannot be removed.")}</span>
            ) : (
              <button type="button" className={dangerButtonClass} disabled={busyId === grant.id} onClick={() => onRemove({ kind: "grant", item: grant })}>
                {t("business_access.remove", "Remove access")}
              </button>
            )}
          </li>
        ))}
      </ul>
      {access.invites.length ? (
        <section aria-label={t("business_access.pending_title", "Pending invites")} className="mt-6">
          <h3 className="font-display text-[16px] font-medium text-black dark:text-white">{t("business_access.pending_title", "Pending invites")}</h3>
          <p className="mb-3 mt-0.5 text-[13px] text-black/55 dark:text-white/55">{t("business_access.pending_note", "Gets access the first time they sign in with this confirmed email.")}</p>
          <ul className={`${cardClass} divide-y divide-black/[0.05] p-2 dark:divide-white/[0.05]`} data-testid="business-access-invites">
            {access.invites.map((invite) => (
              <li key={invite.id} className="grid grid-cols-[2.75rem_minmax(0,1fr)] items-center gap-3 px-3 py-3 sm:flex">
                <Avatar name={invite.email} size={40} status="pending" testId="access-avatar" />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[15px] font-medium text-black dark:text-white">{invite.email}</span>
                  <span className="mt-0.5 block break-words text-[13px] text-black/50 dark:text-white/50">{invite.state === "expired"
                    ? (t("business_access.invite_expired", "La invitación a {{email}} venció.", { email: invite.email }) || `La invitación a ${invite.email} venció.`)
                    : t("business_access.pending_until", "Expires {{date}}", { date: formatDay(invite.expires_at, locale) })}</span>
                </span>
                <div className="col-start-2 flex flex-wrap gap-2">
                  <button type="button" className={secondaryButtonClass} disabled={busyId === invite.id} onClick={() => onResend(invite)}>
                    {t("business_access.resend", "Reenviar") || "Reenviar"}
                  </button>
                  <button type="button" className={dangerButtonClass} disabled={busyId === invite.id} onClick={() => onRemove({ kind: "invite", item: invite })}>
                    {t("business_access.remove_invite", "Cancel invite")}
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </>
  );
}

/** Equipo y accesos. `embedded` drops its own heading inside the Negocio page, which names it. */
export default function BusinessAccessPanel({ embedded = false }: { embedded?: boolean } = {}) {
  const { t } = useTranslation();
  const { source, revision, reload } = useBusiness();
  const naming = useBusinessNaming();
  const [access, setAccess] = useState<BusinessAccess | null>(null);
  const [failed, setFailed] = useState(false);
  const [email, setEmail] = useState("");
  const [giving, setGiving] = useState(false);
  const [giveError, setGiveError] = useState<string | null>(null);
  const [pending, setPending] = useState<Pending | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [removeError, setRemoveError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setFailed(false);
    source
      .access()
      .then((next) => !cancelled && setAccess(next))
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, [revision, source]);

  const give = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const address = email.trim();
    if (!address.includes("@")) {
      setGiveError(t("business_access.invalid_email", "Enter an email address."));
      return;
    }
    setGiving(true);
    setGiveError(null);
    try {
      if (naming && !await naming.requireName()) return;
      const next = await source.giveAccess(address);
      setAccess(next);
      if (next.invite_delivery && next.invite_delivery !== "accepted") {
        setGiveError(t("business_access.give_error", "We couldn't give access. Try again."));
      }
      setEmail("");
    } catch (error) {
      const status = (error as { status?: number }).status;
      setGiveError(status === 422 ? t("business_access.invalid_email", "Enter an email address.") : t("business_access.give_error", "We couldn't give access. Try again."));
    } finally {
      setGiving(false);
    }
  };

  const resend = async (invite: BusinessAccessInvite) => {
    setBusyId(invite.id);
    setGiveError(null);
    try {
      const next = await source.resendAccessInvite(invite.id);
      setAccess(next);
      if (next.invite_delivery && next.invite_delivery !== "accepted") {
        setGiveError(t("business_access.give_error", "We couldn't give access. Try again."));
      }
    } catch {
      setGiveError(t("business_access.give_error", "We couldn't give access. Try again."));
    } finally {
      setBusyId(null);
    }
  };

  const remove = async () => {
    if (!pending) return;
    const target = pending;
    setPending(null);
    setBusyId(target.item.id);
    setRemoveError(false);
    try {
      if (target.kind === "grant") await source.revokeAccessGrant(target.item.id);
      else await source.revokeAccessInvite(target.item.id);
      setAccess(await source.access());
    } catch {
      setRemoveError(true);
    } finally {
      setBusyId(null);
    }
  };

  const who = pending ? (pending.kind === "grant" ? pending.item.email ?? pending.item.display_name : pending.item.email) : "";

  return (
    <section>
      {embedded ? <p className="mb-4 text-[14px] text-[#56635e] dark:text-white/70">{t("business_access.subtitle", "Who can see and prepare your business records. Only you approve.")}</p> : (
        <PanelHeading
          title={t("business_access.title", "Access")}
          subtitle={t("business_access.subtitle", "Who can see and prepare your business records. Only you approve.")}
        />
      )}
      {failed ? (
        <EmptyState kind="error" testId="business-access-error" title={t("business.empty.access_error", "We couldn't load access")} body={t("business.empty.error_body", "Your data is still saved. Check your connection and try again.")} action={{ label: t("common.retry", "Retry"), run: reload }} />
      ) : access === null ? (
        <Settle pending layout="access" />
      ) : (
        <>
          <AccessList access={access} busyId={busyId} onRemove={setPending} onResend={resend} />
          {removeError ? <p role="alert" className="mt-3 text-[14px] text-black/70 dark:text-white/70">{t("business_access.remove_error", "We couldn't remove access. Try again.")}</p> : null}
          <ConfirmDialog
            isOpen={pending !== null}
            title={pending?.kind === "invite"
              ? t("business_access.remove_invite_title", { who, defaultValue: "Cancel the invite for {{who}}?" })
              : t("business_access.remove_title", { who, defaultValue: "Remove access for {{who}}?" })}
            description={pending?.kind === "invite"
              ? t("business_access.remove_invite_body", "You can invite them again at any time.")
              : t("business_access.remove_body", "They stop seeing and preparing your records at once.")}
            confirmLabel={pending?.kind === "invite" ? t("business_access.remove_invite", "Cancel invite") : t("business_access.remove", "Remove access")}
            cancelLabel={t("business_access.keep", "Keep")}
            onCancel={() => setPending(null)}
            onConfirm={() => void remove()}
          />
          <form onSubmit={give} className={`${cardClass} mt-6`} data-testid="business-access-give">
            <h3 className="font-display text-[16px] font-medium text-black dark:text-white">{t("business_access.give_title", "Give access to your accountant")}</h3>
            <p className="mb-3 mt-0.5 text-[13px] text-black/55 dark:text-white/55">{t("business_access.give_body", "Enter their email. They can see and prepare receipts. They can never approve.")}</p>
            <label className="block">
              <span className="sr-only">{t("business_access.email_label", "Email address")}</span>
              <input
                type="email"
                inputMode="email"
                autoComplete="off"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder={t("business_access.email_label", "Email address")}
                className="w-full rounded-item border border-black/10 bg-white px-4 py-3 text-[15px] text-black outline-none focus:border-black/30 dark:border-white/10 dark:bg-[#1f2225] dark:text-white dark:focus:border-white/30"
              />
            </label>
            {giveError ? <p role="alert" className="mt-2 text-[13px] text-black/70 dark:text-white/70">{giveError}</p> : null}
            <button type="submit" className={`${primaryButtonClass} mt-3`} disabled={giving}>
              {giving ? t("business_access.giving", "Giving access...") : t("business_access.give", "Give access")}
            </button>
          </form>
        </>
      )}
    </section>
  );
}
