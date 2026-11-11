"use client";

import { useCallback, useEffect, useId, useRef, useState, type ReactNode } from "react";
import { Check, Plus, Trash2, X } from "lucide-react";
import { Trans, useTranslation } from "react-i18next";
import BottomSheet from "@/components/ui/BottomSheet";
import { fieldClass, fieldErrorClass } from "@/components/ui/form-field";
import { ReferenceCode } from "@/components/status/ReferenceCode";
import { withViewportPortal } from "@/components/ui/withViewportPortal";
import { useModalSurface } from "@/components/layout/useModalSurface";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import AccessRolePicker from "@/app/design-workspace/AccessRolePicker";
import { accessRoleOptions, businessAccessChangedEvent, defaultInvitationRole, readAccessPreview, recordInvitationPreview } from "@/app/design-workspace/businessAccessPreviewState";
import { getBusinessAccess, inviteBusinessMembers, type BusinessInvitationCommand, type BusinessInvitationResult } from "@/lib/business-api";
import { referenceCode } from "@/lib/failure-screen";
import { supportEmail } from "@/lib/support-email";
import { primaryButtonClass, quietButtonClass, secondaryButtonClass, trashButtonClass } from "./business-ui";
import { formatBusinessName } from "./business-format";
import { useBusiness } from "./BusinessWorkspace";

type Row = BusinessInvitationCommand & { id: string; touched: boolean; result?: BusinessInvitationResult };
type KnownPeople = { members: string[]; pending: string[] };
type Feedback = { tone: "neutral" | "valid" } | { tone: "error"; key: string };
type Failure = { kind: "access" | "availability" | "send"; reference: string };

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const MAX_ROWS = 50;
/** The trash column stays reserved with one row, so the email column never changes width. */
const columns = "grid-cols-[minmax(0,1fr)_170px_44px]";
const footerButtonShape = "rounded-item!";
const DONE_STATES: BusinessInvitationResult["state"][] = ["pending", "accepted", "already_member"];
const NOBODY: KnownPeople = { members: [], pending: [] };
const copy = (key: string) => `workspace_setup_preview.${key}`;
const emptyRow = (): Row => ({ id: crypto.randomUUID(), email: "", role: defaultInvitationRole, command_key: crypto.randomUUID(), touched: false });
const clean = (email: string) => email.trim().toLowerCase();
const isDone = (row: Row) => row.result !== undefined && DONE_STATES.includes(row.result.state);
const isCreated = (row: Row) => row.result?.state === "pending" || row.result?.state === "accepted";
const wentOut = (row: Row) => isCreated(row) && row.result?.delivery === "accepted";
const isRefusal = (error: unknown) => {
  const status = error && typeof error === "object" && "status" in error ? error.status : null;
  return status === 403 || status === 404;
};
const isInvitationUnavailable = (error: unknown) => error !== null && typeof error === "object"
  && "status" in error && error.status === 409
  && "code" in error && error.code === "business_invitations_unavailable";

/** The X keeps the draft for this Business until the page reloads; emails stay out of browser storage. */
const drafts = new Map<string, Row[]>();

export function clearInvitationDraft(businessId: string) {
  if (businessId) drafts.delete(businessId);
}

export function peekInvitationDraftEmails(businessId: string): string[] {
  return (drafts.get(businessId) ?? []).map(row => row.email.trim()).filter(Boolean);
}

function emailProblem(row: Row, rows: Row[], known: KnownPeople): string | null {
  const email = clean(row.email);
  if (!email) return "invite_email_required";
  if (email.length > 254) return "invite_email_long";
  if (!EMAIL.test(email)) return "invite_email_invalid";
  if (rows.some(other => other.id !== row.id && clean(other.email) === email)) return "batch_duplicate";
  if (known.members.includes(email)) return "batch_member";
  if (known.pending.includes(email)) return "batch_pending";
  return null;
}

function rowFeedback(row: Row, rows: Row[], known: KnownPeople): Feedback {
  if (row.result) return { tone: "error", key: "batch_send_error" };
  if (!row.touched) return { tone: "neutral" };
  const problem = emailProblem(row, rows, known);
  return problem ? { tone: "error", key: problem } : { tone: "valid" };
}

function sampleKnownPeople(businessId: string, memberEmail?: string | null): KnownPeople {
  // eslint-disable-next-line no-restricted-syntax -- Development-only sample reuses the business-scoped invitation store.
  const { members, pending } = readAccessPreview(window.localStorage, businessId, memberEmail ? { email: memberEmail, permission: "owner" } : null);
  return { members: members.map(person => person.email), pending: pending.map(person => person.email) };
}

async function liveKnownPeople(): Promise<KnownPeople> {
  const { grants, invites } = await getBusinessAccess();
  return {
    members: grants.flatMap(person => person.email ? [clean(person.email)] : []),
    pending: invites.filter(invite => invite.state === "pending").map(invite => clean(invite.email)),
  };
}

async function fakeInvitations(businessId: string, recipients: BusinessInvitationCommand[]): Promise<{ results: BusinessInvitationResult[] }> {
  await new Promise(resolve => setTimeout(resolve, 650));
  // eslint-disable-next-line no-restricted-syntax -- Development-only sample reuses the business-scoped invitation store.
  recordInvitationPreview(window.localStorage, businessId, recipients.map(({ email, role }) => ({ email, permission: role })));
  return { results: recipients.map(({ command_key, email }) => ({ command_key, email, invite_id: null, state: "pending", delivery: "pending", code: null })) };
}

function DesktopDialog({ title, firstField, onClose, children }: { title: string; firstField: { current: HTMLElement | null }; onClose: () => void; children: ReactNode }) {
  const { t } = useTranslation();
  const id = useId();
  const panel = useRef<HTMLDivElement>(null);
  useModalSurface({ isOpen: true, overlayId: id, containerRef: panel, onDismiss: onClose, initialFocusRef: firstField });
  return <div className="fixed inset-0 z-[130] flex items-center justify-center bg-black/40 p-4 dark:bg-black/60">
    <button type="button" tabIndex={-1} aria-label={t("common.close")} className="absolute inset-0" onClick={onClose} />
    <div ref={panel} role="dialog" aria-modal="true" aria-labelledby={id} data-invitation-modal style={{ maxHeight: "calc(100dvh - 2rem)" }} className="relative flex w-full max-w-[600px] flex-col overflow-hidden rounded-surface border border-black/10 bg-white p-7 text-[#172b26] dark:border-white/10 dark:bg-[#151719] dark:text-white">
      <div className="grid grid-cols-[minmax(0,1fr)_44px] items-start gap-2">
        <h2 id={id} className="font-display pt-1 text-left text-[24px] font-medium tracking-tight">{title}</h2>
        <button type="button" aria-label={t("common.close")} onClick={onClose} className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-[#56635e] hover:bg-black/5 focus-visible:outline-2 focus-visible:outline-offset-2 dark:text-white/70 dark:hover:bg-white/5"><X className="h-5 w-5" aria-hidden="true" /></button>
      </div>
      {children}
    </div>
  </div>;
}
const CenteredDialog = withViewportPortal(DesktopDialog);

/** One invitation form for the Acceso button and the Business menu: a centered dialog on desktop, the tray below it. */
export default function BusinessInvitationForm({ onClose, onRefused }: { onClose: () => void; onRefused?: (error: unknown) => void }) {
  const { t } = useTranslation();
  const { chosen, source, bridge } = useBusiness();
  const { isBelowDesktop } = useResponsiveLayout();
  const businessId = chosen?.space_id ?? "";
  const live = source.mode === "live";
  const [rows, setRows] = useState<Row[]>(() => drafts.get(businessId) ?? [emptyRow()]);
  useEffect(() => {
    setRows(drafts.get(businessId) ?? [emptyRow()]);
  }, [businessId]);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [serverKnown, setServerKnown] = useState(NOBODY);
  const [sends, setSends] = useState(0);
  const form = useRef<HTMLFormElement>(null);
  const firstField = useRef<HTMLInputElement>(null);
  const summary = useRef<HTMLDivElement>(null);
  const formId = useId();
  useEffect(() => { drafts.set(businessId, rows); }, [businessId, rows]);
  const refuse = useCallback((error: unknown) => {
    drafts.delete(businessId);
    setFailure({ kind: "access", reference: referenceCode(error) });
    onRefused?.(error);
  }, [businessId, onRefused]);
  useEffect(() => {
    if (!live) return;
    let current = true;
    // The server still judges every recipient, so a failed read only loses the early warning.
    liveKnownPeople().then(
      people => { if (current) setServerKnown(people); },
      error => { if (current && isRefusal(error)) refuse(error); },
    );
    return () => { current = false; };
  }, [live, refuse, sends]);

  const refused = failure?.kind === "access";
  const unavailable = failure?.kind === "availability";
  const blocked = refused || unavailable;
  const known = live ? serverKnown : sampleKnownPeople(businessId, bridge?.memberEmail);
  const doneCount = rows.filter(isDone).length;
  const createdCount = rows.filter(isCreated).length;
  const sentCount = rows.filter(wentOut).length;
  const finished = doneCount > 0 && doneCount === rows.length;
  const partial = doneCount > 0 && !finished;
  const headline = partial ? t(copy("batch_partial"), { sent: sentCount, failed: rows.length - sentCount })
    : createdCount === 0 ? t(copy("batch_member"))
    : sentCount < createdCount ? t(copy("invite_pending_detail"))
    : sentCount === 1 ? t(copy("batch_success_one")) : t(copy("batch_success"), { count: sentCount });
  const removable = rows.length > 1;
  const roleOptions = accessRoleOptions(t, Boolean(chosen?.permissions?.includes("assign_owner")));
  const changeRow = (id: string, patch: Partial<Row>) => setRows(current => current.map(row => row.id === id ? { ...row, ...patch } : row));
  const focusLastEmail = () => requestAnimationFrame(() => {
    const fields = form.current?.querySelectorAll<HTMLInputElement>("[data-recipient-email]");
    fields?.[fields.length - 1]?.focus();
  });
  const close = () => {
    if (busy) return;
    onClose();
    if (finished) drafts.delete(businessId);
    // Refreshing the parent can unmount this form, so keep outcomes until dismissal.
    if (sends > 0) window.dispatchEvent(new Event(businessAccessChangedEvent));
  };
  const submit = async () => {
    if (busy || blocked) return;
    const filled = rows.some(row => row.email.trim()) ? rows.filter(row => row.email.trim()) : rows.slice(0, 1);
    const marked = filled.map(row => isDone(row) ? row : { ...row, touched: true });
    setRows(marked);
    const unsent = marked.filter(row => !isDone(row));
    if (unsent.some(row => emailProblem(row, marked, known))) {
      requestAnimationFrame(() => form.current?.querySelector<HTMLElement>('[aria-invalid="true"]')?.focus());
      return;
    }
    setBusy(true);
    setFailure(null);
    const recipients = unsent.map(({ email, role, command_key }) => ({ email: email.trim(), role, command_key }));
    try {
      const response = live ? await inviteBusinessMembers(recipients) : await fakeInvitations(businessId, recipients);
      setRows(current => current.map(row => {
        const result = response.results.find(item => item.command_key === row.command_key);
        return result ? { ...row, result } : row;
      }));
      setSends(count => count + 1);
      requestAnimationFrame(() => summary.current?.focus());
    } catch (error) {
      if (isRefusal(error)) refuse(error);
      else setFailure({ kind: isInvitationUnavailable(error) ? "availability" : "send", reference: referenceCode(error) });
    } finally {
      setBusy(false);
    }
  };

  const sentRow = (row: Row) => {
    const result = row.result;
    return <>
      <div className="flex flex-wrap items-baseline justify-between gap-x-2"><p className="min-w-0 break-all text-[16px] font-medium">{row.email}</p><span className="text-[14px] text-[#56635e] dark:text-white/70">{t(copy(`permission_${row.role}`))}</span></div>
      <p role="status" className="mt-1.5 flex items-center gap-1.5 text-[14px] text-[#56635e] dark:text-white/70"><Check aria-hidden="true" className="h-4 w-4 shrink-0 text-[#2f5a49] dark:text-[#8fcbb0]" />{t(result?.state === "accepted" ? "business_access.invitation_accepted" : result?.state === "already_member" ? copy("batch_member") : wentOut(row) ? copy("batch_sent_pending") : copy("invite_pending_detail"))}</p>
      {result?.delivery && result.delivery !== "pending" ? <p className="text-[14px]">{t(`business_access.delivery_${result.delivery}`)}</p> : null}
    </>;
  };
  const draftRow = (row: Row, index: number) => {
    const feedback: Feedback = unavailable ? { tone: "neutral" } : rowFeedback(row, rows, known);
    const inputId = `${formId}-${row.id}`;
    const email = <div className="min-w-0">
      <label htmlFor={inputId} className={isBelowDesktop ? "mb-1 block text-[14px] font-medium" : "sr-only"}>{t(copy("invite_email_label"))}</label>
      <div className="relative">
        <input ref={index === 0 ? firstField : undefined} id={inputId} data-recipient-email type="email" autoComplete="email" autoCapitalize="none" spellCheck={false} placeholder={t(copy("invite_email_example"))} value={row.email} disabled={busy || blocked} aria-invalid={feedback.tone === "error"} aria-describedby={`${inputId}-note`} className={`${fieldClass} mt-0! ${feedback.tone === "valid" ? "border-[#2f5a49]! pr-11! dark:border-[#8fcbb0]!" : ""}`}
          onBlur={() => { if (row.email.trim()) changeRow(row.id, { touched: true }); }}
          onChange={event => changeRow(row.id, { email: event.target.value, touched: feedback.tone === "error", result: undefined, command_key: crypto.randomUUID() })} />
        {feedback.tone === "valid" ? <Check aria-hidden="true" className="pointer-events-none absolute right-3 top-3.5 h-5 w-5 text-[#2f5a49] dark:text-[#8fcbb0]" /> : null}
      </div>
    </div>;
    const access = <div className="min-w-0 flex-1">
      <AccessRolePicker compact value={row.role} label={row.email ? `${t(copy("permission_label"))} · ${row.email}` : t(copy("permission_label"))} disabled={busy || blocked} options={roleOptions} portalRoot={typeof document === "undefined" ? null : document.querySelector("[data-invitation-modal]")} onChange={role => changeRow(row.id, { role: role as Row["role"], command_key: crypto.randomUUID() })} />
    </div>;
    const remove = removable ? <button type="button" className={trashButtonClass} disabled={busy || blocked} aria-label={row.email ? t(copy("batch_remove"), { email: row.email }) : t(copy("batch_remove_empty"))} onClick={() => { setRows(current => current.filter(item => item.id !== row.id)); focusLastEmail(); }}><Trash2 className="h-4 w-4" aria-hidden="true" /></button> : null;
    const note = <p id={`${inputId}-note`} role={feedback.tone === "error" ? "alert" : "status"} className={feedback.tone === "error" ? `mt-1.5 ${fieldErrorClass}` : "sr-only"}>{feedback.tone === "error" ? t(copy(feedback.key)) : feedback.tone === "valid" ? t(copy("batch_email_format_valid")) : ""}</p>;
    if (isBelowDesktop) return <>{email}{note}<div className="mt-2 flex items-end gap-2">{access}{remove}</div></>;
    return <><div className={`grid items-center gap-2 ${columns}`}>{email}{access}{remove}</div>{note}</>;
  };

  const sendable = rows.filter(row => !isDone(row) && row.email.trim()).length;
  const sendLabel = busy ? t(copy("invite_sending")) : partial || failure ? t(copy("batch_retry")) : sendable > 1 ? t(copy("batch_send_count"), { count: sendable }) : t(copy(sendable === 1 ? "batch_send_one" : "batch_send"));
  const content = <form ref={form} noValidate aria-busy={busy} onSubmit={event => { event.preventDefault(); void submit(); }} className={isBelowDesktop ? "pb-5 pt-1 text-[#172b26] dark:text-white" : "flex min-h-0 flex-col"}>
    <p className="mb-3 break-words text-[14px] leading-[21px] text-[#56635e] dark:text-white/70"><Trans i18nKey={copy("batch_subtitle")} values={{ business: formatBusinessName(chosen?.name, t("business.overview.title", "My business")) }} components={{ strong: <strong className="text-[16px] font-semibold text-[#172b26] dark:text-white" /> }} /></p>
    {finished || partial ? <div ref={summary} tabIndex={-1} role="status" className="mb-4 outline-none">
      <p className="text-[21px] font-semibold">{headline}</p>
      {sentCount > 0 ? <p className="mt-1.5 text-[14px] text-[#56635e] dark:text-white/70">{t(copy("batch_no_access"))}</p> : null}
    </div> : null}
    {!finished && !isBelowDesktop ? <div className={`grid items-center gap-2 text-[16px] font-medium ${columns}`}><span>{t(copy("invite_email_label"))}</span><span>{t(copy("permission_label"))}</span></div> : null}
    <ul aria-label={t(copy("batch_recipients"))} className={isBelowDesktop ? undefined : "-mx-1 min-h-0 overflow-y-auto overscroll-contain px-1"}>
      {rows.map((row, index) => <li key={row.id} className={isBelowDesktop ? "py-2.5" : "py-1.5"}>{isDone(row) ? sentRow(row) : draftRow(row, index)}</li>)}
    </ul>
    {!finished ? <div className="flex justify-start"><button type="button" className={`${quietButtonClass} -ml-1`} disabled={busy || blocked || rows.length >= MAX_ROWS} onClick={() => { setRows(current => [...current, emptyRow()]); focusLastEmail(); }}><Plus className="h-4 w-4" aria-hidden="true" />{t(copy("batch_add_short"))}</button></div> : null}
    {failure ? <div role="alert" className={`mt-3 space-y-1 ${fieldErrorClass}`}>
      <p>{t(unavailable ? copy("batch_unavailable_placeholder") : refused ? "business.lifecycle.errors.business_unavailable" : copy("batch_send_error"))}</p>
      {refused ? <p>{t("auth.business_unavailable.body", { supportEmail })}</p> : null}
      <ReferenceCode reference={failure.reference} />
    </div> : null}
    <div className="mt-4 border-t border-[#DCE0DA] pt-4 dark:border-white/10">
      {finished
        ? <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
            <button type="button" className={`${secondaryButtonClass} ${footerButtonShape} w-full sm:w-auto`} onClick={() => { setRows([emptyRow()]); requestAnimationFrame(() => firstField.current?.focus()); }}>{t(copy("batch_more"))}</button>
            <button type="button" className={`${primaryButtonClass} ${footerButtonShape} w-full sm:w-auto`} onClick={close}>{t(copy("batch_done"))}</button>
          </div>
        : <button type="submit" className={`${primaryButtonClass} ${footerButtonShape} w-full`} disabled={busy || blocked}>{sendLabel}</button>}
    </div>
  </form>;

  const title = t(copy("batch_title"));
  if (isBelowDesktop) return <BottomSheet isOpen onClose={close} title={title} closeLabel={t("common.close")} backLabel={t("common.back")} snaps={["full"]} initialSnap="full">{content}</BottomSheet>;
  return <CenteredDialog title={title} firstField={firstField} onClose={close}>{content}</CenteredDialog>;
}
