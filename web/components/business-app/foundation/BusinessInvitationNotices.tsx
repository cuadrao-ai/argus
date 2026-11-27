"use client";

import { useEffect, useRef, useState, type RefObject } from "react";
import Image from "next/image";
import { Building2, Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";

import { acceptBusinessInvitation } from "@/lib/business-api";
import type { BusinessNotice } from "@/lib/business-notifications";
import { forgetPendingInvite, pendingInviteId } from "@/lib/business-pending-invite";
import { formatBusinessName } from "../business-format";
import { primaryButtonClass, quietButtonClass } from "../business-ui";
import styles from "./business-notifications.module.css";
import type { BusinessNotices } from "./useBusinessNotices";

/** How the person reached the invitation they accepted: the email's link, or the bell while working. */
export type AcceptedVia = "link" | "bell";

const LEAVE_MS = 220;
const REFUSED = new Set([403, 404, 409]);

type Props = {
  notices: BusinessNotices;
  /** The notices that were unread when the panel opened; their dots stay while it is open. */
  fresh: readonly string[];
  /** The invitation the email link named, when the server lists it. */
  linked: string | null;
  /** The email link named an invitation the server no longer offers this person. */
  gone: boolean;
  listRef: RefObject<HTMLDivElement | null>;
  onAccepted: (grantId: string, via: AcceptedVia) => void;
};

export default function BusinessInvitationNotices({ notices, fresh, linked, gone, listRef, onAccepted }: Props) {
  const { t } = useTranslation();
  const [accepting, setAccepting] = useState<string | null>(null);
  const [leaving, setLeaving] = useState<string | null>(null);
  const [failed, setFailed] = useState<ReadonlySet<string>>(new Set());
  const [refused, setRefused] = useState<ReadonlySet<string>>(new Set());
  const emptyHeading = useRef<HTMLHeadingElement>(null);
  const focusNext = useRef(false);
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => {
    if (linked) listRef.current?.querySelector<HTMLButtonElement>("[data-linked] button")?.focus();
  }, [linked, listRef]);
  useEffect(() => {
    if (!focusNext.current) return;
    focusNext.current = false;
    (listRef.current?.querySelector<HTMLButtonElement>("li button:not(:disabled)") ?? emptyHeading.current)?.focus();
  }, [notices.items, listRef]);

  const accept = async (notice: BusinessNotice) => {
    if (accepting || leaving || refused.has(notice.id)) return;
    setAccepting(notice.id);
    setFailed((current) => new Set([...current].filter((id) => id !== notice.id)));
    try {
      const accepted = await acceptBusinessInvitation(notice);
      const via: AcceptedVia = pendingInviteId() === notice.id ? "link" : "bell";
      if (via === "link") forgetPendingInvite();
      const still = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true;
      if (mounted.current && !still) {
        setLeaving(notice.id);
        await new Promise((resolve) => setTimeout(resolve, LEAVE_MS));
      }
      focusNext.current = via === "bell";
      notices.remove(notice.id);
      onAccepted(accepted.grant_id, via);
    } catch (error) {
      if (!mounted.current) return;
      setFailed((current) => new Set([...current, notice.id]));
      const status = error && typeof error === "object" && "status" in error ? error.status : null;
      if (typeof status === "number" && REFUSED.has(status)) setRefused((current) => new Set([...current, notice.id]));
    } finally {
      if (mounted.current) { setAccepting(null); setLeaving(null); }
    }
  };

  if (notices.load === "failed") return <div className={styles.empty}>
    <p role="alert" className={styles.loadFailed}>{t("business.notifications.load_failed")}</p>
    <button type="button" className={quietButtonClass} onClick={notices.retry}>{t("common.retry")}</button>
  </div>;
  const goneNotice = gone ? <div className={styles.goneSlot}><div role="status" className={`rounded-item ${styles.gone}`}>
    <p className={styles.goneTitle}>{t("business.notifications.invitation_gone_title")}</p>
    <p className={styles.goneBody}>{t("business.notifications.invitation_gone_body")}</p>
  </div></div> : null;
  if (notices.load === "loading") return <>{goneNotice}<div className="m-5 h-24 animate-pulse rounded-item bg-black/5 dark:bg-white/[0.06]" aria-busy="true" /></>;
  return <>
    {goneNotice}
    {notices.items.length ? <ul aria-label={t("business_access.invitations_title")}>
      {notices.items.map((notice) => {
        const named = Boolean(notice.business_name?.trim());
        const name = formatBusinessName(notice.business_name, t("business.overview.title", "My business"));
        const busy = accepting === notice.id;
        const off = refused.has(notice.id) || (Boolean(accepting) && !busy) || Boolean(leaving);
        return <li key={notice.id} data-notice={notice.id} data-linked={linked === notice.id ? "" : undefined} data-leaving={leaving === notice.id ? "" : undefined} className={styles.invitation}>
          <span aria-hidden="true" className={`rounded-item ${styles.tile} ${named ? "" : styles.tileUnnamed}`}>{named ? name.trim().charAt(0).toUpperCase() : <Building2 size={18} />}</span>
          <div className="min-w-0">
            <div className={styles.rowHeading}>
              <h3 className={styles.unreadTitle}>{name}</h3>
              {fresh.includes(notice.id) ? <span role="img" aria-label={t("business.notifications.unread_label")} className={`${styles.dot} self-center`} /> : null}
            </div>
            <p className={styles.invitationMeta}>{t(`workspace_setup_preview.permission_${notice.requested_role}`)} · {t("workspace_setup_preview.invite_pending")}</p>
            {failed.has(notice.id) ? <p role="alert" className={styles.acceptFailed}>{t("business_access.invitation_accept_failed")}</p> : null}
            <button type="button" className={`${primaryButtonClass} ${styles.accept}`} disabled={off || busy} aria-busy={busy} onClick={() => void accept(notice)}>
              {busy ? <Loader2 aria-hidden="true" size={16} className="animate-spin motion-reduce:animate-none" /> : null}{t("business_access.accept_invitation")}
            </button>
          </div>
        </li>;
      })}
    </ul> : <div className={styles.empty} data-notification-state="empty-all">
      <div className={styles.emptyArt}><Image src="/images/notifications/quiet-bell.png" alt="" width={88} height={88} sizes="88px" /></div>
      <h3 ref={emptyHeading} tabIndex={-1} className={styles.emptyTitle}>{t("business.notifications.empty_all_title")}</h3>
      <p className={styles.emptyDescription}>{t("business.notifications.empty_all_body")}</p>
      <div className={styles.emptyAction} />
    </div>}
  </>;
}
