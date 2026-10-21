"use client";

import { withViewportPortal } from "@/components/ui/withViewportPortal";

import { conversationPreviewText } from "@/lib/conversation-preview-display";

import {
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";
import {
  ChevronRight,
  Loader2,
  MessageSquareWarning,
  Search,
  X,
} from "lucide-react";
import { panelFailureIconClass } from "@/lib/failure-treatment";
import { useTranslation } from "react-i18next";
import { readStored, writeStored } from "@/lib/browser-storage";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { DecisionHistoryView } from "@/components/sidebar/command-palette/DecisionHistoryView";
import { RunDossierView } from "@/components/sidebar/command-palette/RunDossierView";
import CommandPaletteRowActions from "@/components/sidebar/command-palette/CommandPaletteRowActions";
import pointerAffordances from "@/components/sidebar/pointerAffordances.module.css";
import { commandPaletteRowActions } from "@/components/sidebar/command-palette/rowActionItems";
import CommandPaletteDossierSheet from "@/components/sidebar/command-palette/CommandPaletteDossierSheet";
import { BottomSheet } from "@/components/ui/BottomSheet";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import { useModalSurface } from "@/components/layout/useModalSurface";
import { useSheetStack } from "@/components/ui/sheetStack";
import { useRunDossierHistory } from "@/components/sidebar/command-palette/useRunDossierHistory";
import { CommandPaletteFooter, useCommandPaletteShortcutLegend } from "@/components/sidebar/command-palette/CommandPaletteShortcutLegend";
import { SearchHighlight } from "@/components/sidebar/SearchHighlight";
import { searchQueryIsIndexable } from "@/lib/search-text";
import { refreshCanonicalMutation } from "@/lib/canonical-mutation-refresh";
import {
  commitDossierDecision,
  DEFAULT_DOSSIER_PANE_STATE,
  dossierCountsForHistory,
  dossierPaneTransition,
  openSelectedDossierConversation,
  selectedDossierForPane,
  type DossierPaneState,
} from "@/lib/command-palette-dossier-integration";
import {
  deleteConversation as apiDeleteConversation,
  createEvidenceDecision,
  listHistory,
  patchConversation,
  searchGlobal,
  type DecisionState,
  type HistoryItem,
  type SearchAssetRollupItem,
  type SearchConversationItem,
  type SearchItem,
  type SearchLedgerGroup,
} from "@/lib/argus-api";
import {
  commandPaletteAssetRollupFromSearch,
  commandPaletteCanonicalRecallLimit,
  commandPaletteConversationNavigationDisabled,
  commandPaletteDecisionStateFallback,
  commandPaletteGroupsByLedgerState,
  commandPaletteItemFromSearch,
  commandPaletteItemsFromHistory,
  commandPaletteItemsInRenderedOrder,
  commandPaletteOpenFallback,
  commandPaletteOpenLabelKey,
  commandPaletteOpenMessageId,
  commandPaletteRequestIsCurrent,
  commandPaletteSelectedRenderedPreview,
  commandPaletteStatusFallback,
  commandPaletteStatusLabelKey,
  commandPaletteTypeFallback,
  commandPaletteTypeLabelKey,
  type CommandPaletteDisplayItem,
} from "@/lib/command-palette-items";
import type {
  DecisionState as RunDossierDecisionState,
  SearchDecisionAction,
} from "@/lib/run-dossier-contract";
import { dossierDecisionResumeTarget, type GuestDecisionResumeTarget } from "@/lib/guest-conversion";
import {
  isRecentRecallResponse,
  loadCommandPaletteRecentRecall,
  retainRecalledRecentItems,
} from "@/lib/command-palette-recent-recall";
import { AssetHistoryRollup } from "./command-palette/AssetHistoryRollup";
import { AnswerDossierView } from "./command-palette/AnswerDossierView";
import { AskArgusRow } from "./command-palette/AskArgusRow";
import { useDossierDecisionResumeRefresh } from "./command-palette/useDossierDecisionResumeRefresh";
import { useCommandPaletteKeys } from "./command-palette/useCommandPaletteKeys";
import {
  effectivePaletteLayout,
  paletteRowActionVariant,
  type LayoutMode,
} from "./command-palette/paletteLayout";
import CommandPaletteLoadMoreControl from "./CommandPaletteLoadMoreControl";
import { useChatAvailable, useChatWorkspace, useConversationSurface } from "@/components/chat/ChatWorkspace";
import { moveWorkspaceFocus, useRecentSearches, useWorkspaceSearch, WorkspaceSearchHome, WorkspaceSearchNoMatch, WorkspaceSearchResults } from "./command-palette/WorkspaceSearchResults";
import { primaryButtonClass, quietButtonClass } from "@/components/business-app/business-ui";

type ChatCommandPaletteProps = {
  onClose: () => void;
  onOpenConversation: (
    conversationId: string,
    messageId?: string,
    openAtLeftOff?: boolean,
  ) => void;
  onRetest: (conversationId: string, sourceRunId: string) => Promise<void> | void;
  /** Starts a new chat with the typed text when nothing matched. */
  onAsk?: (text: string) => void;
  turnInFlight?: boolean;
  activeConversationId: string | null;
  isGuest?: boolean;
  groundedDiscoveryAvailable?: boolean;
  canManageConversation?: boolean;
  onDecisionUnavailable?: (target: GuestDecisionResumeTarget) => void;
  decisionResumeTarget?: GuestDecisionResumeTarget | null;
  onDecisionResumeHandled?: () => void;
  onMutated?: () => void;
  onConversationRemoved?: (conversationId: string) => void;
};

type SearchReadError = "history" | "search" | "ledger" | null;
type DateDisplayGroup = {
  id: string;
  label: string;
  items: CommandPaletteDisplayItem[];
};

const SEARCH_DEBOUNCE_MS = 200;
const RECENTS_SEARCH_SIGNATURE = JSON.stringify(["", false, null]);
export const commandPaletteDossierPanelClassName = (view: DossierPaneState["view"]) =>
  `flex w-full shrink-0 flex-col bg-black/[0.02] p-5 dark:bg-white/[0.02] md:h-auto md:max-h-none md:w-[44%] md:overflow-visible md:p-6 ${view === "history" ? "h-[68%] max-h-[68%] overflow-hidden" : "max-h-[42%] overflow-y-auto"}`;

function formatRelativeDate(
  value: string,
  t: ReturnType<typeof useTranslation>["t"],
  locale: string,
) {
  const date = new Date(value);
  const now = new Date();
  const todayStart = new Date(
    now.getFullYear(),
    now.getMonth(),
    now.getDate(),
  ).getTime();
  const time = date.getTime();

  if (time >= todayStart) return t("chat.history.today", "Today");
  if (time >= todayStart - 86400000)
    return t("chat.history.yesterday", "Yesterday");
  return new Intl.DateTimeFormat(locale, {
    month: "short",
    day: "numeric",
  }).format(date);
}

function formatDossierDate(value: string, locale: string) {
  const date = new Date(
    /^\d{4}-\d{2}-\d{2}$/.test(value) ? `${value}T00:00:00.000Z` : value,
  );
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat(locale, {
    year: "numeric",
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  }).format(date);
}

function dateGroup(value: string, t: ReturnType<typeof useTranslation>["t"]) {
  const date = new Date(value);
  const now = new Date();
  const todayStart = new Date(
    now.getFullYear(),
    now.getMonth(),
    now.getDate(),
  ).getTime();
  const time = date.getTime();

  if (time >= todayStart) return t("chat.history.today", "Today");
  if (time >= todayStart - 86400000)
    return t("chat.history.yesterday", "Yesterday");
  if (time >= todayStart - 86400000 * 6)
    return t("chat.history.last_7_days", "Last 7 days");
  if (time >= todayStart - 86400000 * 29)
    return t("chat.history.last_30_days", "Last 30 days");
  return t("chat.history.earlier", "Earlier");
}

function groupItems(
  items: CommandPaletteDisplayItem[],
  t: ReturnType<typeof useTranslation>["t"],
) {
  const groups: DateDisplayGroup[] = [];
  const buckets = new Map<string, CommandPaletteDisplayItem[]>();

  for (const item of items) {
    const label = dateGroup(item.updatedAt, t);
    const existing = buckets.get(label);
    if (existing) {
      existing.push(item);
    } else {
      const bucket = [item];
      buckets.set(label, bucket);
      groups.push({ id: `date:${label}`, label, items: bucket });
    }
  }

  return groups;
}

function isSearchConversationItem(
  item: SearchItem,
): item is SearchConversationItem {
  return item.type === "conversation";
}

function rawConversationId(item: HistoryItem | SearchConversationItem) {
  return item.conversation_id ?? item.id;
}

function searchResultKey(item: SearchItem) {
  return item.type === "asset_rollup"
    ? `asset_rollup:${item.symbol}`
    : `conversation:${item.id}`;
}

function ledgerDecisionChipClassName(state: DecisionState, selected: boolean) {
  const base =
    "min-h-11 shrink-0 rounded-full border px-3 py-1 text-[11px] font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 disabled:opacity-60 active:scale-[0.98]";
  if (!selected) {
    return `${base} border-black/8 text-black/45 hover:bg-black/[0.03] focus-visible:ring-black/15 dark:border-white/10 dark:text-white/45 dark:hover:bg-white/[0.04] dark:focus-visible:ring-white/15`;
  }
  switch (state) {
    case "promising":
      return `${base} border-[#5ba897]/34 bg-[#5ba897]/11 text-[#3f816f] focus-visible:ring-[#5ba897]/20 dark:text-[#7bc1ad]`;
    case "rejected":
      return `${base} border-[#d66d75]/34 bg-[#d66d75]/11 text-[#ad4e56] focus-visible:ring-[#d66d75]/18 dark:text-[#e58c93]`;
    case "revisit_later":
      return `${base} border-[#b79246]/34 bg-[#b79246]/11 text-[#92722d] focus-visible:ring-[#b79246]/18 dark:text-[#d7b56f]`;
    case "watching":
    default:
      return `${base} border-[#6f8fb8]/34 bg-[#6f8fb8]/11 text-[#4f6f98] focus-visible:ring-[#6f8fb8]/18 dark:text-[#91afd1]`;
  }
}

function ChatCommandPaletteSurface({
  onClose,
  onOpenConversation,
  onRetest,
  onAsk,
  turnInFlight = false,
  activeConversationId,
  isGuest = false,
  groundedDiscoveryAvailable = true,
  canManageConversation = true,
  onDecisionUnavailable,
  decisionResumeTarget,
  onDecisionResumeHandled,
  onMutated,
  onConversationRemoved,
}: ChatCommandPaletteProps) {
  const { t, i18n } = useTranslation();
  const surface = useConversationSurface();
  const chatAvailable = useChatAvailable();
  const workspaceSearch = useChatWorkspace()?.search ?? null;
  // Personal shows run dossiers; a workspace whose hits carry previews keeps the pane too.
  const hasPreviewPane = surface === "personal" || workspaceSearch?.previewAvailable === true;
  const searchSurface = useCallback(
    (params: Parameters<typeof searchGlobal>[0]) =>
      searchGlobal({ ...params, surface, includeLedgerGroups: surface === "personal" && params.includeLedgerGroups }),
    [surface],
  );
  const [query, setQuery] = useState("");
  const [recentItems, setRecentItems] = useState<HistoryItem[]>([]);
  const [searchResults, setSearchResults] = useState<SearchItem[]>([]);
  const [searchNextCursor, setSearchNextCursor] = useState<string | null>(null);
  const [ledgerGroups, setLedgerGroups] = useState<SearchLedgerGroup[]>([]);
  const [isLedgerMode, setIsLedgerMode] = useState(false);
  const [decisionStateFilter, setDecisionStateFilter] =
    useState<DecisionState | null>(null);
  const [isColdStartLoading, setIsColdStartLoading] = useState(true);
  const [isSearching, setIsSearching] = useState(false);
  const [isLedgerLoading, setIsLedgerLoading] = useState(false);
  const [isLoadingMoreSearch, setIsLoadingMoreSearch] = useState(false);
  const [loadMoreFailed, setLoadMoreFailed] = useState(false);
  const [readError, setReadError] = useState<SearchReadError>(null);
  const [retryNonce, setRetryNonce] = useState(0);
  const [previewItem, setPreviewItem] =
    useState<CommandPaletteDisplayItem | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingTitle, setEditingTitle] = useState("");
  const [isSubmittingEdit, setIsSubmittingEdit] = useState(false);
  const [pendingDeleteItem, setPendingDeleteItem] =
    useState<CommandPaletteDisplayItem | null>(null);
  const [showDeleteKeyboardHints, setShowDeleteKeyboardHints] =
    useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [isSavingDecision, setIsSavingDecision] = useState(false);
  const [layoutMode, setLayoutMode] = useState<LayoutMode>("expanded");
  const { isBelowTablet, isBelowDesktop } = useResponsiveLayout();
  const paletteOverlayId = useId();
  const paletteRef = useRef<HTMLDivElement>(null);
  const [isDossierSheetOpen, setIsDossierSheetOpen] = useState(false);
  const effectiveLayoutMode = hasPreviewPane ? effectivePaletteLayout(layoutMode, isBelowTablet) : "collapsed";
  const rowActionVariant = paletteRowActionVariant(isBelowDesktop);
  const shortcutLegend = useCommandPaletteShortcutLegend();
  const [dossierPaneState, setDossierPaneState] = useState<DossierPaneState>(
    DEFAULT_DOSSIER_PANE_STATE,
  );
  const inputRef = useRef<HTMLInputElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const historyRequestIdRef = useRef(0);
  const ledgerBrowseRequestIdRef = useRef(0);
  const searchRequestIdRef = useRef(0);
  const canonicalMutationIdRef = useRef(0);
  const decisionMutationInFlightRef = useRef(false);
  const searchSignatureRef = useRef(RECENTS_SEARCH_SIGNATURE);
  const isRecentsMode =
    query.trim() === "" &&
    !isLedgerMode &&
    decisionStateFilter === null;

  useEffect(() => {
    const saved = readStored("argus:command_palette_layout");
    if (saved === "expanded" || saved === "collapsed") {
      setLayoutMode(saved);
    }
  }, []);

  useEffect(() => {
    if (
      !isRecentsMode ||
      searchSignatureRef.current !== RECENTS_SEARCH_SIGNATURE
    ) {
      return;
    }
    if (!chatAvailable) {
      setIsColdStartLoading(false);
      return;
    }
    const requestId = ++historyRequestIdRef.current;
    const capturedSignature = RECENTS_SEARCH_SIGNATURE;
    setIsColdStartLoading(true);
    setReadError(null);
    const isCurrent = () =>
      commandPaletteRequestIsCurrent({
        capturedSignature,
        capturedRequestId: requestId,
        currentSignature: searchSignatureRef.current,
        currentRequestId: historyRequestIdRef.current,
      });
    void (async () => {
      try {
        const { items } = await listHistory({ limit: 50, surface });
        if (!isCurrent()) return;
        const visibleRecents = items.filter((item) => item.type === "chat");
        const response = await loadCommandPaletteRecentRecall({
          recentItems: visibleRecents,
          fetchRecall: searchSurface,
          isCurrent,
        });
        if (!response || !isCurrent()) return;
        setRecentItems(response.recentItems);
        setSearchResults(response.items);
        setSearchNextCursor(null);
        setLedgerGroups(isGuest ? [] : (response.ledger_groups ?? []));
        setReadError(null);
      } catch {
        if (!isCurrent()) return;
        setSearchResults([]);
        setLedgerGroups([]);
        setReadError("history");
      } finally {
        if (requestId === historyRequestIdRef.current) {
          setIsColdStartLoading(false);
        }
      }
    })();
  }, [chatAvailable, isGuest, isRecentsMode, retryNonce, searchSurface, surface]);

  const clearSearchAndLedger = useCallback(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (searchSignatureRef.current !== RECENTS_SEARCH_SIGNATURE) {
      historyRequestIdRef.current += 1;
    }
    searchSignatureRef.current = RECENTS_SEARCH_SIGNATURE;
    ledgerBrowseRequestIdRef.current += 1;
    searchRequestIdRef.current += 1;
    setLedgerGroups([]);
    setQuery("");
    setIsLedgerMode(false);
    setDecisionStateFilter(null);
    setSearchResults([]);
    setSearchNextCursor(null);
    setPreviewItem(null);
    setIsSearching(false);
    setIsLedgerLoading(false);
    setIsLoadingMoreSearch(false);
    setLoadMoreFailed(false);
    setReadError(null);
  }, []);

  const loadLedgerBrowse = useCallback(
    async (nextDecisionState: DecisionState | null) => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      const capturedSignature = JSON.stringify([
        "",
        true,
        nextDecisionState,
      ]);
      searchSignatureRef.current = capturedSignature;
      searchRequestIdRef.current += 1;
      setLedgerGroups([]);
      setQuery("");
      setIsLedgerMode(true);
      setDecisionStateFilter(nextDecisionState);
      setPreviewItem(null);
      setIsSearching(false);
      setIsLedgerLoading(true);
      setIsLoadingMoreSearch(false);
      setLoadMoreFailed(false);
      setReadError(null);
      const requestId = ++ledgerBrowseRequestIdRef.current;
      const isCurrent = () =>
        commandPaletteRequestIsCurrent({
          capturedSignature,
          capturedRequestId: requestId,
          currentSignature: searchSignatureRef.current,
          currentRequestId: ledgerBrowseRequestIdRef.current,
        });
      try {
        const { items, next_cursor, ledger_groups } = await searchSurface({
          q: "",
          limit: 100,
          decisionState: nextDecisionState,
          includeLedgerGroups: true,
        });
        if (!isCurrent()) return;
        setSearchResults(items);
        setSearchNextCursor(next_cursor);
        setLedgerGroups(ledger_groups ?? []);
      } catch {
        if (isCurrent()) {
          setReadError("ledger");
        }
      } finally {
        if (isCurrent()) {
          setIsLedgerLoading(false);
        }
      }
    },
    [searchSurface],
  );

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);

    const trimmed = query.trim();
    const capturedSignature = JSON.stringify([
      trimmed,
      isLedgerMode,
      decisionStateFilter,
    ]);
    searchSignatureRef.current = capturedSignature;
    setIsLoadingMoreSearch(false);
    setLoadMoreFailed(false);
    setPreviewItem(null);
    if (!trimmed || !chatAvailable) {
      searchRequestIdRef.current += 1;
      if (!isLedgerMode) {
        setSearchResults([]);
        setSearchNextCursor(null);
      }
      setIsSearching(false);
      if (!isLedgerMode) setReadError(null);
      return;
    }
    if (!searchQueryIsIndexable(trimmed)) {
      searchRequestIdRef.current += 1;
      setSearchResults([]);
      setSearchNextCursor(null);
      setIsSearching(false);
      setReadError(null);
      return;
    }

    setIsSearching(true);
    setReadError(null);
    debounceRef.current = setTimeout(() => {
      const requestId = ++searchRequestIdRef.current;
      const isCurrent = () =>
        commandPaletteRequestIsCurrent({
          capturedSignature,
          capturedRequestId: requestId,
          currentSignature: searchSignatureRef.current,
          currentRequestId: searchRequestIdRef.current,
        });
      searchSurface({
        q: trimmed,
        limit: 30,
        includeLedgerGroups: true,
      })
        .then(({ items, next_cursor, ledger_groups }) => {
          if (!isCurrent()) return;
          setSearchResults(items);
          setSearchNextCursor(next_cursor);
          setLedgerGroups(ledger_groups ?? []);
        })
        .catch(() => {
          if (isCurrent()) {
            setReadError("search");
          }
        })
        .finally(() => {
          if (isCurrent()) {
            setIsSearching(false);
          }
        });
    }, SEARCH_DEBOUNCE_MS);

    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [chatAvailable, decisionStateFilter, isLedgerMode, query, retryNonce, searchSurface]);

  const workspaceResults = useWorkspaceSearch(isLedgerMode ? null : workspaceSearch, query);
  const workspaceRecents = useRecentSearches(workspaceSearch?.recents ?? null);
  const [workspaceSelection, setWorkspaceSelection] = useState<string | null>(null);
  const [workspaceSheet, setWorkspaceSheet] = useState(false);
  const workspaceGroups = workspaceResults.state.status === "ready" ? workspaceResults.state.groups : [];
  const selectedWorkspaceHit = workspaceGroups.flatMap((group) => group.hits.map((hit) => ({ key: `${group.id}:${hit.id}`, hit }))).find((item) => item.key === workspaceSelection)?.hit;
  // A new query or a conversation preview replaces the previewed record.
  useEffect(() => { setWorkspaceSelection(null); setWorkspaceSheet(false); }, [query, previewItem]);
  const openSelectedWorkspaceHit = selectedWorkspaceHit?.open;
  const workspaceDossier = selectedWorkspaceHit?.preview ? <div data-dossier-pane="true" className="flex h-full flex-col gap-4">
    <div className="min-h-0 flex-1 overflow-y-auto">{selectedWorkspaceHit.preview}</div>
    {openSelectedWorkspaceHit ? <button type="button" className={`${primaryButtonClass} shrink-0`} onClick={() => { onClose(); openSelectedWorkspaceHit(); }}>{t("business.search.open_record", "Open record")}</button> : null}
  </div> : null;
  const isFiltering = query.trim().length > 0;
  const isWaitingForIndexableQuery =
    isFiltering && !searchQueryIsIndexable(query);
  const isResultMode = isFiltering || isLedgerMode;
  // Without chat or a workspace's own screens there is nothing to list before a query, so the palette is just its field.
  const isFieldOnly = !chatAvailable && !isFiltering && !workspaceSearch;
  const assetRollup = useMemo(
    () =>
      isFiltering
        ? (searchResults.find(
            (item): item is SearchAssetRollupItem =>
              item.type === "asset_rollup",
          ) ?? null)
        : null,
    [isFiltering, searchResults],
  );
  const assetRollupDisplay = useMemo(
    () =>
      assetRollup
        ? commandPaletteAssetRollupFromSearch(assetRollup, {
            heading: t(
              "command_palette.asset_rollup.heading",
              "Your Argus history",
            ),
            scope: isGuest
              ? t(
                  "command_palette.asset_rollup.scope_guest",
                  "In this temporary conversation",
                )
              : t(
                  "command_palette.asset_rollup.scope_registered",
                  "Across your conversations",
                ),
            resultsInvolving: (count, symbol) =>
              t("command_palette.asset_rollup.results_involving", {
                count,
                symbol,
                defaultValue: `${count} ${
                  count === 1 ? "result" : "results"
                } involving ${symbol}`,
              }),
            decisionStateLabel: (state) =>
              t(
                `chat.result_card.decision_states.${state}`,
                commandPaletteDecisionStateFallback(state),
              ),
            dateLabel: (value) =>
              formatDossierDate(
                value,
                i18n.resolvedLanguage ?? i18n.language ?? "en",
              ),
            lastTouched: (date) =>
              t("command_palette.asset_rollup.last_touched", {
                date,
                defaultValue: `Last touched ${date}`,
              }),
          })
        : null,
    [assetRollup, i18n.language, i18n.resolvedLanguage, isGuest, t],
  );
  const displayItems = useMemo(() => {
    const items = isResultMode
      ? searchResults
          .filter(isSearchConversationItem)
          .map((item) => commandPaletteItemFromSearch(item))
      : commandPaletteItemsFromHistory(
          recentItems,
          searchResults.filter(isSearchConversationItem),
        );
    return items
      .filter((item): item is CommandPaletteDisplayItem => Boolean(item))
      .map((item) => ({ ...item, snippet: item.snippet || conversationPreviewText(item.preview, t) }))
      .map((item) =>
        canManageConversation
          ? item
          : { ...item, canManageConversation: false },
      );
  }, [canManageConversation, isResultMode, recentItems, searchResults, t]);
  const dateGroupedItems = useMemo(
    () => groupItems(displayItems, t),
    [displayItems, t],
  );
  const visibleLedgerGroups = useMemo(
    () =>
      decisionStateFilter
        ? ledgerGroups.filter(
            (group) => group.decision_state === decisionStateFilter,
          )
        : ledgerGroups,
    [decisionStateFilter, ledgerGroups],
  );
  const ledgerGroupedItems = useMemo(
    () => commandPaletteGroupsByLedgerState(displayItems, visibleLedgerGroups),
    [displayItems, visibleLedgerGroups],
  );
  const groupedItems = isLedgerMode ? ledgerGroupedItems : dateGroupedItems;
  const keyboardItems = useMemo(
    () => commandPaletteItemsInRenderedOrder(groupedItems),
    [groupedItems],
  );
  const selectedPreview = commandPaletteSelectedRenderedPreview(
    previewItem,
    groupedItems,
  );
  const selectedNavigationDisabled = commandPaletteConversationNavigationDisabled({ turnInFlight, activeConversationId, targetConversationId: selectedPreview?.conversationId ?? null });
  const dossierContextKey = JSON.stringify([
    query.trim(),
    isLedgerMode,
    decisionStateFilter,
    selectedPreview?.source ?? null,
    selectedPreview?.type ?? null,
    selectedPreview?.id ?? null,
    selectedPreview?.conversationId ?? null,
  ]);
  const history = useRunDossierHistory(
    selectedPreview?.conversationId ?? "",
    dossierContextKey,
  );
  const selectedDossier = selectedPreview?.dossier
    ? selectedDossierForPane({
        latestDossier: selectedPreview.dossier,
        historyItems: history.items,
        state: dossierPaneState,
      })
    : null;
  const dossierCounts = dossierCountsForHistory({
    history,
    fallbackTotalRuns: selectedPreview?.totalRuns ?? 0,
    fallbackDecidedRuns: selectedPreview?.decidedRuns ?? 0,
  });

  useEffect(() => {
    setDossierPaneState((current) =>
      dossierPaneTransition(current, {
        type: "reset",
        reason: "selection",
      }),
    );
  }, [dossierContextKey]);

  useEffect(() => {
    if (
      history.status !== "ready" ||
      !dossierPaneState.historicalRunId ||
      history.items.some(
        (item) => item.run_id === dossierPaneState.historicalRunId,
      )
    ) {
      return;
    }
    setDossierPaneState((current) =>
      dossierPaneTransition(current, { type: "restore_latest" }),
    );
  }, [
    dossierPaneState.historicalRunId,
    history.items,
    history.status,
  ]);

  const refreshCanonicalSearch = useCallback(
    async (capturedSignature: string, mutationId: number) => {
      const [currentQuery, currentLedgerMode, currentDecisionState] =
        JSON.parse(capturedSignature) as [
          string,
          boolean,
          DecisionState | null,
        ];
      setIsLoadingMoreSearch(false);
      setLoadMoreFailed(false);
      setIsLedgerLoading(false);
      historyRequestIdRef.current += 1;
      ledgerBrowseRequestIdRef.current += 1;
      const requestId = ++searchRequestIdRef.current;
      const isStale = () =>
        mutationId !== canonicalMutationIdRef.current ||
        requestId !== searchRequestIdRef.current ||
        capturedSignature !== searchSignatureRef.current;
      const response =
        currentQuery === "" && !currentLedgerMode
          ? await loadCommandPaletteRecentRecall({
              recentItems,
              fetchRecall: searchSurface,
              isCurrent: () => !isStale(),
            })
          : await searchSurface({
              q: currentQuery,
              limit: commandPaletteCanonicalRecallLimit(
                currentQuery,
                currentLedgerMode,
              ),
              decisionState: currentLedgerMode ? currentDecisionState : null,
              includeLedgerGroups: true,
            });
      if (!response || isStale()) return;
      if (isRecentRecallResponse(response)) {
        setRecentItems((current) =>
          retainRecalledRecentItems(
            current,
            response.recalledConversationIds,
          ),
        );
      }
      setSearchResults(response.items);
      setSearchNextCursor(response.next_cursor);
      setLedgerGroups(
        currentQuery === "" && !currentLedgerMode && isGuest
          ? []
          : (response.ledger_groups ?? []),
      );
      setReadError(null);
    },
    [isGuest, recentItems, searchSurface],
  );

  const refreshAfterCanonicalMutation = useCallback(
    async (mutationId = ++canonicalMutationIdRef.current) => {
      const currentSignature = searchSignatureRef.current;
      const [currentQuery, currentLedgerMode] = JSON.parse(
        currentSignature,
      ) as [
        string,
        boolean,
        DecisionState | null,
      ];
      await refreshCanonicalMutation({
        refresh: async () => {
          await refreshCanonicalSearch(currentSignature, mutationId);
        },
        onFailure: () => {
          if (
            mutationId === canonicalMutationIdRef.current &&
            currentSignature === searchSignatureRef.current
          ) {
            setReadError(
              currentLedgerMode
                ? "ledger"
                : currentQuery
                  ? "search"
                  : "history",
            );
          }
        },
      });
    },
    [refreshCanonicalSearch],
  );
  useDossierDecisionResumeRefresh(decisionResumeTarget, refreshAfterCanonicalMutation, history.refresh);

  const saveDecision = useCallback(
    async (
      selectedRunId: string,
      action: SearchDecisionAction,
      draft: { decision_state: RunDossierDecisionState; note: string },
    ) => {
      if (decisionMutationInFlightRef.current) {
        throw new Error("A decision mutation is already in progress.");
      }
      decisionMutationInFlightRef.current = true;
      const mutationId = ++canonicalMutationIdRef.current;
      setIsSavingDecision(true);
      try {
        const reboundDossier = await commitDossierDecision({
          selectedRunId,
          mutate: async () => {
            await createEvidenceDecision(action.evidence_artifact_id, draft);
            if (mutationId !== canonicalMutationIdRef.current) {
              throw new Error("Decision mutation context changed.");
            }
            onMutated?.();
          },
          refreshCanonicalSearch: () =>
            refreshAfterCanonicalMutation(mutationId),
          refreshLoadedHistory: async () => {
            await history.refresh();
            return history.getCurrentState();
          },
        });
        if (mutationId !== canonicalMutationIdRef.current) return;
        setDossierPaneState((current) => {
          if (current.historicalRunId !== selectedRunId) return current;
          return reboundDossier
            ? current
            : dossierPaneTransition(current, { type: "restore_latest" });
        });
      } finally {
        decisionMutationInFlightRef.current = false;
        setIsSavingDecision(false);
      }
    },
    [history, onMutated, refreshAfterCanonicalMutation],
  );

  const updateLocalTitle = useCallback(
    (conversationId: string, title: string) => {
      setRecentItems((current) =>
        current.map((item) =>
          rawConversationId(item) === conversationId
            ? { ...item, title }
            : item,
        ),
      );
      setSearchResults((current) =>
        current.map((item) =>
          isSearchConversationItem(item) &&
          rawConversationId(item) === conversationId
            ? { ...item, title }
            : item,
        ),
      );
      setPreviewItem((current) =>
        current?.conversationId === conversationId
          ? { ...current, title }
          : current,
      );
    },
    [],
  );

  const removeLocalConversation = useCallback((conversationId: string) => {
    setRecentItems((current) =>
      current.filter((item) => rawConversationId(item) !== conversationId),
    );
    setSearchResults((current) =>
      current.filter(
        (item) =>
          !isSearchConversationItem(item) ||
          rawConversationId(item) !== conversationId,
      ),
    );
    setPreviewItem((current) =>
      current?.conversationId === conversationId ? null : current,
    );
  }, []);

  const loadMoreSearch = async () => {
    const trimmed = query.trim();
    if (
      (!trimmed && !isLedgerMode) ||
      !searchNextCursor ||
      isLoadingMoreSearch ||
      isSavingDecision
    )
      return;

    const capturedSignature = searchSignatureRef.current;
    const requestId = ++searchRequestIdRef.current;
    setIsLoadingMoreSearch(true);
    setLoadMoreFailed(false);
    try {
      const { items, next_cursor } = await searchSurface({
        q: trimmed,
        limit: isLedgerMode ? 100 : 30,
        cursor: searchNextCursor,
        decisionState: isLedgerMode ? decisionStateFilter : null,
        includeLedgerGroups: isLedgerMode,
      });
      if (
        !commandPaletteRequestIsCurrent({
          capturedSignature,
          capturedRequestId: requestId,
          currentSignature: searchSignatureRef.current,
          currentRequestId: searchRequestIdRef.current,
        })
      ) {
        return;
      }
      setSearchResults((current) => {
        const seen = new Set(current.map(searchResultKey));
        const next = [...current];
        for (const item of items) {
          const key = searchResultKey(item);
          if (!seen.has(key)) {
            seen.add(key);
            next.push(item);
          }
        }
        return next;
      });
      setSearchNextCursor(next_cursor);
    } catch {
      if (
        commandPaletteRequestIsCurrent({
          capturedSignature,
          capturedRequestId: requestId,
          currentSignature: searchSignatureRef.current,
          currentRequestId: searchRequestIdRef.current,
        })
      ) {
        setLoadMoreFailed(true);
      }
    } finally {
      if (
        commandPaletteRequestIsCurrent({
          capturedSignature,
          capturedRequestId: requestId,
          currentSignature: searchSignatureRef.current,
          currentRequestId: searchRequestIdRef.current,
        })
      ) {
        setIsLoadingMoreSearch(false);
      }
    }
  };

  const openSourceConversation = useCallback(
    (item: CommandPaletteDisplayItem, openAtLeftOff = false) => {
      if (!item.conversationId) return;
      if (
        commandPaletteConversationNavigationDisabled({
          turnInFlight,
          activeConversationId,
          targetConversationId: item.conversationId,
        })
      ) {
        return;
      }
      const messageId = commandPaletteOpenMessageId(item, openAtLeftOff);
      onOpenConversation(
        item.conversationId,
        messageId ?? undefined,
        openAtLeftOff,
      );
      onClose();
    },
    [activeConversationId, onClose, onOpenConversation, turnInFlight],
  );

  const activateItem = useCallback(
    (item: CommandPaletteDisplayItem, openAtLeftOff = false) => {
      openSourceConversation(item, openAtLeftOff);
    },
    [openSourceConversation],
  );

  const startRename = useCallback(
    (item: CommandPaletteDisplayItem) => {
      if (!canManageConversation) return;
      if (!item.canManageConversation || !item.conversationId) return;
      setEditingId(item.conversationId);
      setEditingTitle(item.title.slice(0, 80));
      setPreviewItem(item);
    },
    [canManageConversation],
  );

  const cancelRename = useCallback(() => {
    setEditingId(null);
    setEditingTitle("");
  }, []);

  const handleRenameSave = useCallback(
    async (item: CommandPaletteDisplayItem) => {
      if (!canManageConversation) return;
      if (isSubmittingEdit) return;
      if (!item.canManageConversation || !item.conversationId) return;

      const nextTitle = editingTitle.trim();
      if (!nextTitle || nextTitle === item.title) {
        cancelRename();
        return;
      }

      setIsSubmittingEdit(true);
      try {
        await patchConversation(item.conversationId, { title: nextTitle });
        updateLocalTitle(item.conversationId, nextTitle);
        onMutated?.();
        setEditingId(null);
        setEditingTitle("");
      } finally {
        setIsSubmittingEdit(false);
      }
    },
    [
      canManageConversation,
      cancelRename,
      editingTitle,
      isSubmittingEdit,
      onMutated,
      updateLocalTitle,
    ],
  );

  const handleArchive = useCallback(
    async (item: CommandPaletteDisplayItem) => {
      if (!canManageConversation) return;
      if (!item.canManageConversation || !item.conversationId) return;
      removeLocalConversation(item.conversationId);
      onConversationRemoved?.(item.conversationId);
      await patchConversation(item.conversationId, { archived: true });
      onMutated?.();
    },
    [
      canManageConversation,
      onConversationRemoved,
      onMutated,
      removeLocalConversation,
    ],
  );

  const handleDelete = useCallback(
    (item: CommandPaletteDisplayItem, fromKeyboardShortcut = false) => {
      if (!canManageConversation) return;
      if (!item.canManageConversation) return;
      setShowDeleteKeyboardHints(fromKeyboardShortcut);
      setPendingDeleteItem(item);
    },
    [canManageConversation],
  );

  const handleCancelDelete = useCallback(() => {
    if (!isDeleting) {
      setPendingDeleteItem(null);
      setShowDeleteKeyboardHints(false);
    }
  }, [isDeleting]);

  const handleConfirmDelete = useCallback(async () => {
    if (!canManageConversation) return;
    if (!pendingDeleteItem || isDeleting) return;
    if (!pendingDeleteItem.conversationId) return;

    const mutationId = ++canonicalMutationIdRef.current;
    setIsDeleting(true);
    removeLocalConversation(pendingDeleteItem.conversationId);
    onConversationRemoved?.(pendingDeleteItem.conversationId);
    try {
      await apiDeleteConversation(pendingDeleteItem.conversationId);
      onMutated?.();
      setPendingDeleteItem(null);
      setShowDeleteKeyboardHints(false);
      try {
        await refreshAfterCanonicalMutation(mutationId);
      } catch {
        // The canonical refresh already published the scoped read error.
      }
    } finally {
      setIsDeleting(false);
    }
  }, [
    isDeleting,
    canManageConversation,
    onConversationRemoved,
    onMutated,
    pendingDeleteItem,
    refreshAfterCanonicalMutation,
    removeLocalConversation,
  ]);

  // Pointer, Enter, Space, and the search field's open action all land here, so
  // no input method gets a different, more destructive navigation than another.
  const openRow = useCallback(
    (
      item: CommandPaletteDisplayItem,
      options: { navigationDisabled: boolean; openAtLeftOff?: boolean },
    ) => {
      if (isBelowDesktop && hasPreviewPane) {
        setPreviewItem(item);
        setIsDossierSheetOpen(true);
        return;
      }
      if (options.navigationDisabled) {
        setPreviewItem(item);
        setLayoutMode("expanded");
        return;
      }
      activateItem(item, options.openAtLeftOff);
    },
    [activateItem, hasPreviewPane, isBelowDesktop, setIsDossierSheetOpen, setPreviewItem],
  );

  const askText = chatAvailable && onAsk && isFiltering && !isWaitingForIndexableQuery && !isLedgerMode && !isSearching && !readError && displayItems.length === 0 && !assetRollupDisplay && workspaceResults.quiet ? query.trim() : null;
  const paletteKeys = useCommandPaletteKeys({
    askText,
    onAsk,
    cancelRename,
    canManageConversation,
    dossierPaneState,
    editingId,
    handleArchive,
    handleDelete,
    inputRef,
    keyboardItems,
    onClose,
    openRow,
    pendingDeleteItem,
    selectedNavigationDisabled,
    selectedPreview,
    setDossierPaneState,
    setPreviewItem,
    startRename,
    usesCommandKey: shortcutLegend.usesCommandKey,
  });
  const onPaletteKeyDown = (event: KeyboardEvent) => moveWorkspaceFocus(event, inputRef.current) || paletteKeys(event);

  // Owns more than Escape, so it hands over a whole keydown, and takes system
  // back with it: without an entry, back left Argus from an open search.
  // A result's details open as a sheet on a phone; the palette steps aside for it and comes back with its back arrow.
  const { drawn: paletteDrawn } = useSheetStack(paletteOverlayId, true);
  useModalSurface({
    isOpen: true,
    overlayId: paletteOverlayId,
    containerRef: paletteRef,
    onKeyDown: onPaletteKeyDown,
    onDismiss: onClose,
    initialFocusRef: inputRef,
  });

  const changeQuery = (nextQuery: string) => {
    const nextSignature = JSON.stringify([nextQuery.trim(), false, null]);
    if (nextSignature !== searchSignatureRef.current) {
      historyRequestIdRef.current += 1;
    }
    searchSignatureRef.current = nextSignature;
    ledgerBrowseRequestIdRef.current += 1;
    searchRequestIdRef.current += 1;
    setLedgerGroups([]);
    setIsLedgerLoading(false);
    setIsLoadingMoreSearch(false);
    setQuery(nextQuery);
    if (isLedgerMode || decisionStateFilter) {
      setIsLedgerMode(false);
      setDecisionStateFilter(null);
      setSearchResults([]);
      setSearchNextCursor(null);
    }
  };
  // A recent search fills the bar and searches, as typing it would.
  const fillQuery = (text: string) => { changeQuery(text); inputRef.current?.focus(); };

  const toggleLayout = () => {
    setLayoutMode((current) => {
      const next = current === "expanded" ? "collapsed" : "expanded";
      writeStored("argus:command_palette_layout", next);
      return next;
    });
  };

  const isLoading = isResultMode ? isSearching || isLedgerLoading : isColdStartLoading;
  // A workspace's search is a sheet, not a centred box: flat, no blur, no dimming.
  // From the tablet stop it hangs from the top and the page stays readable around
  // it; on a phone it fills the screen and closes from its own button.
  const workspaceIsSheet = workspaceSearch !== null;
  const workspaceSheetRootClass = `fixed inset-0 z-[60] flex justify-center ${isBelowTablet ? "" : "items-start p-3 pt-[8dvh] sm:p-6 sm:pt-[8dvh]"}`;
  const workspaceSheetPanelClass = isBelowTablet
    ? "relative flex h-[100dvh] w-full flex-col overflow-hidden bg-white dark:bg-[#1b1d20]"
    : `relative flex max-h-[84dvh] flex-col overflow-hidden rounded-[20px] border border-black/10 bg-white dark:border-white/10 dark:bg-[#1b1d20] ${
        effectiveLayoutMode === "expanded" ? "h-[78dvh] w-[94vw] max-w-6xl" : "h-[60dvh] w-full max-w-lg"
      }`;
  const footerCount = displayItems.length + workspaceGroups.reduce((count, group) => count + group.hits.length, 0);
  const selectedCanManageShortcutActions = Boolean(canManageConversation && selectedPreview?.canManageConversation);

  // One dossier body, shown as a pane on desktop and as a sheet below 1024px.
  const dossierPaneContent =
              selectedPreview ? (
                <div
                  className="flex h-full flex-col"
                  data-dossier-pane={selectedPreview.dossier || selectedPreview.answerDossier ? "true" : undefined}
                >
                  <div className="mb-6">
                    <div className="mb-3 flex flex-wrap gap-2">
                      {(selectedPreview.type === "chat" ||
                        selectedPreview.type === "conversation") &&
                        activeConversationId ===
                          selectedPreview.conversationId && (
                          <span className="inline-flex rounded-full border border-black/8 bg-white/50 px-2.5 py-1 text-[11px] font-semibold text-black/45 dark:border-white/10 dark:bg-white/[0.03] dark:text-white/45">
                            {t("common.current", "Current")}
                          </span>
                        )}
                      <span className="inline-flex rounded-full border border-black/8 bg-white/50 px-2.5 py-1 text-[11px] font-semibold text-black/45 dark:border-white/10 dark:bg-white/[0.03] dark:text-white/45">
                        {t(
                          commandPaletteTypeLabelKey(selectedPreview.type),
                          commandPaletteTypeFallback(selectedPreview.type),
                        )}
                      </span>
                    </div>
                    <h2 className="font-display text-[24px] font-medium leading-tight text-black dark:text-white">
                      {selectedPreview.title}
                    </h2>
                    <p className="mt-2 text-[13px] text-black/40 dark:text-white/40">
                      {formatRelativeDate(
                        selectedPreview.updatedAt,
                        t,
                        i18n.language,
                      )}
                    </p>
                  </div>
                  {selectedPreview.dossier && selectedDossier ? (
                    dossierPaneState.view === "history" ? (
                      <DecisionHistoryView
                        items={history.items}
                        nextCursor={history.nextCursor}
                        status={history.status}
                        onBack={() =>
                          setDossierPaneState((current) =>
                            dossierPaneTransition(current, {
                              type: "restore_latest",
                            }),
                          )
                        }
                        onLoadOlder={history.loadOlder}
                        onRetry={history.retry}
                        onSelectRun={(dossier) =>
                          setDossierPaneState((current) =>
                            dossierPaneTransition(current, {
                              type: "select_run",
                              runId: dossier.run_id,
                            }),
                          )
                        }
                      />
                    ) : (
                      <RunDossierView
                        key={selectedDossier.run_id}
                        dossier={selectedDossier}
                        totalRuns={dossierCounts.totalRuns}
                        decidedRuns={dossierCounts.decidedRuns}
                        onBackToLatest={
                          dossierPaneState.historicalRunId
                            ? () =>
                                setDossierPaneState((current) =>
                                  dossierPaneTransition(current, {
                                    type: "restore_latest",
                                  }),
                                )
                            : undefined
                        }
                        onOpenHistory={() => {
                          void history.open();
                          setDossierPaneState((current) =>
                            dossierPaneTransition(current, {
                              type: "open_history",
                            }),
                          );
                        }}
                        openConversationDisabled={
                          !selectedPreview.conversationId ||
                          selectedNavigationDisabled
                        }
                        retestDisabled={turnInFlight}
                        // The sheet pins this action in its footer, so the body
                        // only carries it where nothing else does: the pane.
                        onOpenConversation={
                          isBelowDesktop
                            ? undefined
                            : () => {
                                openSelectedDossierConversation({
                                  conversationId: selectedPreview.conversationId,
                                  dossier: selectedDossier,
                                  navigationDisabled: selectedNavigationDisabled,
                                  onOpenConversation: (
                                    conversationId,
                                    messageId,
                                  ) => onOpenConversation(conversationId, messageId),
                                  onClose,
                                });
                              }
                        }
                        onRetest={(sourceRunId) => {
                          if (!selectedPreview.conversationId) return;
                          return onRetest(
                            selectedPreview.conversationId,
                            sourceRunId,
                          );
                        }}
                        onSaveDecision={(action, draft) =>
                          saveDecision(selectedDossier.run_id, action, draft)
                        }
                        onDecisionUnavailable={onDecisionUnavailable}
                        resumeDecisionTarget={dossierDecisionResumeTarget(
                          decisionResumeTarget,
                        )}
                        onDecisionResumeHandled={onDecisionResumeHandled}
                      />
                    )
                  ) : selectedPreview.answerDossier ? (
                    // A computed answer's dossier beside the run dossier; the
                    // run dossier keeps precedence when the conversation has one.
                    <AnswerDossierView
                      key={selectedPreview.answerDossier.message_id}
                      dossier={selectedPreview.answerDossier}
                      openConversationDisabled={!selectedPreview.conversationId || selectedNavigationDisabled}
                      onOpenConversation={isBelowDesktop || !selectedPreview.conversationId ? undefined : () => {
                        onOpenConversation(selectedPreview.conversationId!, selectedPreview.answerDossier!.message_id);
                        onClose();
                      }}
                      onDecisionSaved={() => { onMutated?.(); void refreshAfterCanonicalMutation(); }}
                      onOpenConversationById={(conversationId) => { onOpenConversation(conversationId); onClose(); }}
                    />
                  ) : (
                    <>
                      <div
                        className="shrink-0 rounded-[14px] border border-black/5 bg-white/70 p-4 dark:border-white/10 dark:bg-[#1f2225]/70 md:min-h-0 md:flex-1 md:shrink md:overflow-y-auto"
                        tabIndex={0}
                        role="region"
                        aria-label={t("command_palette.preview", "Preview")}
                      >
                        <p className="text-[12px] font-semibold uppercase tracking-wider text-black/35 dark:text-white/35">
                          {t("command_palette.preview", "Preview")}
                        </p>
                        <p className="mt-2 text-[14px] leading-relaxed text-black/60 dark:text-white/60">
                          {selectedPreview.snippet ||
                            t(
                              "command_palette.preview_empty",
                              "Select a result to preview its details.",
                            )}
                        </p>
                      </div>
                      {isBelowDesktop ? null : (
                      <button
                        type="button"
                        onClick={() => openSourceConversation(selectedPreview)}
                        disabled={
                          !selectedPreview.conversationId ||
                          selectedNavigationDisabled
                        }
                        title={
                          selectedPreview.conversationId
                            ? undefined
                            : t(
                                "command_palette.no_source_conversation",
                                "No source conversation",
                              )
                        }
                        className="mt-auto flex min-h-11 shrink-0 items-center justify-between border-t border-black/5 pt-4 text-left text-[12px] text-black/35 transition-colors hover:text-black disabled:cursor-default disabled:hover:text-black/35 dark:border-white/5 dark:text-white/35 dark:hover:text-white dark:disabled:hover:text-white/35"
                      >
                        <span>
                          {selectedPreview.conversationId
                            ? t(
                                commandPaletteOpenLabelKey(selectedPreview),
                                commandPaletteOpenFallback(selectedPreview),
                              )
                            : t(
                                "command_palette.no_source_conversation",
                                "No source conversation",
                              )}
                        </span>
                        <ChevronRight className="h-4 w-4" />
                      </button>
                      )}
                    </>
                  )}
                </div>
              ) : (
                <div className="flex flex-1 items-center justify-center text-center">
                  <p className={`text-[13px] ${workspaceSearch ? "text-[#56635e] dark:text-white/65" : "text-black/30 dark:text-white/30"}`}>
                    {t(
                      "command_palette.select_preview",
                      "Select a result to preview its details.",
                    )}
                  </p>
                </div>
              );

  return (
    <div ref={paletteRef} hidden={!paletteDrawn} className={workspaceIsSheet ? workspaceSheetRootClass : "fixed inset-0 z-[60] flex items-center justify-center p-3 sm:p-6"}>
      <button
        tabIndex={-1}
        type="button"
        className={workspaceIsSheet ? "absolute inset-0" : "absolute inset-0 bg-black/20 backdrop-blur-sm dark:bg-black/60"}
        onClick={onClose}
        aria-label={t("command_palette.close", "Close search")}
      />

      <div
        className={workspaceIsSheet ? workspaceSheetPanelClass : `relative flex max-h-[calc(100dvh-1.5rem)] flex-col overflow-hidden rounded-[18px] border border-black/10 bg-white transition-all duration-300 dark:border-white/10 dark:bg-[#1b1d20] ${
          effectiveLayoutMode === "expanded"
            ? "h-[78dvh] w-[94vw] max-w-6xl"
            : isFieldOnly
              ? "mt-[calc(20dvh-0.75rem)] w-full max-w-lg self-start sm:mt-[calc(20dvh-1.5rem)]"
              : "h-[60dvh] w-full max-w-lg"
        }`}
      >
        <div className="flex items-center gap-3 border-b border-black/5 px-5 py-3.5 dark:border-white/5">
          <Search className="h-4 w-4 shrink-0 text-black/30 dark:text-white/30" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            maxLength={512}
            onChange={(event) => changeQuery(event.target.value)}
            placeholder={workspaceSearch?.copy.placeholder ?? t(
              "command_palette.search_placeholder",
              "Search Argus...",
            )}
            className="min-h-11 w-full bg-transparent font-display text-[16px] font-medium text-black outline-none placeholder:text-black/35 dark:text-white dark:placeholder:text-white/35"
          />
          {(query || isLedgerMode) && (
            <button
              type="button"
              onClick={clearSearchAndLedger}
              className="flex min-h-11 min-w-11 shrink-0 items-center justify-center rounded-full hover:bg-black/5 dark:hover:bg-white/10"
              aria-label={t("command_palette.clear_search", "Clear search")}
            >
              <X className="h-3.5 w-3.5 text-black/40 dark:text-white/40" />
            </button>
          )}
          {workspaceSearch && isBelowTablet ? (
            <button
              type="button"
              onClick={onClose}
              className={`${quietButtonClass} shrink-0 px-3`}
            >
              {workspaceSearch.copy.close}
            </button>
          ) : null}
        </div>

        {isGuest && !groundedDiscoveryAvailable && (
          <div
            className="border-b border-black/5 bg-black/[0.02] px-5 py-2.5 text-[12px] leading-relaxed text-black/50 dark:border-white/5 dark:bg-white/[0.025] dark:text-white/50"
            role="status"
          >
            {t(
              "command_palette.guest.discovery_unavailable",
              "Search is limited to this temporary conversation. Broader grounded discovery isn’t available yet.",
            )}
          </div>
        )}

        {ledgerGroups.length > 0 && (
          <div
            className="flex items-center gap-2 overflow-x-auto border-b border-black/5 px-5 py-2.5 dark:border-white/5"
            aria-label={t(
              "command_palette.ledger.decision_filters",
              "Decision filters",
            )}
          >
            {ledgerGroups.map((group) => {
              const selected = decisionStateFilter === group.decision_state;
              return (
                <button
                  key={group.decision_state}
                  type="button"
                  onClick={() => {
                    const nextDecisionState =
                      decisionStateFilter === group.decision_state
                        ? null
                        : group.decision_state;
                    if (nextDecisionState === null) {
                      clearSearchAndLedger();
                      return;
                    }
                    void loadLedgerBrowse(nextDecisionState);
                  }}
                  aria-pressed={isLedgerMode && selected}
                  disabled={isLedgerLoading}
                  className={ledgerDecisionChipClassName(
                    group.decision_state,
                    isLedgerMode && selected,
                  )}
                >
                  {t(
                    `chat.result_card.decision_states.${group.decision_state}`,
                    commandPaletteDecisionStateFallback(group.decision_state),
                  )}
                  <span className="ml-1 text-black/35 dark:text-white/35">
                    {group.count}
                  </span>
                </button>
              );
            })}
          </div>
        )}

        <div className="flex flex-1 flex-col overflow-hidden md:flex-row">
          <div
            className={`flex-1 overflow-y-auto ${
              effectiveLayoutMode === "expanded"
                ? "border-b border-black/5 dark:border-white/5 tablet:border-b-0 tablet:border-r"
                : ""
            }`}
            data-command-palette-action-region
            {...shortcutLegend.actionRegionProps}
          >
            {workspaceSearch && !isFiltering && !isLedgerMode ? <WorkspaceSearchHome search={workspaceSearch} recents={workspaceRecents} onFill={fillQuery} onOpened={onClose} /> : null}
            {workspaceSearch && isFiltering && <WorkspaceSearchResults search={workspaceSearch} {...workspaceResults} onOpened={onClose} onChosen={() => workspaceRecents.remember(query)} selectedKey={workspaceSelection ?? undefined} onPreview={workspaceSearch.previewAvailable ? (group, hit) => setWorkspaceSelection(`${group}:${hit.id}`) : undefined} onSelect={workspaceSearch.previewAvailable ? (group, hit) => { setWorkspaceSelection(`${group}:${hit.id}`); if (isBelowDesktop || effectiveLayoutMode === "collapsed") setWorkspaceSheet(true); } : undefined} />}
            {isLoading ? (
              <div className="flex items-center justify-center py-20">
                <Loader2 className="h-5 w-5 animate-spin text-black/20 dark:text-white/20" />
              </div>
            ) : readError ? (
              <div
                className="flex flex-col items-center justify-center px-6 py-20 text-center"
                role="alert"
              >
                <MessageSquareWarning
                  className={`mb-3 ${panelFailureIconClass}`}
                  aria-hidden="true"
                />
                <p className="text-[14px] text-black/50 dark:text-white/50">
                  {workspaceSearch?.copy.readError ?? t(
                    "command_palette.read_error",
                    "Argus couldn’t load these results.",
                  )}
                </p>
                <button
                  type="button"
                  onClick={() => {
                    if (readError === "ledger" && isLedgerMode) {
                      void loadLedgerBrowse(decisionStateFilter);
                      return;
                    }
                    setRetryNonce((current) => current + 1);
                  }}
                  className="mt-3 min-h-11 rounded-full border border-black/10 px-4 text-[13px] font-medium text-black/65 dark:border-white/10 dark:text-white/65"
                >
                  {t("command_palette.retry_search", "Try searching again")}
                </button>
              </div>
            ) : displayItems.length === 0 &&
              !assetRollupDisplay &&
              !isLedgerMode ? (workspaceSearch ? (isFiltering && workspaceResults.quiet ? <>
                <WorkspaceSearchNoMatch search={workspaceSearch} query={query} waiting={isWaitingForIndexableQuery} onOpened={onClose} />
                {askText && onAsk ? <div className="mt-3 px-3"><AskArgusRow label={workspaceSearch.copy.ask} text={askText} onAsk={onAsk} /></div> : null}
              </> : null) : workspaceResults.quiet && !isFieldOnly &&
              <div className="flex flex-col items-center justify-center py-20 text-center">
                <Search className="mb-3 h-8 w-8 text-black/10 dark:text-white/10" />
                <p className="text-[14px] text-black/30 dark:text-white/30">
                  {isFiltering
                    ? t(
                        isWaitingForIndexableQuery
                          ? "command_palette.keep_typing"
                          : "command_palette.no_results",
                        isWaitingForIndexableQuery
                          ? "Keep typing"
                          : "No results found",
                      )
                    : t(
                        "command_palette.no_conversations",
                        "No conversations yet",
                      )}
                </p>
                {isFiltering && (
                  <p className="mt-2 max-w-xs text-[12px] leading-relaxed text-black/25 dark:text-white/25">
                    {t(
                      isWaitingForIndexableQuery
                        ? "command_palette.keep_typing_detail"
                        : "command_palette.try_searching",
                      isWaitingForIndexableQuery
                        ? "Search starts with a 2-character ticker or a 3-character word."
                        : "Try a ticker, phrase, or note you remember.",
                    )}
                  </p>
                )}
                {askText && onAsk ? <div className="mt-6 w-full max-w-md px-3"><AskArgusRow text={askText} onAsk={onAsk} /></div> : null}
              </div>
            ) : (
              <div className="flex flex-col gap-3 p-3">
                {assetRollupDisplay && (
                  <AssetHistoryRollup rollup={assetRollupDisplay} />
                )}
                {groupedItems.map((group, groupIndex) => {
                  const groupRowStart = groupedItems
                    .slice(0, groupIndex)
                    .reduce(
                      (count, priorGroup) => count + priorGroup.items.length,
                      0,
                    );
                  const isLedgerGroup = "decisionState" in group;
                  const groupLabel = isLedgerGroup
                    ? t(
                        `chat.result_card.decision_states.${group.decisionState}`,
                        commandPaletteDecisionStateFallback(
                          group.decisionState,
                        ),
                      )
                    : group.label;
                  return (
                    <div key={group.id}>
                      <div className="px-2 pb-1.5 pt-1">
                        <span className="font-display text-[11px] font-semibold uppercase tracking-wider text-black/40 dark:text-white/40">
                          {groupLabel}
                          {isLedgerGroup && (
                            <span className="ml-1 text-black/30 dark:text-white/30">
                              {group.count}
                            </span>
                          )}
                        </span>
                      </div>
                      {group.items.length === 0 &&
                      isLedgerGroup &&
                      group.count === 0 ? (
                        <p className="px-2 py-2 text-[12px] text-black/30 dark:text-white/30">
                          {t(
                            "command_palette.ledger.no_saved_ideas",
                            "No saved ideas in this state",
                          )}
                        </p>
                      ) : (
                        group.items.map((item, itemIndex) => {
                          const isCurrent =
                            (item.type === "chat" ||
                              item.type === "conversation") &&
                            activeConversationId === item.conversationId;
                          const isEditing = editingId === item.conversationId;
                          const isNavigationDisabled =
                            commandPaletteConversationNavigationDisabled({
                              turnInFlight,
                              activeConversationId,
                              targetConversationId: item.conversationId,
                            });
                          const statusLabelKey =
                            commandPaletteStatusLabelKey(item);
                          const statusFallback =
                            commandPaletteStatusFallback(item);
                          const rowIndex = groupRowStart + itemIndex;
                          const handleRowKeyDown = (
                            event: ReactKeyboardEvent<HTMLDivElement>,
                          ) => {
                            if (isEditing) return;
                            // The row's own action menu is a control, not part
                            // of the row: Enter there must open the menu.
                            if (
                              event.target instanceof Element &&
                              event.target.closest("[data-row-action]")
                            ) {
                              return;
                            }
                            if (event.key === "Enter" || event.key === " ") {
                              event.preventDefault();
                              event.stopPropagation();
                              openRow(item, {
                                navigationDisabled: isNavigationDisabled,
                                openAtLeftOff:
                                  event.key === "Enter" &&
                                  (event.metaKey || event.ctrlKey),
                              });
                            }
                          };
                          return (
                            <div
                              key={`${item.source}:${item.id}`}
                              data-palette-row-index={rowIndex}
                              onClick={() =>
                                openRow(item, {
                                  navigationDisabled: isNavigationDisabled,
                                })
                              }
                              onKeyDown={handleRowKeyDown}
                              onMouseEnter={() => setPreviewItem(item)}
                              onFocus={() => setPreviewItem(item)}
                              role="button"
                              tabIndex={0}
                              aria-disabled={isNavigationDisabled}
                              className={`group relative flex w-full items-start gap-2 rounded-[12px] px-3 py-2.5 text-left transition-colors ${workspaceSearch ? "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-[#2f5a49]" : "outline-none focus:ring-2 focus:ring-black/20 dark:focus:ring-white/25"} max-desktop:min-h-11 max-desktop:pe-12 ${
                                selectedPreview?.id === item.id &&
                                selectedPreview.type === item.type
                                  ? "bg-black/5 dark:bg-white/5"
                                  : "hover:bg-black/[0.03] dark:hover:bg-white/[0.03]"
                              }`}
                            >
                              <div className="min-w-0 flex-1 pr-24 max-desktop:pr-0 max-desktop:self-center">
                                <div className="flex min-w-0 items-center gap-2 max-tablet:flex-wrap max-tablet:gap-y-1">
                                  {isEditing ? (
                                    <input
                                      autoFocus
                                      value={editingTitle}
                                      maxLength={80}
                                      onChange={(event) =>
                                        setEditingTitle(event.target.value)
                                      }
                                      onClick={(event) =>
                                        event.stopPropagation()
                                      }
                                      onFocus={(event) =>
                                        event.currentTarget.select()
                                      }
                                      onBlur={() => {
                                        void handleRenameSave(item);
                                      }}
                                      onKeyDown={(event) => {
                                        if (event.key === "Enter") {
                                          event.preventDefault();
                                          event.stopPropagation();
                                          void handleRenameSave(item);
                                        }
                                        if (event.key === "Escape") {
                                          event.preventDefault();
                                          event.stopPropagation();
                                          cancelRename();
                                        }
                                      }}
                                      className="min-w-0 flex-1 rounded-md border border-black/10 bg-white px-2 py-1 font-display text-[14px] font-medium text-black outline-none focus:border-black/30 max-tablet:w-full max-tablet:flex-none dark:border-white/10 dark:bg-[#24272b] dark:text-white dark:focus:border-white/30"
                                      aria-label={t(
                                        "command_palette.rename_conversation",
                                        "Rename conversation",
                                      )}
                                    />
                                  ) : (
                                    <span className="truncate font-display text-[14px] font-medium text-black max-tablet:w-full max-tablet:shrink-0 dark:text-white">
                                      <SearchHighlight
                                        text={item.title}
                                        query={query}
                                      />
                                    </span>
                                  )}
                                  {isCurrent && (
                                    <span className="shrink-0 rounded-full bg-[#5ba897]/15 px-2 py-0.5 text-[10px] font-semibold text-[#5ba897]">
                                      {t("common.current", "Current")}
                                    </span>
                                  )}
                                  <span className="shrink-0 rounded-full border border-black/8 px-2 py-0.5 text-[10px] font-semibold text-black/40 dark:border-white/10 dark:text-white/40">
                                    {t(
                                      commandPaletteTypeLabelKey(item.type),
                                      commandPaletteTypeFallback(item.type),
                                    )}
                                  </span>
                                  {!isCurrent &&
                                    statusLabelKey &&
                                    statusFallback && (
                                      <span className="shrink-0 rounded-full border border-black/8 px-2 py-0.5 text-[10px] font-semibold text-black/40 dark:border-white/10 dark:text-white/40">
                                        {t(statusLabelKey, statusFallback)}
                                      </span>
                                    )}
                                  {rowActionVariant === "menu" && (
                                    <span className="ml-auto me-2 shrink-0 whitespace-nowrap text-[11px] text-black/30 dark:text-white/30">
                                      {formatRelativeDate(
                                        item.updatedAt,
                                        t,
                                        i18n.language,
                                      )}
                                    </span>
                                  )}
                                </div>
                                {item.snippet && (
                                  <div className="mt-0.5 flex items-center gap-2">
                                    <span className="line-clamp-1 text-[12px] leading-relaxed text-black/40 dark:text-white/40">
                                      <SearchHighlight
                                        text={item.snippet}
                                        query={query}
                                      />
                                    </span>
                                    {item.matchCount > 1 && (
                                      <span className="shrink-0 text-[10px] text-black/30 dark:text-white/30">
                                        {t("command_palette.match_count", {
                                          count: item.matchCount,
                                          defaultValue: `${item.matchCount} matches`,
                                        })}
                                      </span>
                                    )}
                                  </div>
                                )}
                              </div>
                              {rowActionVariant !== "menu" && (
                                <span
                                  className={`absolute top-3 text-[11px] text-black/30 dark:text-white/30 ${pointerAffordances.hoverLayoutDate}`}
                                >
                                  {formatRelativeDate(
                                    item.updatedAt,
                                    t,
                                    i18n.language,
                                  )}
                                </span>
                              )}
                              {!isEditing && (
                                <CommandPaletteRowActions
                                  variant={rowActionVariant}
                                  actions={commandPaletteRowActions({
                                    item,
                                    t,
                                    navigationDisabled: isNavigationDisabled,
                                    onRename: () => startRename(item),
                                    onArchive: () => void handleArchive(item),
                                    onDelete: () => handleDelete(item),
                                    onOpenSource: () => openSourceConversation(item),
                                  })}
                                />
                              )}
                            </div>
                          );
                        })
                      )}
                    </div>
                  );
                })}
                {isResultMode && searchNextCursor && (
                  <CommandPaletteLoadMoreControl
                    errorLabel={workspaceSearch?.copy.loadMoreError}
                    failed={loadMoreFailed}
                    loading={isLoadingMoreSearch}
                    disabled={isLoadingMoreSearch || isSavingDecision}
                    onLoadMore={() => void loadMoreSearch()}
                  />
                )}
              </div>
            )}
          </div>

          {effectiveLayoutMode === "expanded" && !isBelowDesktop && (
            <div className={commandPaletteDossierPanelClassName(dossierPaneState.view)}>
              {workspaceDossier ?? dossierPaneContent}
            </div>
          )}
        </div>

        {workspaceSheet && selectedWorkspaceHit && workspaceDossier ? <BottomSheet isOpen snaps={["full"]} title={selectedWorkspaceHit.title} closeLabel={t("command_palette.close_dossier", "Close dossier")} backLabel={t("common.back", "Back")} onClose={() => setWorkspaceSheet(false)}>{workspaceDossier}</BottomSheet> : null}
        {isBelowDesktop && isDossierSheetOpen && selectedPreview ? (
          <CommandPaletteDossierSheet
            preview={selectedPreview}
            navigationDisabled={selectedNavigationDisabled}
            onClose={() => setIsDossierSheetOpen(false)}
            onOpenConversation={() => {
              if (!selectedDossier) {
                openSourceConversation(selectedPreview);
                return;
              }
              openSelectedDossierConversation({
                conversationId: selectedPreview.conversationId,
                dossier: selectedDossier,
                navigationDisabled: selectedNavigationDisabled,
                onOpenConversation: (conversationId, messageId) =>
                  onOpenConversation(conversationId, messageId),
                onClose,
              });
            }}
          >
            {dossierPaneContent}
          </CommandPaletteDossierSheet>
        ) : null}

        {isFieldOnly ? null : (
          <CommandPaletteFooter
            footerCount={footerCount}
            hasManageActions={selectedCanManageShortcutActions}
            isFiltering={isFiltering}
            isLedgerMode={isLedgerMode}
            layoutMode={effectiveLayoutMode}
            onToggleLayout={isBelowTablet || !hasPreviewPane ? undefined : toggleLayout}
            shortcutLegendVisible={shortcutLegend.isVisible}
            usesCommandKey={shortcutLegend.usesCommandKey}
          />
        )}
        <ConfirmDialog
          isOpen={Boolean(pendingDeleteItem)}
          title={t("sidebar.delete_confirm.title", "Delete this conversation?")}
          description={t(
            "sidebar.delete_confirm.description",
            "This removes “{{title}}” from your visible history.",
            {
              title:
                pendingDeleteItem?.title ??
                t("common.conversation", "Conversation"),
            },
          )}
          confirmLabel={t(
            "common.delete",
            "Delete",
          )}
          cancelLabel={t("common.cancel", "Cancel")}
          isBusy={isDeleting}
          showKeyboardHints={showDeleteKeyboardHints}
          onCancel={handleCancelDelete}
          onConfirm={() => void handleConfirmDelete()}
        />
      </div>
    </div>
  );
}

export default withViewportPortal(ChatCommandPaletteSurface);
