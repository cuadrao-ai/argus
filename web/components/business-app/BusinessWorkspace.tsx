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
import { getChosenGrant, grantNotLive, setChosenGrant, subscribeChosenGrant } from "@/lib/business-grant";
import { normalizeEnabledLanguage } from "@/lib/language-features";
import { withBusinessSpace, type BusinessDataSource } from "./business-data";
import { periodRange, type Period, type PeriodKey } from "./business-format";
import { useBusinessActions, type BusinessActions } from "./business-actions";
import { clearTitleFocusUnless } from "./bandeja-order";
import BusinessSidebarNav from "./BusinessSidebarNav";
import BusinessSwitcher from "./BusinessSwitcher";
import { BusinessReviewShortcutsProvider } from "./BusinessReviewShortcuts";
import { useBusinessKeyboardShortcuts } from "./business-keyboard-shortcuts";
import BusinessBottomTabs from "./BusinessBottomTabs";
import BusinessPanel from "./BusinessPanel";
import BusinessHome from "./BusinessHome";
import ComposerAttachControl from "./ComposerAttachControl";
import { ReceiptUploadQueue, composerUploadDisposition, type IntakeTarget } from "./receipt-upload-queue";
import ReceiptIntakeDialog from "./ReceiptIntakeDialog";
import RecordExpenseDialog from "./RecordExpenseDialog";
import ManualCaptureDialog from "./ManualCaptureDialog";
import { useReceiptInboxRefresh } from "./useReceiptInboxRefresh";
import { useBusinessSearch } from "./useBusinessSearch";

export type BusinessPanelState =
  | { kind: "overview" }
  | { kind: "inbox"; emailId?: string }
  | { kind: "expenses"; expenseId?: string }
  | { kind: "expense"; expenseId: string }
  | { kind: "updates" }
  | { kind: "access" }
  | { kind: "receipt"; receiptId: string }
  | { kind: "draft"; draftId: string };

type Records = {
  workspace: BusinessWorkspaceInfo | null;
  overview: BusinessOverview | null;
  inbox: ReceiptSummary[] | null;
  receiptActivity?: ReceiptActivityCounts | null;
  /** Saved notes, newest first; null until loaded. A notes outage never hides receipts. */
  notes: BusinessCapture[] | null;
  notesError: boolean;
  /** The captures list stops at the server's page size; older open notes are found through search. */
  notesTruncated: boolean;
  error: boolean;
};

export type BusinessContextValue = Readonly<{
  source: BusinessDataSource;
  records: Records;
  /** Every Business the person may enter, the server's list; null until read. */
  spaces: GrantedSpace[] | null;
  /** The Business the person is working in: their own unless they chose a client's. */
  chosen: GrantedSpace | null;
  chooseBusiness: (grantId: string | null) => void;
  /** The one-time access line for the chosen client Business was dismissed. */
  markAccessSeen: () => Promise<void>;
  /** The chosen grant stopped being live mid-session; the person is back in their own Business. */
  lostAccess: boolean;
  revision: number;
  reload: () => void;
  period: Period;
  setPeriod: (next: PeriodKey | Period) => void;
  panel: BusinessPanelState;
  openPanel: (panel: BusinessPanelState) => void;
  actions: BusinessActions;
  bridge: ChatShellBridge | null;
  attachedReceipt: ReceiptSummary | null;
  clearAttachedReceipt: () => void;
}>;

/** Exported for DOM tests that mount one panel with a hand-made context; the app provides it through BusinessWorkspaceProvider. */
export const BusinessContext = createContext<BusinessContextValue | null>(null);

export function useBusiness(): BusinessContextValue {
  const value = useContext(BusinessContext);
  if (!value) throw new Error("useBusiness must be used inside BusinessWorkspaceProvider");
  return value;
}

const NO_ACCOUNTS: never[] = [];
// The captures endpoint's largest page; it has no cursor.
const NOTES_PAGE = 50;
const PANEL_KINDS = new Set(["overview", "inbox", "expenses", "updates", "access"]);

// Read from the route's search params, not window.location: on a client-side
// navigation (the sign-in return path) this renders before the address bar moves.
function panelFromSearch(params: URLSearchParams): BusinessPanelState {
  const draftId = params.get("draft");
  if (draftId) return { kind: "draft", draftId };
  const receiptId = params.get("receipt");
  if (receiptId) return { kind: "receipt", receiptId };
  const expenseId = params.get("expense");
  if (expenseId) return { kind: "expense", expenseId };
  const view = params.get("view");
  if (view && PANEL_KINDS.has(view)) {
    return { kind: view as "overview" | "inbox" | "expenses" | "updates" | "access" };
  }
  return { kind: "overview" };
}

const EMPTY_RECORDS: Records = {
  workspace: null,
  overview: null,
  inbox: null,
  receiptActivity: null,
  notes: null,
  notesError: false,
  notesTruncated: false,
  error: false,
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
    if (view === "workspace") {
      if (panel.kind === "receipt") url.searchParams.set("receipt", panel.receiptId);
      else if (panel.kind === "draft") url.searchParams.set("draft", panel.draftId);
      else if (panel.kind === "expense") url.searchParams.set("expense", panel.expenseId);
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
  // A landing on a record URL (the sign-in return path) skips the space
  // bootstrap until the person leaves the record; opening a record later never
  // flips it, so a record's effects do not refetch on every address-bar write.
  const [directRecord, setDirectRecord] = useState(() => searchParams.has("draft") || searchParams.has("receipt"));
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
  const source = onRecord ? apiSource : workspaceSource;
  const [initialView] = useState<ChatShellView>(() =>
    shellViewFromSearch(new URLSearchParams(searchParams.toString())),
  );
  useEffect(() => {
    if (directRecord && panel.kind !== "receipt" && panel.kind !== "draft") setDirectRecord(false);
  }, [directRecord, panel.kind]);
  const [period, setPeriodState] = useState<Period>(() => periodRange("this_month"));
  const setPeriod = useCallback((next: PeriodKey | Period) => setPeriodState(typeof next === "string" ? periodRange(next) : next), []);
  const [records, setRecords] = useState<Records>(EMPTY_RECORDS);
  const [revision, setRevision] = useState(0);
  // The chosen Business: a grant id the client remembers, proven by the server on every request.
  const chosenGrant = useSyncExternalStore(subscribeChosenGrant, getChosenGrant, () => null);
  const [spaces, setSpaces] = useState<GrantedSpace[] | null>(null);
  const [accessRevision, setAccessRevision] = useState(0);
  const [lostAccess, setLostAccess] = useState(false);
  const chosen = useMemo(
    () => spaces?.find((space) => (chosenGrant ? space.grant_id === chosenGrant : space.role === "owner")) ?? null,
    [spaces, chosenGrant],
  );
  // The listing is the server's; a remembered choice it no longer holds falls back to the own Business.
  useEffect(() => {
    let cancelled = false;
    source.spaces().then(
      (listed) => {
        if (cancelled) return;
        setSpaces(listed);
        const grant = getChosenGrant();
        if (grant && !listed.some((space) => space.grant_id === grant && space.role !== "owner")) {
          setChosenGrant(null);
          setLostAccess(true);
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
  const [recordExpenseOpen, setRecordExpenseOpen] = useState(false);
  const [captureOpen, setCaptureOpen] = useState(false);
  const [attachedReceipt, setAttachedReceipt] = useState<ReceiptSummary | null>(null);
  // Switching Business closes whatever was open in the old one before the new
  // one loads: the open record and its address, the dialogs and their typed
  // text, the attached receipt, and every list. Nothing of A shows under B.
  const chooseBusiness = useCallback((grantId: string | null) => {
    if (grantId === getChosenGrant()) return;
    clearTitleFocusUnless();
    setLostAccess(false);
    setChosenGrant(grantId);
    setPanel({ kind: "overview" });
    writePanelToUrl("workspace", { kind: "overview" });
    setDirectRecord(false);
    setIntakeTarget(null);
    setRecordExpenseOpen(false);
    setCaptureOpen(false);
    setAttachedReceipt(null);
    setRecords(EMPTY_RECORDS);
    setRevision((value) => value + 1);
  }, []);
  const drafts = useRef(new Map<string, string>());
  const [draftRevision, setDraftRevision] = useState(0);

  const reload = useCallback(() => setRevision((value) => value + 1), []);

  // A receipt saved from the composer belongs to the conversation it was added in.
  const conversationId = bridge?.conversationId ?? null;
  useEffect(() => {
    setAttachedReceipt(null);
  }, [conversationId]);

  // One queue outlives the dialog: closing it never drops a running upload.
  const [uploadQueue] = useState(() => new ReceiptUploadQueue(source.uploadReceipt, reload));
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
    Promise.all([
      source.workspace(),
      source.overview(period.from, period.to),
      source.receiptPage?.("inbox") ?? source.receipts("inbox").then((items) => ({ items, activity: null })),
    ])
      .then(([workspace, overview, page]) => {
        if (!cancelled) setRecords((current) => ({ ...current, workspace, overview, inbox: page.items, receiptActivity: page.activity, error: false }));
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        if (grantNotLive(error) && getChosenGrant()) {
          // The grant stopped being live mid-session: back to the own Business, said so.
          setChosenGrant(null);
          setLostAccess(true);
          setRevision((value) => value + 1);
          return;
        }
        setRecords((current) => ({ ...current, error: true }));
      });
    return () => {
      cancelled = true;
    };
  }, [onRecord, period.from, period.to, revision, source]);

  useReceiptInboxRefresh({
    source,
    active: !onRecord && panel.kind === "inbox" && bridge?.currentView !== "chat",
    reading: !onRecord && (records.receiptActivity?.reading_count ?? 0) > 0,
    businessKey: chosenGrant,
    onRefresh: (page) => { if (!onRecord) setRecords((value) => ({ ...value, inbox: page.items, receiptActivity: page.activity })); },
  });

  useEffect(() => {
    let cancelled = false;
    if (onRecord) return;
    source.ensureSpace(normalizeEnabledLanguage(i18n.language)).then(() => {
      if (cancelled) return [];
      return source.captures("", NOTES_PAGE, "inbox");
    }).then(
      (notes) => {
        if (!cancelled) setRecords((current) => ({ ...current, notes, notesError: false, notesTruncated: notes.length >= NOTES_PAGE }));
      },
      () => {
        if (!cancelled) setRecords((current) => ({ ...current, notes: [], notesError: true, notesTruncated: false }));
      },
    );
    return () => {
      cancelled = true;
    };
  }, [onRecord, revision, source, i18n]);

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
    openRecordExpense: () => setRecordExpenseOpen(true),
    openCapture: () => setCaptureOpen(true),
    openPanel,
  });

  const value = useMemo<BusinessContextValue>(
    () => ({
      source,
      records,
      spaces,
      chosen,
      chooseBusiness,
      markAccessSeen,
      lostAccess,
      revision,
      reload,
      period,
      setPeriod,
      panel,
      openPanel,
      actions,
      bridge,
      attachedReceipt,
      clearAttachedReceipt: () => setAttachedReceipt(null),
    }),
    [actions, attachedReceipt, bridge, chooseBusiness, chosen, lostAccess, markAccessSeen, openPanel, panel, period, records, reload, revision, setPeriod, source, spaces],
  );

  const chatAvailable = businessChatAvailable(records.workspace);
  const businessSearch = useBusinessSearch({
    source,
    chatAvailable,
    accounts: records.workspace?.accounts ?? NO_ACCOUNTS,
    openPanel,
    setPeriod,
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
      profileInHeader: false,
      keyboardShortcuts,
      bottomNavigation: (shell) => shell.isBelowTablet ? <BusinessBottomTabs shell={shell} /> : null,
      panelHasComposer: panel.kind === "overview",
      sidebarNav: (shell) => <BusinessSidebarNav shell={shell} />,
      sidebarFooter: (shell) => <BusinessSwitcher spaces={spaces} chosen={chosen} collapsed={shell.sidebarCollapsed} onChoose={chooseBusiness} onAccess={() => openPanel({ kind: "access" })} />,
      headerActions: () => <>
        {uploads.length > 0 ? <button type="button" className="min-h-11 rounded-full px-3 text-sm text-black/70 hover:bg-black/[0.04] dark:text-white/70 dark:hover:bg-white/[0.06]" onClick={() => setIntakeTarget(uploads.find((item) => item.status !== "saved" && item.status !== "rejected")?.target ?? uploads[0].target)}>
          {t("business.intake.open_queue", "Uploads ({{count}})", { count: uploads.length })}
        </button> : null}
      </>,
      panel: () => <BusinessPanel />,
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
  }, [keyboardShortcuts, actions.starterEntries, chatAvailable, composerPlaceholder, draftRevision, initialView, panel.kind, businessSearch, uploads, t, spaces, chosen, chooseBusiness, openPanel]);

  return (
    <BusinessContext.Provider value={value}>
      <ChatWorkspaceProvider value={workspace}>
        {children}
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
        <RecordExpenseDialog
          isOpen={recordExpenseOpen}
          onClose={() => setRecordExpenseOpen(false)}
          onRecorded={() => {
            setRecordExpenseOpen(false);
            reload();
            openPanel({ kind: "expenses" });
          }}
        />
        <ManualCaptureDialog isOpen={captureOpen} onClose={() => setCaptureOpen(false)} onSaved={(dossier) => {
          setCaptureOpen(false);
          reload();
          openPanel({ kind: "draft", draftId: dossier.draft_id });
        }} />
      </ChatWorkspaceProvider>
    </BusinessContext.Provider>
  );
}

export function BusinessWorkspaceProvider(props: { source: BusinessDataSource; children: ReactNode }) {
  return <BusinessReviewShortcutsProvider><BusinessWorkspaceContent {...props} /></BusinessReviewShortcutsProvider>;
}
