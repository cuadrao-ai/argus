"use client";

import { createElement, useMemo } from "react";
import { Building2, Copy, Download, FileText, House, Inbox, Mail, Plus, ReceiptText, Users } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { WorkspaceRecentSearchesServer, WorkspaceSearch, WorkspaceSearchGroup, WorkspaceSearchHit } from "@/components/chat/ChatWorkspace";
import type { BusinessAccount } from "@/lib/business-api";
import type { BusinessActions } from "./business-actions";
import type { BusinessDataSource } from "./business-data";
import BusinessSearchDossier, { type BusinessSearchRecord } from "./BusinessSearchDossier";
import { searchKindGroups } from "./business-search-groups";
import { formatDay } from "./business-format";
import { useCategoryLabel } from "./business-ui";
import type { BusinessPanelState } from "./BusinessWorkspace";
import { copyText } from "./foundation/CopyButton";
import { showToast } from "./foundation/toasts";
import { useReceiptStateWord } from "./receipt-state-word";
import { useSourceForwardAddress } from "./useForwardAddress";

/**
 * Business expenses, sales, receipts, notes, accounts, emails and email
 * senders in the shared omnisearch, with the screens and actions a person
 * reaches for. Hovering or focusing a record previews it beside the results;
 * opening it shows the panel that holds it: an expense's receipt, with its
 * original, the expense in its period's list when it has no receipt, a note's
 * draft, or an email in the Bandeja's record tray. An account has no screen
 * of its own, so its row only shows it.
 */
export function useBusinessSearch({
  source,
  accounts,
  openPanel,
  actions,
  owner,
  scope,
  openExport,
}: {
  source: BusinessDataSource;
  accounts: readonly BusinessAccount[];
  openPanel: (panel: BusinessPanelState) => void;
  actions: BusinessActions;
  /** Only the owner adds records and hands out the forwarding address, as on Inicio. */
  owner: boolean;
  /** Which Business the recent searches belong to. */
  scope: string;
  openExport: () => void;
}): WorkspaceSearch {
  const { t, i18n } = useTranslation();
  const stateWord = useReceiptStateWord();
  const categoryLabel = useCategoryLabel();
  const forwardAddress = useSourceForwardAddress(owner ? source : null);
  const locale = i18n.resolvedLanguage ?? "en";

  const recentsServer = useMemo<WorkspaceRecentSearchesServer | undefined>(() => {
    const { searchRecents, addSearchRecent, removeSearchRecent, clearSearchRecents } = source;
    if (!searchRecents || !addSearchRecent || !removeSearchRecent || !clearSearchRecents) return undefined;
    return { list: searchRecents, add: addSearchRecent, remove: removeSearchRecent, clear: clearSearchRecents };
  }, [source]);

  return useMemo<WorkspaceSearch>(() => {
    const line = (...parts: (string | null | undefined)[]) => parts.filter(Boolean).join(" · ");
    const preview = (record: BusinessSearchRecord) => createElement(BusinessSearchDossier, { record, source, accounts });
    const screen = t("business.search.badge_screen", "Screen");
    const action = t("business.search.badge_action", "Action");
    const go = (id: string, icon: WorkspaceSearchHit["icon"], title: string, panel: BusinessPanelState, keywords?: string): WorkspaceSearchHit =>
      ({ id, icon, title, detail: "", amount: null, badge: screen, keywords, open: () => openPanel(panel) });
    const add = owner ? actions.create.find((item) => item.id === "upload_receipt") : undefined;
    const copyAddress = owner && forwardAddress ? async () => {
      const copied = await copyText(forwardAddress);
      if (copied) showToast({ kind: "success", text: t("business.email.copied", "Address copied.") });
      else openPanel({ kind: "business", tab: "correo" });
    } : null;
    const shortcuts: WorkspaceSearchGroup[] = [
      {
        id: "screens",
        label: t("business.search.go_to", "Go to"),
        hits: [
          go("overview", House, t("business.nav.overview", "Home"), { kind: "overview" }),
          go("inbox", Inbox, t("business.nav.inbox", "Inbox"), { kind: "inbox" }),
          go("expenses", ReceiptText, t("business.nav.expenses", "Expenses"), { kind: "expenses" }),
          go("business", Building2, t("business.nav.business", "Business"), { kind: "business" }, t("business.search.keywords_business", "settings details tax")),
          go("team", Users, t("business.search.go_team", "Team and access"), { kind: "business", tab: "equipo" }, t("business.search.keywords_team", "accountant people")),
          go("correo", Mail, t("business.settings.tab_correo", "Receipt email"), { kind: "business", tab: "correo" }, t("business.search.keywords_correo", "emails history forwarding")),
        ],
      },
      {
        id: "actions",
        label: t("business.search.actions", "Actions"),
        hits: [
          ...(add ? [{ id: "add", icon: Plus, title: add.label, detail: "", amount: null, badge: action, keywords: t("business.search.keywords_add", "upload receipt photo file note"), open: add.run }] : []),
          { id: "export", icon: Download, title: t("business.overview.export_records", "Export records"), detail: "", amount: null, badge: action, keywords: "606 607", open: openExport },
          ...(copyAddress ? [{ id: "copy_forward", icon: Copy, title: t("business.overview.copy_forward", "Copy forwarding address"), detail: "", amount: null, badge: action, keywords: t("business.search.keywords_copy_forward", "email"), open: () => void copyAddress() }] : []),
        ],
      },
    ];
    return {
      previewAvailable: true,
      shortcuts,
      recents: { key: "cuadrao:business_recent_searches:v1", scope, server: recentsServer },
      copy: {
        placeholder: t("business.search.placeholder", "Search a merchant, amount or note"),
        noResultsHint: t("business.search.no_results_hint", "Search by merchant, amount, category, account or note text."),
        region: t("business.search.region", "Business records"),
        loading: t("business.search.loading", "Searching your business"),
        failed: t("business.search.failed", "We couldn't search your business."),
        retry: t("command_palette.retry_search", "Try searching again"),
        recent: t("business.search.recent", "Recent searches"),
        showMore: (count) => t("business.search.show_more", { count, defaultValue: "See {{count}} more" }),
        showLess: t("business.search.show_less", "See less"),
        loadMore: t("business.search.load_more", "Load more"),
        loadMoreFailed: t("business.search.load_more_failed", "We couldn't load more results. The ones shown are still here."),
        retryLoad: t("business.search.retry_load", "Retry"),
        removeRecent: (query) => t("business.search.recent_remove", { query, defaultValue: "Remove “{{query}}” from recent searches" }),
        clearRecents: t("business.search.recent_clear", "Clear all"),
        noMatch: (query) => t("business.search.no_match", { query, defaultValue: "Nothing matched “{{query}}”." }),
        keepTyping: t("business.search.keep_typing", "Type at least 3 letters to search your records."),
        readError: t("business.search.chats_failed", "We couldn't load your chats. Your records are still shown."),
        loadMoreError: t("business.search.chats_more_failed", "We couldn't load more chats. The ones shown are still here."),
        ask: t("business.search.ask", "Ask in a new chat"),
        close: t("common.close", "Close"),
      },
      find: async (query) => {
        const [records, captures] = await Promise.allSettled([source.search(query), source.captures(query)]);
        if (records.status === "rejected") throw records.reason;
        const kinds = searchKindGroups({ t, locale, source, accounts, openPanel, stateWord, categoryLabel }, query, records.value);
        const notes: WorkspaceSearchGroup = {
          id: "captures",
          label: t("business.capture.notes", "Original notes"),
          ...(captures.status === "rejected" ? { error: t("business.capture.search_failed", "Notes are unavailable. Other record results are shown below.") } : {}),
          hits: captures.status === "fulfilled" ? captures.value.map((note) => ({
            id: note.source_id,
            icon: FileText,
            title: note.text,
            detail: line(t("business.capture.saved_note", "Saved original note"), formatDay(note.received_at, locale), t("business.dossier.revision", "Revision {{version}}", { version: note.revision }), t(`business.dossier.state.${note.review_state}`, note.review_state)),
            amount: null,
            badge: t("business.search.badge_note", "Note"),
            preview: preview({ kind: "note", note }),
            open: () => openPanel({ kind: "draft", draftId: note.draft_id, list: "inbox" }),
          })) : [],
        };
        return [kinds.expenses, kinds.ventas, kinds.receipts, notes, kinds.accounts, kinds.email_deliveries, kinds.email_senders];
      },
    };
  }, [accounts, actions.create, categoryLabel, forwardAddress, locale, openPanel, owner, recentsServer, scope, source, stateWord, t]);
}
