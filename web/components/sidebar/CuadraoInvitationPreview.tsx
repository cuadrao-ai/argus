"use client";

import { useEffect, useId, useRef, useState, type ReactNode, type RefObject } from "react";
import { ArrowLeft, ChevronRight, HandHeart, LoaderCircle, Send, Users, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useModalSurface } from "@/components/layout/useModalSurface";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import BottomSheet from "@/components/ui/BottomSheet";
import { FormField, useFieldChecks } from "@/components/ui/FormField";
import { withViewportPortal } from "@/components/ui/withViewportPortal";
import { primaryButtonClass, quietButtonClass } from "@/components/business-app/business-ui";
import { CopyButton } from "@/components/business-app/foundation/CopyButton";
import { showToast } from "@/components/business-app/foundation/toasts";
import { localeForLanguage, normalizeEnabledLanguage } from "@/lib/language-features";
import styles from "./cuadrao-invitation-preview.module.css";

export type LocalInvitation = { id: string; email: string; createdAt: string; status: "pending" | "joined" };
const INVITATION_LINK = "https://cuadrao.example/i/piloto";

type Props = {
  invitations: readonly LocalInvitation[];
  onSent: (invitation: LocalInvitation) => void;
  onClose: () => void;
  returnFocusRef: RefObject<HTMLElement | null>;
};

function DesktopSurface({ children, title, onClose, returnFocusRef }: { children: ReactNode; title: string; onClose: () => void; returnFocusRef: RefObject<HTMLElement | null> }) {
  const id = useId();
  const panel = useRef<HTMLDivElement>(null);
  const close = useRef<HTMLButtonElement>(null);
  const { t } = useTranslation();
  useModalSurface({ isOpen: true, overlayId: id, containerRef: panel, initialFocusRef: close, returnFocusRef, onDismiss: onClose });
  return <div className={styles.scrim}>
    <button type="button" tabIndex={-1} aria-label={t("common.close")} className={styles.backdrop} onClick={onClose} />
    <div ref={panel} role="dialog" aria-modal="true" aria-label={title} className={styles.dialog} data-testid="cuadrao-invitation-dialog">
      <button ref={close} type="button" aria-label={t("common.close")} className={styles.close} onClick={onClose}><X size={20} aria-hidden="true" /></button>
      {children}
    </div>
  </div>;
}
const DesktopModal = withViewportPortal(DesktopSurface);

export default function CuadraoInvitationPreview({ invitations, onSent, onClose, returnFocusRef }: Props) {
  const { t, i18n } = useTranslation();
  const { isBelowDesktop } = useResponsiveLayout();
  const id = useId();
  const [view, setView] = useState<"compose" | "history">("compose");
  const [email, setEmail] = useState("");
  const [sending, setSending] = useState(false);
  const [copyFailed, setCopyFailed] = useState(false);
  const emailRef = useRef<HTMLInputElement>(null);
  const linkRef = useRef<HTMLInputElement>(null);
  const backRef = useRef<HTMLButtonElement>(null);
  const historyRef = useRef<HTMLButtonElement>(null);
  const moveFocus = useRef(false);
  const sendTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const normalEmail = email.trim().toLowerCase();
  const checks = useFieldChecks({ email: () => {
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(normalEmail)) return t("cuadrao_invitation.email_invalid");
    if (invitations.some((row) => row.email.toLowerCase() === normalEmail)) return t("cuadrao_invitation.email_duplicate");
    return null;
  } }, { email });
  const locale = localeForLanguage(normalizeEnabledLanguage(i18n.resolvedLanguage));
  const date = new Intl.DateTimeFormat(locale, { day: "numeric", month: "short" });
  const sent = invitations.length;
  const joined = invitations.filter((row) => row.status === "joined").length;
  const title = t(view === "compose" ? "cuadrao_invitation.title" : "cuadrao_invitation.history_title");

  useEffect(() => () => { if (sendTimer.current) clearTimeout(sendTimer.current); }, []);
  useEffect(() => {
    if (!moveFocus.current) return;
    (view === "history" ? backRef.current : historyRef.current)?.focus();
    moveFocus.current = false;
  }, [view]);
  const changeView = (next: "compose" | "history") => { moveFocus.current = true; setView(next); };
  const close = () => { onClose(); returnFocusRef.current?.focus(); };
  const send = () => {
    if (sendTimer.current) return;
    if (!checks.submit()) { emailRef.current?.focus(); return; }
    setSending(true);
    sendTimer.current = setTimeout(() => {
      onSent({ id: crypto.randomUUID(), email: normalEmail, createdAt: new Date().toISOString(), status: "pending" });
      sendTimer.current = null;
      setSending(false);
      setEmail("");
      checks.reset();
      showToast({ kind: "success", text: t("cuadrao_invitation.sent_confirmation", { email: normalEmail }) });
      emailRef.current?.focus();
    }, 300);
  };

  const content = <div className={styles.content} data-testid="cuadrao-invitation-content">
    {view === "compose" ? <>
      <header className={styles.intro}>
        <HandHeart className={styles.art} size={48} strokeWidth={1.5} aria-hidden="true" />
        <h2 className={styles.title}>{t("cuadrao_invitation.title")}</h2>
        <p>{t("cuadrao_invitation.subtitle")}</p>
      </header>
      <div className={styles.fieldRow}>
        <FormField ref={linkRef} id={`${id}-link`} label={t("cuadrao_invitation.link_label")} value={INVITATION_LINK} readOnly reserveMessages={[]} error={copyFailed ? t("cuadrao_invitation.copy_failed") : null} onFocus={(event) => event.currentTarget.select()} />
        <div className={styles.copyAction} onClickCapture={() => setCopyFailed(false)}><CopyButton value={INVITATION_LINK} label={t("cuadrao_invitation.copy")} copiedLabel={t("cuadrao_invitation.copied")} failedLabel={t("cuadrao_invitation.copy_failed")} onFailed={() => { setCopyFailed(true); linkRef.current?.focus(); linkRef.current?.select(); }} className={`${primaryButtonClass} ${styles.action}`}>{t("cuadrao_invitation.copy")}</CopyButton></div>
      </div>
      <form noValidate aria-busy={sending} className={styles.fieldRow} onSubmit={(event) => { event.preventDefault(); send(); }}>
        <FormField ref={emailRef} id={`${id}-email`} label={t("cuadrao_invitation.email_label")} type="email" autoComplete="off" inputMode="email" maxLength={254} placeholder={t("cuadrao_invitation.email_placeholder")} value={email} required readOnly={sending} error={checks.errorOf("email")} success={checks.isValid("email") ? t("cuadrao_invitation.email_valid") : undefined} reserveMessages={[t("cuadrao_invitation.email_invalid"), t("cuadrao_invitation.email_duplicate"), t("cuadrao_invitation.email_valid")]} onBlur={() => checks.blur("email")} onChange={(event) => setEmail(event.target.value)} />
        <button type="submit" disabled={sending} className={`${primaryButtonClass} ${styles.action}`}>
          {sending ? <LoaderCircle size={16} className={styles.spinner} aria-hidden="true" /> : <Send size={16} aria-hidden="true" />}{t(sending ? "cuadrao_invitation.sending" : "cuadrao_invitation.send")}
        </button>
      </form>
      <div className={styles.divider}><span>{t("cuadrao_invitation.summary")}</span></div>
      <div className={styles.summary}>
        <div><strong data-testid="referral-sent-count">{sent}</strong><span>{t("cuadrao_invitation.sent")}</span></div>
        <div><strong data-testid="referral-joined-count">{joined}</strong><span>{t("cuadrao_invitation.joined")}</span></div>
        <Users size={36} strokeWidth={1.5} aria-hidden="true" />
      </div>
      <button ref={historyRef} type="button" disabled={sending} className={`${quietButtonClass} ${styles.historyLink}`} onClick={() => changeView("history")}>{t("cuadrao_invitation.history_title")}<ChevronRight size={16} aria-hidden="true" /></button>
      <p className={styles.note}>{t("cuadrao_invitation.separate_business")}</p>
    </> : <>
      <button ref={backRef} type="button" className={`${quietButtonClass} ${styles.back}`} onClick={() => changeView("compose")}><ArrowLeft size={16} aria-hidden="true" />{t("cuadrao_invitation.back")}</button>
      <h2 className={styles.historyTitle}>{t("cuadrao_invitation.history_title")}</h2>
      {invitations.length ? <ul className={styles.history}>{[...invitations].reverse().map((row) => <li key={row.id}>
        <div><strong>{row.email}</strong><time dateTime={row.createdAt}>{date.format(new Date(row.createdAt))}</time></div>
        <span>{t(`cuadrao_invitation.status_${row.status}`)}</span>
      </li>)}</ul> : <div className={styles.empty}><Users size={32} strokeWidth={1.5} aria-hidden="true" /><h3>{t("cuadrao_invitation.history_empty_title")}</h3><p>{t("cuadrao_invitation.history_empty_body")}</p></div>}
      <p className={styles.note}>{t("cuadrao_invitation.separate_business")}</p>
    </>}
  </div>;
  return isBelowDesktop ? <BottomSheet isOpen onClose={close} title={title} titleHidden closeLabel={t("common.close")} snaps={["full"]} initialSnap="full"><div className={styles.sheet}>{content}</div></BottomSheet> : <DesktopModal title={title} onClose={close} returnFocusRef={returnFocusRef}>{content}</DesktopModal>;
}
