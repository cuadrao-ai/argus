"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { History, Loader2, MessageSquareWarning, X } from "lucide-react";
import type { WorkspaceSearch, WorkspaceSearchGroup, WorkspaceSearchHit, WorkspaceSearchPage } from "@/components/chat/ChatWorkspace";
import { panelFailureIconClass } from "@/lib/failure-treatment";
import { searchQueryIsIndexable } from "@/lib/search-text";
import { foldedWords } from "./search-fold";
import type { RecentSearches } from "./useRecentSearches";

export { useRecentSearches } from "./useRecentSearches";

const DEBOUNCE_MS = 200;
export const HOVER_PREVIEW_MS = 200;
/** Rows a record group shows before Ver más reveals the rest it already holds. */
export const WORKSPACE_GROUP_ROWS = 3;
const HIT = "data-workspace-hit";

const ROW_CLASS =
  "flex min-h-11 w-full items-center gap-3 rounded-item px-3 py-2.5 text-left transition-colors hover:bg-black/[0.03] focus:bg-black/[0.04] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-[#2f5a49] dark:hover:bg-white/[0.03] dark:focus:bg-white/[0.05] dark:focus-visible:outline-[#8fcbb0]";
const LABEL_CLASS = "font-display text-[12px] font-medium text-[#56635e] dark:text-white/65";
const MUTED_CLASS = "text-[#56635e] dark:text-white/65";
const ACTION_CLASS = "text-[13px] font-medium text-[#2f5a49] dark:text-[#8fcbb0]";

export type WorkspaceSearchState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "failed" }
  | { status: "ready"; groups: readonly WorkspaceSearchGroup[] };

/** Screens and actions whose words start with every word typed, accents and case aside. */
export function matchShortcuts(groups: readonly WorkspaceSearchGroup[], query: string): WorkspaceSearchGroup[] {
  const typed = foldedWords(query);
  if (typed.length === 0) return [];
  return groups
    .map((group) => ({
      ...group,
      hits: group.hits.filter((hit) => {
        const words = foldedWords(`${hit.title} ${hit.keywords ?? ""}`);
        return typed.every((part) => words.some((word) => word.startsWith(part)));
      }),
    }))
    .filter((group) => group.hits.length > 0);
}

export type GroupLoad = "loading" | "error";

/** A group with the page that came after its first rows; a restarted page replaces them. */
function withPage(group: WorkspaceSearchGroup, page: WorkspaceSearchPage): WorkspaceSearchGroup {
  const known = new Set(page.restarted ? [] : group.hits.map((hit) => hit.id));
  return { ...group, hits: page.restarted ? page.hits : [...group.hits, ...page.hits.filter((hit) => !known.has(hit.id))], loadMore: page.loadMore };
}

/**
 * Runs the workspace's own search beside the conversation search, on the same
 * debounce and the same "keep typing" threshold. Only the latest query's
 * answer is kept. Screens and actions match on the device at once. Rows a
 * group loads after its first page join the group here, so the footer count
 * and the preview see them like the first rows.
 */
export function useWorkspaceSearch(search: WorkspaceSearch | null, query: string) {
  const [state, setState] = useState<WorkspaceSearchState>({ status: "idle" });
  const [loads, setLoads] = useState<Readonly<Record<string, GroupLoad>>>({});
  const [attempt, setAttempt] = useState(0);
  const latest = useRef(0);
  const current = useRef(search);
  const trimmed = query.trim();
  const enabled = search !== null;

  // A new query or retry searches again; a re-rendered workspace does not.
  useEffect(() => {
    current.current = search;
  }, [search]);

  useEffect(() => {
    const request = ++latest.current;
    setLoads({});
    if (!enabled || !searchQueryIsIndexable(trimmed)) {
      setState({ status: "idle" });
      return;
    }
    setState({ status: "loading" });
    const timer = setTimeout(() => {
      current.current
        ?.find(trimmed)
        .then((groups) => {
          if (latest.current === request) {
            setState({ status: "ready", groups: groups.filter((group) => group.hits.length > 0 || Boolean(group.error)) });
          }
        })
        .catch(() => {
          if (latest.current === request) setState({ status: "failed" });
        });
    }, DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [attempt, enabled, trimmed]);

  const retry = useCallback(() => setAttempt((value) => value + 1), []);

  const groups = state.status === "ready" ? state.groups : null;
  const loadMore = useCallback((groupId: string) => {
    const next = groups?.find((group) => group.id === groupId)?.loadMore;
    if (!next) return;
    const request = latest.current;
    setLoads((value) => ({ ...value, [groupId]: "loading" }));
    next().then(
      (page) => {
        if (latest.current !== request) return;
        setState((value) => (value.status === "ready" ? { status: "ready", groups: value.groups.map((group) => (group.id === groupId ? withPage(group, page) : group)) } : value));
        setLoads((value) => Object.fromEntries(Object.entries(value).filter(([id]) => id !== groupId)));
      },
      () => {
        if (latest.current === request) setLoads((value) => ({ ...value, [groupId]: "error" }));
      },
    );
  }, [groups]);

  const shortcuts = search ? matchShortcuts(search.shortcuts, trimmed) : [];
  const hasHits = shortcuts.length > 0 || (state.status === "ready" && state.groups.length > 0);
  /** Nothing of the workspace's is showing or still coming. */
  const quiet = !hasHits && (state.status === "idle" || state.status === "ready");
  return { state, shortcuts, retry, hasHits, quiet, loads, loadMore };
}

/**
 * Up and Down walk the workspace rows, then hand over to the conversation rows
 * below them. Returns whether it moved focus. The palette's own keys run
 * otherwise, so Enter on a row stays the row's own click.
 */
export function moveWorkspaceFocus(event: KeyboardEvent, input: HTMLInputElement | null): boolean {
  if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return false;
  const hits = Array.from(document.querySelectorAll<HTMLElement>(`[${HIT}]`));
  if (hits.length === 0 || !(event.target instanceof HTMLElement)) return false;
  const down = event.key === "ArrowDown";
  const index = hits.findIndex((hit) => hit === event.target);
  const firstRow = document.querySelector<HTMLElement>('[data-palette-row-index="0"]');
  let next: HTMLElement | null | undefined = null;
  if (event.target === input) next = down ? hits[0] : null;
  else if (index >= 0) next = down ? (hits[index + 1] ?? firstRow) : (hits[index - 1] ?? input);
  else if (!down && event.target === firstRow) next = hits[hits.length - 1];
  if (!next) return false;
  event.preventDefault();
  next.focus();
  return true;
}

type RowHandlers = {
  onOpened: () => void;
  /** Hover and keyboard focus show the hit's record without opening it. */
  onPreview?: (groupId: string, hit: WorkspaceSearchHit) => void;
  /** Click and Enter keep the hit's record in the pane or sheet. */
  onSelect?: (groupId: string, hit: WorkspaceSearchHit) => void;
  /** A record was chosen from this query, so the query is worth remembering. */
  onChosen?: () => void;
  selectedKey?: string;
};

function Badge({ children }: { children: string }) {
  return <span className="shrink-0 rounded-mark border border-black/10 px-2 py-0.5 text-[11px] font-medium text-[#56635e] dark:border-white/15 dark:text-white/70">{children}</span>;
}

function HitBody({ hit }: { hit: WorkspaceSearchHit }) {
  const Icon = hit.icon;
  return <>
    <Icon className={`h-4 w-4 shrink-0 ${MUTED_CLASS}`} aria-hidden="true" />
    <span className="min-w-0 flex-1">
      <span className="block truncate text-[14px] font-medium text-[#172b26] dark:text-white">{hit.title}</span>
      {hit.detail ? <span className={`block truncate text-[12px] ${MUTED_CLASS}`}>{hit.detail}</span> : null}
    </span>
    <Badge>{hit.badge}</Badge>
    {hit.amount ? <span className="cuadrao-amount shrink-0 text-[14px] font-medium tabular-nums text-[#172b26] dark:text-white/85">{hit.amount}</span> : null}
  </>;
}

function HitGroup({ group, rows, handlers, copy, load, onLoadMore }: { group: WorkspaceSearchGroup; rows: number | null; handlers: RowHandlers; copy: WorkspaceSearch["copy"]; load?: GroupLoad; onLoadMore?: (groupId: string) => void }) {
  const { onOpened, onPreview, onSelect, onChosen, selectedKey } = handlers;
  const [expanded, setExpanded] = useState(false);
  // Hover waits a beat so a pointer crossing the list does not fetch every record.
  const hoverTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const cancelHover = () => {
    if (hoverTimer.current !== null) clearTimeout(hoverTimer.current);
    hoverTimer.current = null;
  };
  useEffect(() => cancelHover, []);
  const hidden = rows === null ? 0 : Math.max(0, group.hits.length - rows);
  const shown = rows === null || expanded ? group.hits : group.hits.slice(0, rows);
  // Ver más shows rows already loaded; Cargar más asks for the next page, and only once none are left hidden.
  const revealPending = !expanded && hidden > 0;
  return (
    <div role="group" aria-label={group.label} data-workspace-group={group.id}>
      <div className="px-2 pb-1.5 pt-1"><span className={LABEL_CLASS}>{group.label}</span></div>
      {group.error ? <p role="alert" className={`px-3 py-2 text-[13px] ${MUTED_CLASS}`}>{group.error}</p> : null}
      {shown.map((hit) => {
        const open = hit.open;
        if (!open) {
          return <div key={hit.id} data-testid="workspace-hit-static" className="flex min-h-11 w-full items-center gap-3 px-3 py-2.5"><HitBody hit={hit} /></div>;
        }
        return (
          <button
            key={hit.id}
            type="button"
            {...{ [HIT]: "" }}
            data-row-action
            aria-pressed={onSelect && hit.preview ? selectedKey === `${group.id}:${hit.id}` : undefined}
            onMouseEnter={hit.preview && onPreview ? () => {
              cancelHover();
              hoverTimer.current = setTimeout(() => onPreview(group.id, hit), HOVER_PREVIEW_MS);
            } : undefined}
            onMouseLeave={hit.preview ? cancelHover : undefined}
            onFocus={hit.preview ? () => onPreview?.(group.id, hit) : undefined}
            onClick={(event) => {
              cancelHover();
              onChosen?.();
              // One pointer click or tap keeps the record in the pane; Enter,
              // Space and a double click open it, as every row did before.
              if (onSelect && hit.preview && event.detail === 1) {
                onSelect(group.id, hit);
                return;
              }
              onOpened();
              open();
            }}
            className={ROW_CLASS}
          >
            <HitBody hit={hit} />
          </button>
        );
      })}
      {hidden > 0 ? (
        <button type="button" {...{ [HIT]: "" }} data-row-action data-group-reveal aria-expanded={expanded} onClick={() => setExpanded((value) => !value)} className={`${ROW_CLASS} ${ACTION_CLASS}`}>
          {expanded ? copy.showLess : copy.showMore(hidden)}
        </button>
      ) : null}
      {!revealPending && group.loadMore && onLoadMore ? (
        <>
          {load === "error" ? <p role="alert" data-group-load-error className={`px-3 pt-1 text-[13px] ${MUTED_CLASS}`}>{copy.loadMoreFailed}</p> : null}
          <button type="button" {...{ [HIT]: "" }} data-row-action data-group-load disabled={load === "loading"} aria-busy={load === "loading"} onClick={() => onLoadMore(group.id)} className={`${ROW_CLASS} ${ACTION_CLASS} disabled:opacity-60`}>
            {load === "loading" ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : null}
            {load === "error" ? copy.retryLoad : copy.loadMore}
          </button>
        </>
      ) : null}
    </div>
  );
}

function ShortcutGroups({ search, groups, onOpened }: { search: WorkspaceSearch; groups: readonly WorkspaceSearchGroup[]; onOpened: () => void }) {
  return <>{groups.map((group) => <HitGroup key={group.id} group={group} rows={null} handlers={{ onOpened }} copy={search.copy} />)}</>;
}

/** Before a query: what was searched lately, then where to go and what to do (`groups`, when the window trims them). */
export function WorkspaceSearchHome({ search, groups = search.shortcuts, recents, onFill, onOpened }: { search: WorkspaceSearch; groups?: readonly WorkspaceSearchGroup[]; recents: RecentSearches; onFill: (query: string) => void; onOpened: () => void }) {
  return (
    <section aria-label={search.copy.region} data-testid="workspace-search-home" className="flex flex-col gap-3 px-3 pt-3">
      {recents.items.length ? (
        <div role="group" aria-label={search.copy.recent}>
          <div className="flex items-center justify-between px-2 pb-1.5 pt-1">
            <span className={LABEL_CLASS}>{search.copy.recent}</span>
            <button type="button" {...{ [HIT]: "" }} data-row-action data-recent-clear onClick={recents.clear} className={`min-h-11 rounded-full px-3 ${ACTION_CLASS} hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#2f5a49] dark:focus-visible:outline-[#8fcbb0]`}>
              {search.copy.clearRecents}
            </button>
          </div>
          {recents.items.map((item) => (
            <div key={item.id ?? item.q} className="flex items-center">
              <button type="button" {...{ [HIT]: "" }} data-row-action data-recent-search onClick={() => onFill(item.q)} className={`${ROW_CLASS} flex-1`}>
                <History className={`h-4 w-4 shrink-0 ${MUTED_CLASS}`} aria-hidden="true" />
                <span className="min-w-0 flex-1 truncate text-[14px] text-[#172b26] dark:text-white">{item.q}</span>
              </button>
              <button type="button" {...{ [HIT]: "" }} data-row-action data-recent-remove aria-label={search.copy.removeRecent(item.q)} onClick={() => recents.remove(item)} className={`flex min-h-11 min-w-11 shrink-0 items-center justify-center rounded-full ${MUTED_CLASS} hover:bg-black/[0.04] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#2f5a49] dark:hover:bg-white/[0.05] dark:focus-visible:outline-[#8fcbb0]`}>
                <X className="h-4 w-4" aria-hidden="true" />
              </button>
            </div>
          ))}
        </div>
      ) : null}
      <ShortcutGroups search={search} groups={groups} onOpened={onOpened} />
    </section>
  );
}

/** Nothing matched: say so, say what search reads, and offer every screen and action. */
export function WorkspaceSearchNoMatch({ search, query, waiting, onOpened }: { search: WorkspaceSearch; query: string; waiting: boolean; onOpened: () => void }) {
  return (
    <section aria-label={search.copy.region} data-testid="workspace-search-no-match" className="flex flex-col gap-3 px-3 pt-3">
      <div className="px-2 py-3" aria-live="polite">
        <p className="text-[15px] font-medium text-[#172b26] dark:text-white">{waiting ? search.copy.keepTyping : search.copy.noMatch(query.trim())}</p>
        <p className={`mt-1 text-[13px] ${MUTED_CLASS}`}>{search.copy.noResultsHint}</p>
      </div>
      <ShortcutGroups search={search} groups={search.shortcuts} onOpened={onOpened} />
    </section>
  );
}

export function WorkspaceSearchResults({
  search,
  state,
  shortcuts = [],
  retry,
  onOpened,
  onPreview,
  onSelect,
  onChosen,
  selectedKey,
  loads = {},
  loadMore,
}: RowHandlers & {
  search: WorkspaceSearch;
  state: WorkspaceSearchState;
  /** Which groups are fetching their next page or failed to. */
  loads?: Readonly<Record<string, GroupLoad>>;
  loadMore?: (groupId: string) => void;
  /** Screens and actions the query matched; they sit first because they never wait on the network. */
  shortcuts?: readonly WorkspaceSearchGroup[];
  retry: () => void;
}) {
  const { copy } = search;
  const handlers: RowHandlers = { onOpened, onPreview, onSelect, onChosen, selectedKey };
  const records = state.status === "ready" ? state.groups : [];
  if (state.status === "idle" && shortcuts.length === 0) return null;
  if (state.status === "ready" && records.length === 0 && shortcuts.length === 0) return null;
  return (
    <section aria-label={copy.region} data-testid="workspace-search-results" className="flex flex-col gap-3 px-3 pt-3">
      <ShortcutGroups search={search} groups={shortcuts} onOpened={onOpened} />
      {state.status === "loading" ? (
        <div role="status" className={`flex items-center gap-2 px-2 pt-1 text-[13px] ${MUTED_CLASS}`}>
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          {copy.loading}
        </div>
      ) : null}
      {state.status === "failed" ? (
        <div role="alert" className={`flex flex-wrap items-center gap-2 px-2 pt-1 text-[13px] ${MUTED_CLASS}`}>
          <MessageSquareWarning className={`h-4 w-4 ${panelFailureIconClass}`} aria-hidden="true" />
          <span>{copy.failed}</span>
          <button
            type="button"
            data-row-action
            onClick={retry}
            className="min-h-11 rounded-full px-3 font-medium text-[#2f5a49] underline-offset-2 hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#2f5a49] dark:text-[#8fcbb0]"
          >
            {copy.retry}
          </button>
        </div>
      ) : null}
      {records.map((group) => <HitGroup key={group.id} group={group} rows={WORKSPACE_GROUP_ROWS} handlers={handlers} copy={copy} load={loads[group.id]} onLoadMore={loadMore} />)}
    </section>
  );
}
