"use client";

import { useBusinessNaming } from "./BusinessNamingProvider";

import { useEffect, useState, type FormEvent } from "react";
import { Mail, ShieldCheck, UserRound } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { BusinessAccess, BusinessAccessGrant, BusinessAccessInvite } from "@/lib/business-api";
import { useBusiness } from "./BusinessWorkspace";
import { cardClass, dangerButtonClass, dangerConfirmButtonClass, LoadingRows, PanelHeading, primaryButtonClass, secondaryButtonClass } from "./business-ui";

type Pending = { kind: "grant"; item: BusinessAccessGrant } | { kind: "invite"; item: BusinessAccessInvite };

function formatDay(value: string, locale: string): string {
  return new Date(value).toLocaleDateString(locale, { day: "numeric", month: "short", year: "numeric" });
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
}: {
  access: BusinessAccess;
  busyId: string | null;
  onRemove: (target: Pending) => void;
}) {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? "en";
  const rowClass = "flex items-center gap-3 px-3 py-3";
  return (
    <>
      <ul className={`${cardClass} divide-y divide-black/[0.05] p-2 dark:divide-white/[0.05]`} data-testid="business-access-grants">
        {access.grants.map((grant) => (
          <li key={grant.id} className={rowClass}>
            <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-[12px] bg-black/[0.04] dark:bg-white/[0.06]">
              {grant.owner ? <ShieldCheck className="h-5 w-5 text-black/55 dark:text-white/55" aria-hidden="true" /> : <UserRound className="h-5 w-5 text-black/55 dark:text-white/55" aria-hidden="true" />}
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-[15px] font-medium text-black dark:text-white">{grant.display_name}{grant.email ? ` · ${grant.email}` : ""}</span>
              <span className="mt-0.5 block truncate text-[13px] text-black/50 dark:text-white/50">
                {grant.owner ? t("business_access.owner", "Owner") : t("business_access.member", "Reads and prepares")} · {t("business_access.since", "Since {{date}}", { date: formatDay(grant.created_at, locale) })}
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
              <li key={invite.id} className={rowClass}>
                <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-[12px] bg-black/[0.04] dark:bg-white/[0.06]">
                  <Mail className="h-5 w-5 text-black/55 dark:text-white/55" aria-hidden="true" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[15px] font-medium text-black dark:text-white">{invite.email}</span>
                  <span className="mt-0.5 block truncate text-[13px] text-black/50 dark:text-white/50">{t("business_access.pending_until", "Expires {{date}}", { date: formatDay(invite.expires_at, locale) })}</span>
                </span>
                <button type="button" className={dangerButtonClass} disabled={busyId === invite.id} onClick={() => onRemove({ kind: "invite", item: invite })}>
                  {t("business_access.remove_invite", "Cancel invite")}
                </button>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </>
  );
}

export default function BusinessAccessPanel() {
  const { t } = useTranslation();
  const { source, revision } = useBusiness();
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
      setAccess(await source.giveAccess(address));
      setEmail("");
    } catch (error) {
      const status = (error as { status?: number }).status;
      setGiveError(status === 422 ? t("business_access.invalid_email", "Enter an email address.") : t("business_access.give_error", "We couldn't give access. Try again."));
    } finally {
      setGiving(false);
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
      <PanelHeading
        title={t("business_access.title", "Access")}
        subtitle={t("business_access.subtitle", "Who can see and prepare your business records. Only you approve.")}
      />
      {failed ? (
        <p role="alert" className="text-[14px] text-black/70 dark:text-white/70">{t("business_access.error", "We couldn't load access. Try again.")}</p>
      ) : access === null ? (
        <LoadingRows />
      ) : (
        <>
          <AccessList access={access} busyId={busyId} onRemove={setPending} />
          {removeError ? <p role="alert" className="mt-3 text-[14px] text-black/70 dark:text-white/70">{t("business_access.remove_error", "We couldn't remove access. Try again.")}</p> : null}
          {pending ? (
            <div role="alertdialog" aria-labelledby="business-access-confirm" className={`${cardClass} mt-4`}>
              <p id="business-access-confirm" className="text-[15px] text-black dark:text-white">
                {pending.kind === "grant"
                  ? t("business_access.remove_confirm", "Remove access for {{who}}? They stop seeing and preparing at once.", { who })
                  : t("business_access.remove_invite_confirm", "Cancel the invite for {{who}}?", { who })}
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                <button type="button" className={dangerConfirmButtonClass} onClick={remove}>{t("business_access.confirm", "Yes, remove")}</button>
                <button type="button" className={secondaryButtonClass} onClick={() => setPending(null)}>{t("business_access.cancel", "Cancel")}</button>
              </div>
            </div>
          ) : null}
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
                className="w-full rounded-[14px] border border-black/10 bg-white px-4 py-3 text-[15px] text-black outline-none focus:border-black/30 dark:border-white/10 dark:bg-[#1f2225] dark:text-white dark:focus:border-white/30"
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
