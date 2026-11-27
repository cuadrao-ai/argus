"use client";

import { useEffect, useEffectEvent, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { z } from "zod";
import { discoverBusinessTransfers, requestBusinessTransfer, respondToBusinessTransfer, type BusinessTransferDetails } from "@/lib/business-transfer-api";
import { businessLifecycleErrorKey, getOwnedBusinessSpaces, type OwnedBusiness } from "@/lib/business-lifecycle-api";
import { browserAuthGeneration, requireBrowserAuthGeneration } from "@/lib/browser-auth-generation";
import { serverRequestReference } from "@/lib/failure-screen";
import { personName } from "@/lib/person-name";
import { businessLifecycleControlsEnabled } from "@/lib/private-alpha-flags";
import { randomId } from "@/lib/random-id";
import BusinessTransferDialog, { type BusinessTransferView } from "./BusinessTransferDialog";
import type { BusinessCloseState } from "./BusinessCloseDialog";
import { useBusiness } from "./BusinessWorkspace";
import { formatBusinessName } from "./business-format";
import { showToast } from "./foundation/toasts";

type Target = { transferId?: string; startSpaceId?: string };
type Subject = "business" | "transfer";
type Entry =
  | { kind: "loading" }
  | { kind: "unavailable"; of: Subject }
  | { kind: "failed"; of: Subject; reference: string | null }
  | { kind: "request"; business: OwnedBusiness }
  | { kind: "transfer"; transfer: BusinessTransferDetails };
type Answer = "accept" | "decline" | "withdraw";

/** What the server says once an answer landed, and the toast that confirms it. */
const ANSWERED: Record<Answer, { status: BusinessTransferDetails["status"]; toast: string }> = {
  accept: { status: "accepted", toast: "business.lifecycle.transfer.accepted" },
  decline: { status: "declined", toast: "business.lifecycle.transfer.declined_recipient" },
  withdraw: { status: "cancelled", toast: "business.lifecycle.transfer.cancelled" },
};

const errorCode = (error: unknown) => (typeof error === "object" && error !== null && "code" in error ? error.code : null);
const errorStatus = (error: unknown) => (typeof error === "object" && error !== null && "status" in error ? error.status : null);

/**
 * A transfer of the Business, over the app: the owner's start (the Dueño
 * card's link) or the link in the email. Off with the lifecycle switch.
 */
export default function BusinessTransferEntry(target: Target) {
  if (!businessLifecycleControlsEnabled()) return null;
  return <BusinessTransfer {...target} />;
}

function BusinessTransfer({ transferId, startSpaceId }: Target) {
  const { t } = useTranslation();
  const { chosen, chooseBusiness, openPanel, reload } = useBusiness();
  const [entry, setEntry] = useState<Entry>({ kind: "loading" });
  const [command, setCommand] = useState<BusinessCloseState>({ kind: "idle" });
  const [unconfirmed, setUnconfirmed] = useState<Answer | null>(null);
  const [read, setRead] = useState<{ attempt: number; settles: Answer | null }>({ attempt: 0, settles: null });
  const [open, setOpen] = useState(true);
  const busy = useRef(false);
  const journal = useRef<{ input: string; key: string } | null>(null);
  // The transfer this dialog shows: the link's, or the one the owner's start found or made.
  const followed = useRef(transferId);

  const close = () => setOpen(false);
  // A closed dialog leaves no transfer address behind. Closing also spends the dialog's
  // own history entry, which lands on the address it opened over, so that one is cleaned too.
  useEffect(() => {
    if (open) return undefined;
    const clean = () => {
      const url = new URL(window.location.href);
      const stale = ["transfer", ...(startSpaceId ? ["lifecycle", "business"] : [])].filter(name => url.searchParams.has(name));
      if (!stale.length) return;
      stale.forEach(name => url.searchParams.delete(name));
      window.history.replaceState(window.history.state, "", `${url.pathname}${url.search}`);
    };
    clean();
    window.addEventListener("popstate", clean);
    return () => window.removeEventListener("popstate", clean);
  }, [open, startSpaceId]);
  const finish = (answer: Answer, transfer: BusinessTransferDetails) => {
    close();
    if (answer === "accept") { chooseBusiness(transfer.grant_id); reload(); }
    showToast({ kind: "success", text: t(ANSWERED[answer].toast) });
  };
  // Entering the Business the person is already in would only reload the page behind the dialog.
  const enter = (spaceId: string, grantId: string) => { if (chosen?.space_id !== spaceId) chooseBusiness(grantId); };
  const onRead = useEffectEvent((next: Entry, settles: Answer | null) => {
    busy.current = false;
    setCommand({ kind: "idle" });
    setUnconfirmed(null);
    if (next.kind === "request") enter(next.business.space_id, next.business.grant_id);
    if (next.kind === "transfer") {
      const { transfer } = next;
      followed.current = transfer.id;
      if (settles && transfer.status === ANSWERED[settles].status) { finish(settles, transfer); return; }
      // The recipient stays where they were until they accept.
      if (transfer.role === "owner" || transfer.status === "accepted") enter(transfer.space_id, transfer.grant_id);
    }
    // The owner's start opens over Negocio, where its card is.
    if (startSpaceId && (next.kind === "request" || next.kind === "transfer")) openPanel({ kind: "business", tab: "datos" });
    setEntry(next);
  });

  useEffect(() => {
    const controller = new AbortController();
    if (!open) return () => controller.abort();
    const generation = browserAuthGeneration();
    const of: Subject = followed.current ? "transfer" : "business";
    if (!z.uuid().safeParse(followed.current ?? startSpaceId).success) { setEntry({ kind: "unavailable", of }); return () => controller.abort(); }
    setEntry({ kind: "loading" });
    const load = async (): Promise<Entry> => {
      if (followed.current) {
        const transfer = (await discoverBusinessTransfers(controller.signal)).find(item => item.id === followed.current);
        return transfer ? { kind: "transfer", transfer } : { kind: "unavailable", of };
      }
      const business = (await getOwnedBusinessSpaces(controller.signal)).find(space => space.space_id === startSpaceId);
      if (!business) return { kind: "unavailable", of };
      const pending = (await discoverBusinessTransfers(controller.signal)).find(item => item.space_id === startSpaceId && item.status === "pending");
      return pending ? { kind: "transfer", transfer: pending } : { kind: "request", business };
    };
    void load().then(next => {
      requireBrowserAuthGeneration(generation);
      if (!controller.signal.aborted) onRead(next, read.settles);
    }).catch(error => {
      if (controller.signal.aborted || browserAuthGeneration() !== generation) return;
      const gone = errorStatus(error) === 403 || errorStatus(error) === 404 || businessLifecycleErrorKey(error, "discovery").endsWith("business_unavailable");
      setEntry(gone ? { kind: "unavailable", of } : { kind: "failed", of, reference: serverRequestReference(error) });
    });
    return () => controller.abort();
  }, [startSpaceId, read, open]);

  if (!open) return null;

  const request = async (business: OwnedBusiness, targetGrantId: string, confirmation: string) => {
    if (busy.current) return;
    busy.current = true;
    const generation = browserAuthGeneration();
    // An unconfirmed request is checked with the key it was sent with.
    const input = JSON.stringify([business.space_id, confirmation, targetGrantId]);
    if (journal.current?.input !== input) journal.current = { input, key: randomId() };
    setCommand({ kind: "submitting" });
    try {
      const made = await requestBusinessTransfer({ spaceId: business.space_id, confirmation, targetGrantId, idempotencyKey: journal.current.key });
      const transfer = (await discoverBusinessTransfers()).find(item => item.id === made.id);
      requireBrowserAuthGeneration(generation);
      if (!transfer) throw new Error("business_transfer_not_listed");
      followed.current = transfer.id;
      busy.current = false;
      setCommand({ kind: "idle" });
      setEntry({ kind: "transfer", transfer });
    } catch (error) {
      if (browserAuthGeneration() !== generation) return;
      busy.current = false;
      setCommand({ kind: "error", message: t(businessLifecycleErrorKey(error, "request_uncertain")), reference: serverRequestReference(error), field: errorCode(error) === "business_name_mismatch" ? "confirmation" : undefined });
      if (errorCode(error) === "business_transfer_target_invalid") {
        void getOwnedBusinessSpaces().then(spaces => {
          requireBrowserAuthGeneration(generation);
          const refreshed = spaces.find(space => space.space_id === business.space_id);
          setEntry(refreshed ? { kind: "request", business: refreshed } : { kind: "unavailable", of: "business" });
        }).catch(() => undefined);
      }
    }
  };
  const answer = async (action: Answer, transfer: BusinessTransferDetails) => {
    if (busy.current) return;
    busy.current = true;
    const generation = browserAuthGeneration();
    setCommand({ kind: "submitting" });
    try {
      await respondToBusinessTransfer({ transferId: transfer.id, action });
      requireBrowserAuthGeneration(generation);
      finish(action, transfer);
    } catch (error) {
      if (browserAuthGeneration() !== generation) return;
      // The answer may have landed: the only next step reads the server, never sends it twice.
      setCommand({ kind: "error", message: t(businessLifecycleErrorKey(error, `${action}_uncertain`)), reference: serverRequestReference(error) });
      setUnconfirmed(action);
    }
  };

  const fallbackName = t("business.overview.title", "My business");
  let view: BusinessTransferView;
  if (entry.kind === "loading" || entry.kind === "unavailable") view = entry;
  else if (entry.kind === "failed") view = { ...entry, onRetry: () => setRead(current => ({ ...current, attempt: current.attempt + 1 })) };
  else if (entry.kind === "request") {
    const { business } = entry;
    view = { kind: "request", businessName: formatBusinessName(business.name, fallbackName), members: business.members, onRequest: (grantId, confirmation) => { void request(business, grantId, confirmation); } };
  } else {
    const { transfer } = entry;
    const owner = transfer.role === "owner";
    const businessName = formatBusinessName(transfer.business_name, fallbackName);
    const targetName = personName(t, { display_name: transfer.target_name, email: transfer.target_email, shown_as: transfer.target_shown_as });
    if (transfer.status === "pending") view = owner
      ? { kind: "pending", expiresAt: transfer.expires_at, targetName, onWithdraw: () => { void answer("withdraw", transfer); } }
      : { kind: "recipient", businessName, expiresAt: transfer.expires_at, ownerName: personName(t, { display_name: transfer.owner_name, email: transfer.owner_email, shown_as: transfer.owner_shown_as }), onAccept: () => { void answer("accept", transfer); }, onDecline: () => { void answer("decline", transfer); } };
    else if (transfer.status === "accepted") view = { kind: "accepted" };
    else if (transfer.status === "declined") view = owner ? { kind: "declined", businessName, targetName } : { kind: "declinedRecipient" };
    else if (transfer.status === "expired") view = owner ? { kind: "expired", targetName } : { kind: "expiredLink" };
    else view = owner ? { kind: "cancelled" } : { kind: "unavailable", of: "transfer" };
  }
  return <BusinessTransferDialog view={view} state={command} onDismiss={close} onRefresh={unconfirmed ? () => { setCommand({ kind: "idle" }); setRead(current => ({ attempt: current.attempt + 1, settles: unconfirmed })); } : undefined} />;
}
