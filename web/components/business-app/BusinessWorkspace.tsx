"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from "react";
import CreateBusinessPreview from "@/app/design-workspace/CreateBusinessPreview";
import {createLocalBusinessPreviewSource,useLocalBusinessDirectory,localBusinessGrant,LOCAL_BUSINESS_EVENT} from "@/app/design-workspace/localBusinessPreview";
import { readStored, writeStored } from "@/lib/browser-storage";
import { useSearchParams } from "next/navigation";
import { useTranslation } from "react-i18next";
import {
  ChatWorkspaceProvider,
  type ChatShellBridge,
  type ChatShellView,
  type ChatWorkspace,
} from "@/components/chat/ChatWorkspace";
import {
  businessChatAvailable,
  type BusinessCapture,
  type BusinessOverview,
  type BusinessWorkspaceInfo,
  type GrantedSpace,
  type ReceiptSummary,
  type ReceiptActivityCounts,
} from "@/lib/business-api";
import { getChosenGrant, setChosenGrant, soleClientGrantId, subscribeChosenGrant } from "@/lib/business-grant";
import { classifyFailure, referenceCode, refusedForGood, runQuietRetries, sessionEndedLoginPath } from "@/lib/failure-screen";
import { normalizeEnabledLanguage } from "@/lib/language-features";
import { responsiveLayoutSnapshot, subscribeResponsiveLayout } from "@/lib/responsive-layout";
import { withBusinessSpace, type BusinessDataSource } from "./business-data";
import { periodRange, type Period, type PeriodKey } from "./business-format";
import { useBusinessActions, type BusinessActions } from "./business-actions";
import { clearTitleFocusUnless } from "./bandeja-order";
import BusinessSidebarNav, { BusinessSidebarFooter } from "./BusinessSidebarNav";
import WorkspaceSetupPreview from "@/app/design-workspace/WorkspaceSetupPreview";
import BusinessSwitcher, { BusinessMark } from "./BusinessSwitcher";
import { BusinessClosedAccess, BusinessClosedOwnerBanner } from "./BusinessLifecycleControls";
import type { ClosedGrantedSpace } from "@/lib/business-api";
import { ToastViewport } from "./foundation/ToastViewport";
import { clearToasts,showToast } from "./foundation/toasts";
import { BusinessReviewShortcutsProvider } from "./BusinessReviewShortcuts";
import { useBusinessKeyboardShortcuts } from "./business-keyboard-shortcuts";
import BusinessBottomTabs from "./BusinessBottomTabs";
import { PhoneSearchButton } from "./foundation/BusinessPhoneHeader";
import BusinessPanel from "./BusinessPanel";
import BusinessHome from "./BusinessHome";
import ComposerAttachControl from "./ComposerAttachControl";
import { ReceiptUploadQueue, composerUploadDisposition, type IntakeTarget } from "./receipt-upload-queue";
import ReceiptIntakeDialog from "./ReceiptIntakeDialog";
import ExportRecordsPanel from "./ExportRecordsPanel";
import { HandHeart } from "lucide-react";
import { Tooltip } from "@/components/ui/Tooltip";
import { AmountsToggle } from "./foundation/AmountsToggle";
import BusinessNotifications from "./foundation/BusinessNotifications";
import BusinessHeader from "./foundation/BusinessHeader";
import { useMonthCloseSource } from "./BusinessMonthClosePanel";
import { useReceiptInboxRefresh } from "./useReceiptInboxRefresh";
import { useBusinessSearch } from "./useBusinessSearch";
import { createReloadWaits } from "./list-reload";
import type { RefreshOutcome } from "@/components/ui/pull-to-refresh";
import { useEmailDeliveries } from "./useEmailDeliveries";
import { emailDeliveriesNeedRefresh, type BusinessEmailDelivery } from "@/lib/business-email";
import { canEnterBusiness } from "@/lib/business-privacy-notice";
import { useBusinessConsent } from "./business-consent-context";
import { quietButtonClass } from "./business-ui";
import { loadFailure, type BandejaSource, type LoadFailure } from "./bandeja-sources";
import { beginBusinessAppearance, failBusinessAppearance, getBusinessProfile, publishBusinessAppearance } from "@/lib/business-profile-api";

export type BusinessPanelState =
  | { kind: "overview" }
  | { kind: "inbox" }
  // Transacciones, the third screen: the period's saved records, or the bank's movements to igualar. `expenseId` is the record a phone comes back from.
  | { kind: "transactions"; expenseId?: string }
  | { kind: "expense"; expenseId: string }
  // Negocio: the business's own settings, one tab at a time; `?view=access` from before lands on Equipo y accesos.
  | { kind: "business"; tab?: BusinessTab }
  // `list` is the list the record was opened from; a desktop shows the record beside it. The address bar never carries it.
  | { kind: "receipt"; receiptId: string; list?: RecordList }
  | { kind: "draft"; draftId: string; list?: RecordList }
  // An email that brought no receipt, or the one a receipt arrived in; it opens beside the Bandeja.
  | { kind: "email"; emailId: string };

export type RecordList = "inbox" | "transactions";
export type BusinessTab = "datos" | "equipo" | "correo";
const BUSINESS_TABS = new Set<string>(["datos", "equipo", "correo"]);

type Records = {
  workspace: BusinessWorkspaceInfo | null;
  overview: BusinessOverview | null;
  inbox: ReceiptSummary[] | null;
  receiptActivity?: ReceiptActivityCounts | null;
  /** Saved notes, newest first; null until loaded or after a failed load. A notes outage never hides receipts, and never reads as no notes. */
  notes: BusinessCapture[] | null;
  notesFailure?: LoadFailure | null;
  /** The server says more notes exist past the page it sent; older open notes are found through search. */
  notesTruncated: boolean;
  /** Received emails, newest first; null until loaded. An email outage never hides receipts. */
  emails: BusinessEmailDelivery[] | null;
  emailsFailure?: LoadFailure | null;
  error: boolean;
  /** With error: the server refused this Business on purpose, so asking again cannot help. */
  refused?: boolean;
  closed?: boolean;
  serverReference?: string | null;
};

export type BusinessContextValue = Readonly<{
  source: BusinessDataSource;
  records: Records;
  /** Every Business the person may enter, the server's list; null until read. */
  spaces: GrantedSpace[] | null;
  closedSpaces?: ClosedGrantedSpace[];
  /** The Business the person is working in: their own unless they chose a client's. */
  chosen: GrantedSpace | null;
  chooseBusiness: (grantId: string | null) => void;
  renamePreviewBusiness?: (name: string) => void;
  /** The one-time access line for the chosen client Business was dismissed. */
  markAccessSeen: () => Promise<void>;
  /** The chosen grant stopped being live mid-session; the person is back in their own Business. */
  lostAccess: boolean;
  clearLostAccess: () => void;
  revision: number;
  reload: () => void;
  /** Reloads and settles once every list has answered, "failed" when any could not. */
  refresh: () => Promise<RefreshOutcome>;
  period: Period;
  setPeriod: (next: PeriodKey | Period) => void;
  panel: BusinessPanelState;
  openPanel: (panel: BusinessPanelState) => void;
  actions: BusinessActions;
  bridge: ChatShellBridge | null;
  attachedReceipt: ReceiptSummary | null;
  clearAttachedReceipt: () => void;
  /** Opens Exportar registros over whatever screen is showing. */
  openExport: () => void;
  /** Asks the server for the emails again; the Negocio history shows it working. */
  emailRefresh: Readonly<{ refresh: () => void; refreshing: boolean; stalled: boolean }>;
  /** Asks again for only the lists named; the rest stay as they are. */
  retrySources: (sources: readonly BandejaSource[]) => void;
}>;

/** Exported for DOM tests that mount one panel with a hand-made context; the app provides it through BusinessWorkspaceProvider. */
export const BusinessContext = createContext<BusinessContextValue | null>(null);

export function useBusiness(): BusinessContextValue {
  const value = useContext(BusinessContext);
  if (!value) throw new Error("useBusiness must be used inside BusinessWorkspaceProvider");
  return value;
}

const NO_ACCOUNTS: never[] = [];
// The captures endpoint's largest page; it has no cursor, so `has_more` sends the rest to search.
const NOTES_PAGE = 50;
const PANEL_KINDS = new Set(["overview", "inbox", "transactions"]);

// Read from the route's search params, not window.location: on a client-side
// navigation (the sign-in return path) this renders before the address bar moves.
function panelFromSearch(params: URLSearchParams): BusinessPanelState {
  const draftId = params.get("draft");
  if (draftId) return { kind: "draft", draftId };
  const emailId = params.get("email");
  if (emailId) return { kind: "email", emailId };
  const receiptId = params.get("receipt");
  if (receiptId) return { kind: "receipt", receiptId };
  const expenseId = params.get("expense");
  if (expenseId) return { kind: "expense", expenseId };
  const view = params.get("view");
  // Correos left the Bandeja; its history lives in Negocio > Correo de recibos.
  if (view === "inbox" && params.get("segment") === "emails") return { kind: "business", tab: "correo" };
  if (view && PANEL_KINDS.has(view)) {
    return { kind: view as "overview" | "inbox" | "transactions" };
  }
  // Gastos became Transacciones; an old link lands there.
  if (view === "expenses") return { kind: "transactions" };
  if (view === "business") {
    const tab = params.get("tab");
    return tab && BUSINESS_TABS.has(tab) ? { kind: "business", tab: tab as BusinessTab } : { kind: "business" };
  }
  if (view === "access") return { kind: "business", tab: "equipo" };
  // Novedades became part of the Bandeja; an old link lands there.
  if (view === "updates") return { kind: "inbox" };
  return { kind: "overview" };
}

const EMPTY_RECORDS: Records = {
  workspace: null,
  overview: null,
  inbox: null,
  receiptActivity: null,
  notes: null,
  notesFailure: null,
  notesTruncated: false,
  emails: null,
  emailsFailure: null,
  error: false,
  refused: false,
  closed: false,
  serverReference: null,
};

function shellViewFromSearch(params: URLSearchParams): ChatShellView {
  return params.has("conversation") || params.get("view") === "chat" ? "chat" : "workspace";
}

function writePanelToUrl(view: ChatShellView, panel: BusinessPanelState) {
  try {
    const url = new URL(window.location.href);
    url.searchParams.delete("view");
    url.searchParams.delete("receipt");
    url.searchParams.delete("draft");
    url.searchParams.delete("expense");
    url.searchParams.delete("email");
    url.searchParams.delete("segment");
    url.searchParams.delete("tab");
    if (view === "workspace") {
      if (panel.kind === "business" && panel.tab) url.searchParams.set("tab", panel.tab);
      if (panel.kind === "receipt") url.searchParams.set("receipt", panel.receiptId);
      else if (panel.kind === "draft") url.searchParams.set("draft", panel.draftId);
      else if (panel.kind === "expense") url.searchParams.set("expense", panel.expenseId);
      else if (panel.kind === "email") url.searchParams.set("email", panel.emailId);
      else if (panel.kind !== "overview") url.searchParams.set("view", panel.kind);
    } else if (view === "chat" && !url.searchParams.has("conversation")) {
      url.searchParams.set("view", "chat");
    }
    const next = `${url.pathname}${url.search}`;
    if (next !== `${window.location.pathname}${window.location.search}`) {
      window.history.replaceState(null, "", next);
    }
  } catch {
    // The address bar is a convenience; the shell state is the truth.
  }
}

function BusinessWorkspaceContent({
  source: apiSource,
  children,
}: {
  source: BusinessDataSource;
  children: ReactNode;
}) {
  const { t, i18n } = useTranslation();
  const searchParams = useSearchParams();
  const localPreview = apiSource.mode !== "live" && process.env.NODE_ENV === "development" && process.env.NEXT_PUBLIC_MOCK_AUTH === "true";
  const localBusinesses = useLocalBusinessDirectory(localPreview);
  const chosenGrant = useSyncExternalStore(subscribeChosenGrant, getChosenGrant, () => null);
  const [creatingBusiness,setCreatingBusiness] = useState(false);
  // A landing on a record URL (the sign-in return path) skips the space
  // bootstrap until the person leaves the record; opening a record later never
  // flips it, so a record's effects do not refetch on every address-bar write.
  // A desktop shows the record beside its list, so the list loads from the start.
  const [directRecord, setDirectRecord] = useState(() => (searchParams.has("draft") || searchParams.has("receipt")) && responsiveLayoutSnapshot().isBelowDesktop);
  const workspaceSource = useMemo(
    () => withBusinessSpace(apiSource, () => normalizeEnabledLanguage(i18n.language)),
    [apiSource, i18n],
  );
  const [panel, setPanel] = useState<BusinessPanelState>(() =>
    panelFromSearch(new URLSearchParams(searchParams.toString())),
  );
  // Derived, not the latch: the moment the person leaves the record the
  // workspace-scoped source is in effect, so the first fetch is already scoped.
  const onRecord = directRecord && (panel.kind === "receipt" || panel.kind === "draft");
  const scopedSource = onRecord ? apiSource : workspaceSource;
  const previewSourceFor = useMemo(() => createLocalBusinessPreviewSource(scopedSource), [scopedSource]);
  const source = localPreview ? previewSourceFor(chosenGrant) : scopedSource;
  const [initialView] = useState<ChatShellView>(() =>
    shellViewFromSearch(new URLSearchParams(searchParams.toString())),
  );
  useEffect(() => {
    if (directRecord && panel.kind !== "receipt" && panel.kind !== "draft") setDirectRecord(false);
  }, [directRecord, panel.kind]);
  useEffect(() => subscribeResponsiveLayout(() => {
    if (!responsiveLayoutSnapshot().isBelowDesktop) setDirectRecord(false);
  }), []);
  const [period, setPeriodState] = useState<Period>(() => periodRange("this_month"));
  const setPeriod = useCallback((next: PeriodKey | Period) => setPeriodState(typeof next === "string" ? periodRange(next) : next), []);
  const [records, setRecords] = useState<Records>(EMPTY_RECORDS);
  const [notesAttempt, setNotesAttempt] = useState(0);
  const [revision, setRevision] = useState(0);
  const [directorySpaces, setSpaces] = useState<GrantedSpace[] | null>(null);
  const [closedSpaces, setClosedSpaces] = useState<ClosedGrantedSpace[]>([]);
  const [closedAccess, setClosedAccess] = useState(false);
  const [accessRevision, setAccessRevision] = useState(0);
  const [lostAccess, setLostAccess] = useState(false);
  const clearLostAccess = useCallback(() => setLostAccess(false), []);
  const [invitationBusiness, setInvitationBusiness] = useState<string | null>(null);
  const [previewNames, setPreviewNames] = useState<Record<string, string>>({});
  useEffect(() => {
    if (!localPreview) return;
    try {
      const cached: unknown = JSON.parse(readStored("cuadrao-preview-business-names-v1") || "{}");
      if (cached && typeof cached === "object" && !Array.isArray(cached)) setPreviewNames(Object.fromEntries(Object.entries(cached).filter(([, name]) => typeof name === "string" && name.trim() && [...name].length <= 80)));
    } catch { /* A damaged preview cache leaves the source name intact. */ }
  }, [localPreview]);
  const spaces = useMemo(() => {
    if(!localPreview)return directorySpaces;
    if(directorySpaces===null&&!localBusinesses.length)return null;
    const directory=new Map([...(directorySpaces??[]),...localBusinesses.map(localBusinessGrant)].map(space=>[space.space_id,space]));
    return [...directory.values()].map(space=>previewNames[space.space_id]?{...space,name:previewNames[space.space_id]}:space);
  },[directorySpaces,localPreview,previewNames,localBusinesses]);
  const chosen = useMemo(() => spaces?.find(space => chosenGrant ? space.grant_id === chosenGrant : space.role === "owner") ?? null, [spaces, chosenGrant]);
  const appearanceBusinessId=chosen?.space_id;
  useEffect(()=>{
    if(source.mode!=="live"||!appearanceBusinessId)return;
    const controller=new AbortController();
    beginBusinessAppearance(appearanceBusinessId);
    getBusinessProfile(appearanceBusinessId,controller.signal).then(value=>publishBusinessAppearance(value,controller.signal),()=>{if(!controller.signal.aborted)failBusinessAppearance(appearanceBusinessId);}).catch(()=>{});
    return()=>controller.abort();
  },[source.mode,appearanceBusinessId,chosenGrant]);
  const renamePreviewBusiness = useCallback((name: string) => {
    if (!localPreview || !chosen || chosen.role !== "owner" || !name.trim() || [...name.trim()].length > 80) return;
    setPreviewNames(current => {
      const next = { ...current, [chosen.space_id]: name.trim() };
      writeStored("cuadrao-preview-business-names-v1", JSON.stringify(next));
      return next;
    });
  }, [chosen, localPreview]);
  const closedAccessName = closedAccess ? closedSpaces.find(space => space.grant_id === chosenGrant)?.name ?? chosen?.name ?? t("business.overview.title") : null;
  // The listing is the server's; a remembered choice it no longer holds falls back to the own Business.
  useEffect(() => {
    let cancelled = false;
    const directory = source.mode === "live" && source.spaceDirectory ? source.spaceDirectory() : source.spaces().then(listed => ({ spaces: listed, closed_spaces: [] }));
    directory.then(
      ({ spaces: listed, closed_spaces: closed }) => {
        if (cancelled) return;
        setSpaces(listed);
        setClosedSpaces(closed);
        const grant = getChosenGrant();
        const selected = listed.find(space => space.grant_id === grant);
        if (grant && !selected) {
          const held = closed.find(space => space.grant_id === grant);
          if (held) { setClosedAccess(true); return; }
          setChosenGrant(null);
          setLostAccess(true);
        } else if (!grant) {
          const sole = soleClientGrantId(listed);
          if (sole) {
            setChosenGrant(sole);
            setRevision((value) => value + 1);
          }
        }
      },
      () => { if (!cancelled) setSpaces((current) => current ?? []); },
    );
    return () => { cancelled = true; };
  }, [source, revision, accessRevision]);
  const markAccessSeen = useCallback(async () => {
    if (!chosen || chosen.role === "owner") return;
    await source.markAccessSeen(chosen.grant_id);
    setAccessRevision((value) => value + 1);
    setSpaces((current) => current?.map((space) => (space.grant_id === chosen.grant_id ? { ...space, access_seen: true } : space)) ?? current);
  }, [chosen, source]);
  const [bridge, setBridge] = useState<ChatShellBridge | null>(null);
  const [intakeTarget, setIntakeTarget] = useState<IntakeTarget | null>(null);
  const [attachedReceipt, setAttachedReceipt] = useState<ReceiptSummary | null>(null);
  // Switching Business closes whatever was open in the old one before the new
  // one loads: the open record and its address, the dialogs and their typed
  // text, the attached receipt, and every list. Nothing of A shows under B.
  const consent = useBusinessConsent();
  const chooseBusiness = useCallback((grantId: string | null) => {
    setInvitationBusiness(null);
    setCreatingBusiness(false);
    if (!canEnterBusiness(consent.accepted, grantId)) {
      consent.reopen();
      return;
    }
    if (grantId === getChosenGrant()) return;
    clearTitleFocusUnless();
    setLostAccess(false);
    setClosedAccess(false);
    setChosenGrant(grantId);
    setPanel({ kind: "overview" });
    writePanelToUrl("workspace", { kind: "overview" });
    setDirectRecord(false);
    setIntakeTarget(null);
    clearToasts();
    setAttachedReceipt(null);
    setRecords(EMPTY_RECORDS);
    setRevision((value) => value + 1);
  }, [consent]);
  const drafts = useRef(new Map<string, string>());
  const [draftRevision, setDraftRevision] = useState(0);

  const reload = useCallback(() => setRevision((value) => value + 1), []);
  const [reloadWaits] = useState(createReloadWaits);
  useEffect(() => reloadWaits.committed(revision), [reloadWaits, revision]);
  const refresh = useCallback(() => {
    reload();
    return reloadWaits.next();
  }, [reload, reloadWaits]);
  const emailsAnswered = useCallback((at: number, ok: boolean) => reloadWaits.answered("emails", at, ok), [reloadWaits]);

  // A receipt saved from the composer belongs to the conversation it was added in.
  const conversationId = bridge?.conversationId ?? null;
  useEffect(() => {
    setAttachedReceipt(null);
  }, [conversationId]);

  // One queue outlives the dialog: closing it never drops a running upload.
  const [uploadQueue] = useState(() => new ReceiptUploadQueue(
    (file, consent, key, documentType, onProgress) => runQuietRetries(() => source.uploadReceipt(file, consent, key, documentType, onProgress)),
    reload,
  ));
  useLayoutEffect(() => {
    uploadQueue.setOnSaved((receipt, origin) => {
      reload();
      const disposition = composerUploadDisposition(origin, { conversationId, intakeTarget });
      if (disposition !== "inbox") setAttachedReceipt(receipt);
      if (disposition === "attach_and_close") setIntakeTarget(null);
    });
  }, [uploadQueue, reload, conversationId, intakeTarget]);
  const uploads = useSyncExternalStore(uploadQueue.subscribe, uploadQueue.snapshot, uploadQueue.snapshot);
  useEffect(() => {
    if (!uploadQueue.unfinished) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [uploadQueue, uploads]);
  const openIntake = useCallback((target: IntakeTarget) => {
    // A new composer upload starts clean unless one is still in flight.
    if (target === "composer" && !uploadQueue.snapshot().some((item) => item.target === target && item.status !== "saved" && item.status !== "rejected")) uploadQueue.clear(target);
    setIntakeTarget(target);
  }, [uploadQueue]);

  useEffect(() => {
    let cancelled = false;
    if (onRecord) return;
    runQuietRetries(() => Promise.all([
      source.workspace(),
      source.overview(period.from, period.to),
      source.receiptPage?.("inbox") ?? source.receipts("inbox").then((items) => ({ items, activity: null })),
    ]))
      .then(([workspace, overview, page]) => {
        if (cancelled) return;
        setRecords((current) => ({ ...current, workspace, overview, inbox: page.items, receiptActivity: page.activity, error: false, refused: false, closed: false, serverReference: null }));
        reloadWaits.answered("records", revision, true);
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        const kind = classifyFailure(error, { fetch: true });
        if (kind === "business_closed") {
          setClosedAccess(true);
          reloadWaits.answered("records", revision, false);
          return;
        }
        if (kind === "removed" && getChosenGrant()) {
          setChosenGrant(null);
          setLostAccess(true);
          setRevision((value) => value + 1);
          return;
        }
        if (kind === "session_ended") {
          window.location.replace(sessionEndedLoginPath(window.location.pathname, window.location.search));
          return;
        }
        reloadWaits.answered("records", revision, false);
        if (kind === "closed") {
          setRecords((current) => ({ ...current, error: false, refused: false, closed: true, serverReference: null }));
          return;
        }
        if (refusedForGood(error)) {
          setRecords((current) => ({ ...current, error: true, refused: true, closed: false, serverReference: null }));
          return;
        }
        if (kind === "unavailable" || kind === "server") {
          setRecords((current) => ({ ...current, error: false, refused: false, closed: false, serverReference: referenceCode(error) }));
          return;
        }
        setRecords((current) => ({ ...current, error: true, refused: false, closed: false, serverReference: null }));
      });
    return () => {
      cancelled = true;
    };
  }, [onRecord, period.from, period.to, revision, source, reloadWaits]);

  const emailDeliveries = useEmailDeliveries({ source, enabled: !onRecord, revision, businessKey: chosenGrant, onAnswered: emailsAnswered });
  const workspaceRecords = useMemo<Records>(
    () => ({ ...records, emails: emailDeliveries.items, emailsFailure: emailDeliveries.failure }),
    [records, emailDeliveries.items, emailDeliveries.failure],
  );
  const emailRefresh = useMemo(
    () => ({ refresh: emailDeliveries.refresh, refreshing: emailDeliveries.refreshing, stalled: emailDeliveries.stalled }),
    [emailDeliveries.refresh, emailDeliveries.refreshing, emailDeliveries.stalled],
  );

  useReceiptInboxRefresh({
    source,
    active: !onRecord && panel.kind === "inbox" && bridge?.currentView !== "chat",
    reading: !onRecord && (records.receiptActivity?.reading_count ?? 0) > 0,
    businessKey: chosenGrant,
    onRefresh: (page) => {
      if (onRecord) return;
      setRecords((value) => ({ ...value, inbox: page.items, receiptActivity: page.activity }));
      // A long read outlasts the email poll; each receipt refresh asks again while an email is still moving.
      if (emailDeliveries.items && !emailDeliveries.refreshing && emailDeliveriesNeedRefresh(emailDeliveries.items)) emailDeliveries.refresh();
    },
  });

  useEffect(() => {
    let cancelled = false;
    if (onRecord) return;
    source.ensureSpace(normalizeEnabledLanguage(i18n.language)).then(() => {
      if (cancelled) return { items: [] };
      return source.captures("", NOTES_PAGE, "inbox");
    }).then(
      (page) => {
        if (cancelled) return;
        setRecords((current) => ({ ...current, notes: page.items, notesFailure: null, notesTruncated: page.has_more === true }));
        reloadWaits.answered("notes", revision, true);
      },
      (error: unknown) => {
        if (cancelled) return;
        setRecords((current) => ({ ...current, notes: null, notesFailure: loadFailure(error), notesTruncated: false }));
        reloadWaits.answered("notes", revision, false);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [onRecord, revision, notesAttempt, source, i18n, reloadWaits]);

  const retryEmails = emailDeliveries.refresh;
  const retrySources = useCallback((sources: readonly BandejaSource[]) => {
    if (sources.includes("notes")) setNotesAttempt((value) => value + 1);
    if (sources.includes("emails")) retryEmails();
  }, [retryEmails]);

  // The shell may replace the route while leaving a conversation; writing again
  // once that navigation lands keeps the panel in the address bar.
  const search = searchParams.toString();
  useEffect(() => {
    if (bridge) writePanelToUrl(bridge.currentView, panel);
  }, [bridge, panel, search]);

  const openPanel = useCallback(
    (next: BusinessPanelState) => {
      clearTitleFocusUnless(next.kind === "receipt" ? next.receiptId : undefined);
      setPanel(next);
      bridge?.showWorkspace();
    },
    [bridge],
  );

  const actions = useBusinessActions({
    records,
    bridge,
    openIntake,
    openPanel,
  });

  const [exportOpen, setExportOpen] = useState(false);
  const openExport = useCallback(() => setExportOpen(true), []);

  const value = useMemo<BusinessContextValue>(
    () => ({
      source,
      records: workspaceRecords,
      spaces,
      closedSpaces,
      chosen,
      chooseBusiness,
      renamePreviewBusiness: localPreview ? renamePreviewBusiness : undefined,
      markAccessSeen,
      lostAccess,
      clearLostAccess,
      revision,
      reload,
      refresh,
      period,
      setPeriod,
      panel,
      openPanel,
      actions,
      bridge,
      attachedReceipt,
      clearAttachedReceipt: () => setAttachedReceipt(null),
      openExport,
      emailRefresh,
      retrySources,
    }),
    [actions, attachedReceipt, bridge, chooseBusiness, chosen, localPreview, renamePreviewBusiness, clearLostAccess, emailRefresh, lostAccess, markAccessSeen, openExport, openPanel, panel, period, workspaceRecords, reload, refresh, retrySources, revision, setPeriod, source, spaces, closedSpaces],
  );

  const chatAvailable = businessChatAvailable(records.workspace) && consent.accepted && !closedAccessName;
  const businessSearch = useBusinessSearch({
    source,
    accounts: records.workspace?.accounts ?? NO_ACCOUNTS,
    openPanel,
    actions,
    owner: chosen?.role !== "accountant",
    scope: chosen?.space_id ?? "own",
    openExport,
  });

  const keyboardShortcuts = useBusinessKeyboardShortcuts({ openPanel, actions, chosen });
  const composerPlaceholder = records.workspace?.assistant_available
    ? t("business.composer.placeholder_ask", "Ask about your saved expenses")
    : t("business.composer.placeholder", "Write a message");
  const workspace = useMemo<ChatWorkspace>(() => {
    const draftKeyFor = (shell: ChatShellBridge) => shell.conversationId ?? "new";
    return {
      id: "business",
      conversationSurface: "business",
      chatAvailable,
      initialView,
      // The person's account sits at the top right on a desktop; the rail keeps the business and its screens.
      profileInHeader: true,
      keyboardShortcuts,
      bottomNavigation: (shell) => !closedAccessName && shell.isBelowTablet ? <BusinessBottomTabs shell={shell} /> : null,
      panelHasComposer: panel.kind === "overview" && !closedAccessName,
      sidebarNav: (shell) => closedAccessName ? null : <BusinessSidebarNav shell={shell} />,
      sidebarHeader: (shell) => shell.isBelowTablet ? null : <BusinessSwitcher spaces={spaces} closedSpaces={closedSpaces} chosen={chosen} collapsed={shell.sidebarCollapsed} onChoose={chooseBusiness} onOpenSettings={() => openPanel({ kind: "business" })} onInvite={localPreview ? () => setInvitationBusiness(chosen?.space_id ?? null) : () => openPanel({ kind: "business", tab: "equipo" })} memberEmail={shell.memberEmail} onAddBusiness={shell.memberEmail?()=>setCreatingBusiness(true):undefined} />,
      sidebarMark: () => <BusinessMark businessId={chosen?.space_id} name={chosen?.name} />,
      sidebarFooter: (shell) => shell.isBelowTablet ? null : <BusinessSidebarFooter shell={shell} />,
      headerLeading: (shell) => shell.isBelowTablet ? <BusinessSwitcher spaces={spaces} closedSpaces={closedSpaces} chosen={chosen} collapsed onChoose={chooseBusiness} onOpenSettings={() => openPanel({ kind: "business" })} onInvite={localPreview ? () => setInvitationBusiness(chosen?.space_id ?? null) : () => openPanel({ kind: "business", tab: "equipo" })} memberEmail={shell.memberEmail} onAddBusiness={shell.memberEmail?()=>setCreatingBusiness(true):undefined} /> : null,
      headerActions: (shell) => closedAccessName ? null : <>
        {uploads.length > 0 ? <button type="button" className={quietButtonClass} onClick={() => setIntakeTarget(uploads.find((item) => item.status !== "saved" && item.status !== "rejected")?.target ?? uploads[0].target)}>
          {t("business.intake.open_queue", "Uploads ({{count}})", { count: uploads.length })}
        </button> : null}
        {shell.isBelowTablet && shell.openSearch ? <PhoneSearchButton label={t("common.search", "Buscar")} onSearch={shell.openSearch} /> : null}
        {localPreview && !shell.isBelowTablet && shell.openPersonalInvitation ? <Tooltip content={t("cuadrao_invitation.title")} side="bottom">
          <button type="button" data-testid="personal-invitation-shortcut" aria-label={t("cuadrao_invitation.title")} aria-haspopup="dialog" onClick={(event) => shell.openPersonalInvitation?.(event.currentTarget)} className="flex h-11 w-11 items-center justify-center rounded-full text-[#56635e] transition-colors hover:bg-[#e3ebe1] hover:text-[#172b26] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f5a49] dark:text-white/70 dark:hover:bg-white/10 dark:hover:text-white dark:focus-visible:outline-[#8fcbb0]">
            <HandHeart className="h-5 w-5" aria-hidden="true" />
          </button>
        </Tooltip> : null}
        <AmountsToggle />
        <BusinessNotifications key={chosen?.space_id} businessId={chosen?.space_id} businessName={chosen?.name} preview={localPreview} onInvitationAccepted={grantId=>{chooseBusiness(grantId);reload();showToast({kind:"success",text:t("business_access.invitation_accepted")});}} onAction={(tab) => openPanel({ kind: "business", tab })} />
      </>,
      headerSearch: (shell) => <BusinessHeader home={shell.currentView === "workspace" && panel.kind === "overview" && !closedAccessName} name={shell.greetingName} title={shell.currentView === "workspace" && !closedAccessName ? panel.kind === "transactions" ? t("business.transactions.title") : panel.kind === "inbox" ? t("business.inbox.title") : undefined : undefined} onSearch={shell.openSearch} />,
      panel: () => closedAccessName ? <BusinessClosedAccess returnHome={!spaces?.length} businessName={closedAccessName} onReturn={() => { setClosedAccess(false); if (!spaces?.length) window.location.assign("/"); else chooseBusiness(spaces.find(space => space.role === "owner") ? null : spaces[0].grant_id); }} /> : <><BusinessClosedOwnerBanner businesses={closedSpaces} /><BusinessPanel /></>,
      starterEntries: () => actions.starterEntries,
      emptyChatLead: () => <BusinessHome variant="new_chat" />,
      search: businessSearch,
      composer: (shell) => {
        const key = draftKeyFor(shell);
        return {
          leadingControl: <ComposerAttachControl />,
          placeholder: composerPlaceholder,
          draftText: drafts.current.get(key) ?? null,
          draftKey: `business-composer-${key}-${draftRevision}`,
          onDraftChange: (text) => {
            drafts.current.set(key, text);
          },
          replaceDraft: (text) => {
            drafts.current.set(key, text);
            setDraftRevision((value) => value + 1);
          },
          onSent: () => setAttachedReceipt(null),
        };
      },
      onShellChange: (shell) => setBridge(shell),
    };
  }, [keyboardShortcuts, actions.starterEntries, chatAvailable, composerPlaceholder, draftRevision, initialView, panel.kind, businessSearch, uploads, t, spaces, closedSpaces, closedAccessName, chosen, chooseBusiness, openPanel, localPreview,reload]);

  return (
    <BusinessContext.Provider value={value}>
      <ChatWorkspaceProvider value={workspace}>
        {children}
        {creatingBusiness?<CreateBusinessPreview accountKey={bridge?.memberEmail??""} live={source.mode==="live"} onClose={()=>setCreatingBusiness(false)} onCreated={business=>{setCreatingBusiness(false);window.dispatchEvent(new Event(LOCAL_BUSINESS_EVENT));chooseBusiness(business.grant_id??business.id);reload();openPanel({kind:"business",tab:"datos"});showToast({kind:"success",text:t("identity.business_created",{name:business.name})});}}/>:null}
        {localPreview && chosen?.role === "owner" && invitationBusiness === chosen.space_id ? <WorkspaceSetupPreview invitation onClose={() => setInvitationBusiness(null)} /> : null}
        <ReceiptIntakeDialog
          target={intakeTarget}
          queue={uploadQueue}
          onClose={() => {
            if (intakeTarget) uploadQueue.clearSettled(intakeTarget);
            setIntakeTarget(null);
          }}
          onReview={(saved) => {
            setIntakeTarget(null);
            openPanel(saved.length === 1 ? { kind: "receipt", receiptId: saved[0].id } : { kind: "inbox" });
          }}
        />
        {exportOpen ? <WorkspaceExport onClose={() => setExportOpen(false)} /> : null}
        <ToastViewport />
      </ChatWorkspaceProvider>
    </BusinessContext.Provider>
  );
}

export function BusinessWorkspaceProvider(props: { source: BusinessDataSource; children: ReactNode }) {
  return <BusinessReviewShortcutsProvider><BusinessWorkspaceContent {...props} /></BusinessReviewShortcutsProvider>;
}

/** The one Exportar registros, opened from the top bar's menu or from search over any screen. */
function WorkspaceExport({ onClose }: { onClose: () => void }) {
  const monthClose = useMonthCloseSource();
  return <ExportRecordsPanel monthClose={monthClose} onClose={onClose} />;
}
