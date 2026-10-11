"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
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
  type BusinessOverview,
  type BusinessWorkspaceInfo,
  type ReceiptSummary,
} from "@/lib/business-api";
import { normalizeEnabledLanguage } from "@/lib/language-features";
import { withBusinessSpace, type BusinessDataSource } from "./business-data";
import { periodRange, type Period } from "./business-format";
import { useBusinessActions, type BusinessActions } from "./business-actions";
import BusinessSidebarNav from "./BusinessSidebarNav";
import BusinessCreateMenu from "./BusinessCreateMenu";
import BusinessPanel from "./BusinessPanel";
import BusinessHome from "./BusinessHome";
import ComposerAttachControl from "./ComposerAttachControl";
import ReceiptIntakeDialog, { type IntakeTarget } from "./ReceiptIntakeDialog";
import RecordExpenseDialog from "./RecordExpenseDialog";
import ManualCaptureDialog from "./ManualCaptureDialog";
import { useBusinessSearch } from "./useBusinessSearch";

export type BusinessPanelState =
  | { kind: "overview" }
  | { kind: "inbox" }
  | { kind: "expenses"; expenseId?: string }
  | { kind: "updates" }
  | { kind: "receipt"; receiptId: string }
  | { kind: "draft"; draftId: string };

type Records = {
  workspace: BusinessWorkspaceInfo | null;
  overview: BusinessOverview | null;
  inbox: ReceiptSummary[] | null;
  error: boolean;
};

export type BusinessContextValue = Readonly<{
  source: BusinessDataSource;
  records: Records;
  revision: number;
  reload: () => void;
  period: Period;
  setPeriod: (key: Period["key"]) => void;
  panel: BusinessPanelState;
  openPanel: (panel: BusinessPanelState) => void;
  actions: BusinessActions;
  bridge: ChatShellBridge | null;
  attachedReceipt: ReceiptSummary | null;
  clearAttachedReceipt: () => void;
}>;

const BusinessContext = createContext<BusinessContextValue | null>(null);

export function useBusiness(): BusinessContextValue {
  const value = useContext(BusinessContext);
  if (!value) throw new Error("useBusiness must be used inside BusinessWorkspaceProvider");
  return value;
}

const NO_ACCOUNTS: never[] = [];
const PANEL_KINDS = new Set(["overview", "inbox", "expenses", "updates"]);

// Read from the route's search params, not window.location: on a client-side
// navigation (the sign-in return path) this renders before the address bar moves.
function panelFromSearch(params: URLSearchParams): BusinessPanelState {
  const draftId = params.get("draft");
  if (draftId) return { kind: "draft", draftId };
  const receiptId = params.get("receipt");
  if (receiptId) return { kind: "receipt", receiptId };
  const view = params.get("view");
  if (view && PANEL_KINDS.has(view)) {
    return { kind: view as "overview" | "inbox" | "expenses" | "updates" };
  }
  return { kind: "overview" };
}

function shellViewFromSearch(params: URLSearchParams): ChatShellView {
  return params.has("conversation") || params.get("view") === "chat" ? "chat" : "workspace";
}

function writePanelToUrl(view: ChatShellView, panel: BusinessPanelState) {
  try {
    const url = new URL(window.location.href);
    url.searchParams.delete("view");
    url.searchParams.delete("receipt");
    url.searchParams.delete("draft");
    if (view === "workspace") {
      if (panel.kind === "receipt") url.searchParams.set("receipt", panel.receiptId);
      else if (panel.kind === "draft") url.searchParams.set("draft", panel.draftId);
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

export function BusinessWorkspaceProvider({
  source: apiSource,
  children,
}: {
  source: BusinessDataSource;
  children: ReactNode;
}) {
  const { t, i18n } = useTranslation();
  const searchParams = useSearchParams();
  const directRecord = searchParams.has("draft") || searchParams.has("receipt");
  const workspaceSource = useMemo(
    () => withBusinessSpace(apiSource, () => normalizeEnabledLanguage(i18n.language)),
    [apiSource, i18n],
  );
  const source = directRecord ? apiSource : workspaceSource;
  const [panel, setPanel] = useState<BusinessPanelState>(() =>
    panelFromSearch(new URLSearchParams(searchParams.toString())),
  );
  const [initialView] = useState<ChatShellView>(() =>
    shellViewFromSearch(new URLSearchParams(searchParams.toString())),
  );
  const [periodKey, setPeriodKey] = useState<Period["key"]>("this_month");
  const period = useMemo(() => periodRange(periodKey), [periodKey]);
  const [records, setRecords] = useState<Records>({
    workspace: null,
    overview: null,
    inbox: null,
    error: false,
  });
  const [revision, setRevision] = useState(0);
  const [bridge, setBridge] = useState<ChatShellBridge | null>(null);
  const [intakeTarget, setIntakeTarget] = useState<IntakeTarget | null>(null);
  const [recordExpenseOpen, setRecordExpenseOpen] = useState(false);
  const [captureOpen, setCaptureOpen] = useState(false);
  const [attachedReceipt, setAttachedReceipt] = useState<ReceiptSummary | null>(null);
  const drafts = useRef(new Map<string, string>());
  const [draftRevision, setDraftRevision] = useState(0);

  const reload = useCallback(() => setRevision((value) => value + 1), []);

  // A receipt saved from the composer belongs to the conversation it was added in.
  const conversationId = bridge?.conversationId ?? null;
  useEffect(() => {
    setAttachedReceipt(null);
  }, [conversationId]);

  useEffect(() => {
    let cancelled = false;
    if (directRecord) return;
    Promise.all([
      source.workspace(),
      source.overview(period.from, period.to),
      source.receipts("inbox"),
    ])
      .then(([workspace, overview, inbox]) => {
        if (!cancelled) setRecords({ workspace, overview, inbox, error: false });
      })
      .catch(() => {
        if (!cancelled) setRecords((current) => ({ ...current, error: true }));
      });
    return () => {
      cancelled = true;
    };
  }, [directRecord, period.from, period.to, revision, source]);

  // The shell may replace the route while leaving a conversation; writing again
  // once that navigation lands keeps the panel in the address bar.
  const search = searchParams.toString();
  useEffect(() => {
    if (bridge) writePanelToUrl(bridge.currentView, panel);
  }, [bridge, panel, search]);

  const openPanel = useCallback(
    (next: BusinessPanelState) => {
      setPanel(next);
      bridge?.showWorkspace();
    },
    [bridge],
  );

  const actions = useBusinessActions({
    records,
    bridge,
    openIntake: setIntakeTarget,
    openRecordExpense: () => setRecordExpenseOpen(true),
    openCapture: () => setCaptureOpen(true),
    openPanel,
  });

  const value = useMemo<BusinessContextValue>(
    () => ({
      source,
      records,
      revision,
      reload,
      period,
      setPeriod: setPeriodKey,
      panel,
      openPanel,
      actions,
      bridge,
      attachedReceipt,
      clearAttachedReceipt: () => setAttachedReceipt(null),
    }),
    [actions, attachedReceipt, bridge, openPanel, panel, period, records, reload, revision, source],
  );

  const chatAvailable = businessChatAvailable(records.workspace);
  const businessSearch = useBusinessSearch({
    source,
    chatAvailable,
    accounts: records.workspace?.accounts ?? NO_ACCOUNTS,
    openPanel,
    setPeriod: setPeriodKey,
  });

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
      profileInHeader: true,
      panelHasComposer: panel.kind === "overview",
      sidebarNav: (shell) => <BusinessSidebarNav shell={shell} />,
      sidebarFooter: (shell) => <BusinessCreateMenu shell={shell} />,
      headerActions: (shell) =>
        shell.isBelowTablet ? <BusinessCreateMenu shell={shell} compact /> : null,
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
  }, [actions.starterEntries, chatAvailable, composerPlaceholder, draftRevision, initialView, panel.kind, businessSearch]);

  return (
    <BusinessContext.Provider value={value}>
      <ChatWorkspaceProvider value={workspace}>
        {children}
        <ReceiptIntakeDialog
          target={intakeTarget}
          onClose={() => setIntakeTarget(null)}
          onCaptured={(captured, target) => {
            setIntakeTarget(null);
            reload();
            if (target === "composer") setAttachedReceipt(captured);
            else openPanel({ kind: "receipt", receiptId: captured.id });
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
