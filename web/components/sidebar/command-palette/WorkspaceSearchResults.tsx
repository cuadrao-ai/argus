"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { History, Loader2, MessageSquareWarning } from "lucide-react";
import type { WorkspaceSearch, WorkspaceSearchGroup, WorkspaceSearchHit } from "@/components/chat/ChatWorkspace";
import { readStored, writeStored } from "@/lib/browser-storage";
import { panelFailureIconClass } from "@/lib/failure-treatment";
import { normalizeSearchText, searchQueryIsIndexable } from "@/lib/search-text";

const DEBOUNCE_MS = 200;
export const HOVER_PREVIEW_MS = 200;
/** Rows a record group shows before Ver más reveals the rest it already holds. */
export const WORKSPACE_GROUP_ROWS = 3;
export const RECENT_SEARCHES = 5;
const HIT = "data-workspace-hit";

const ROW_CLASS =
  "flex min-h-11 w-full items-center gap-3 rounded-[12px] px-3 py-2.5 text-left transition-colors hover:bg-black/[0.03] focus:bg-black/[0.04] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-[#2f5a49] dark:hover:bg-white/[0.03] dark:focus:bg-white/[0.05] dark:focus-visible:outline-[#8fcbb0]";
const LABEL_CLASS = "font-display text-[12px] font-medium text-[#56635e] dark:text-white/65";
const MUTED_CLASS = "text-[#56635e] dark:text-white/65";

export type WorkspaceSearchState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "failed" }
  | { status: "ready"; groups: readonly WorkspaceSearchGroup[] };

function folded(value: string): string[] {
  const text = normalizeSearchText(value.normalize("NFD").replace(/\p{M}/gu, ""));
  return text ? text.split(" ") : [];
}

/** Screens and actions whose words start with every word typed, accents and case aside. */
export function matchShortcuts(groups: readonly WorkspaceSearchGroup[], query: string): WorkspaceSearchGroup[] {
  const typed = folded(query);
  if (typed.length === 0) return [];
  return groups
    .map((group) => ({
      ...group,
      hits: group.hits.filter((hit) => {
        const words = folded(`${hit.title} ${hit.keywords ?? ""}`);
        return typed.every((part) => words.some((word) => word.startsWith(part)));
      }),
    }))
    .filter((group) => group.hits.length > 0);
}

/**
 * Runs the workspace's own search beside the conversation search, on the same
 * debounce and the same "keep typing" threshold. Only the latest query's
 * answer is kept. Screens and actions match on the device at once.
 */
export function useWorkspaceSearch(search: WorkspaceSearch | null, query: string) {
  const [state, setState] = useState<WorkspaceSearchState>({ status: "idle" });
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
  const shortcuts = search ? matchShortcuts(search.shortcuts, trimmed) : [];
  const hasHits = shortcuts.length > 0 || (state.status === "ready" && state.groups.length > 0);
  /** Nothing of the workspace's is showing or still coming. */
  const quiet = !hasHits && (state.status === "idle" || state.status === "ready");
  return { state, shortcuts, retry, hasHits, quiet };
}

function storedRecents(recents: WorkspaceSearch["recents"]): Record<string, unknown> {
  try {
    const parsed: unknown = JSON.parse(readStored(recents.key) ?? "{}");
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? (parsed as Record<string, unknown>) : {};
  } catch {
    return {};
  }
}

function scopedRecents(all: Record<string, unknown>, scope: string): string[] {
  const list = all[scope];
  return Array.isArray(list) ? list.filter((item): item is string => typeof item === "string").slice(0, RECENT_SEARCHES) : [];
}

/** The queries this browser remembers for one scope, newest first. */
export function useRecentSearches(recents: WorkspaceSearch["recents"] | null) {
  const [items, setItems] = useState<string[]>(() => (recents ? scopedRecents(storedRecents(recents), recents.scope) : []));
  const remember = useCallback((query: string) => {
    const text = query.trim();
    if (!recents || !text) return;
    const all = storedRecents(recents);
    const same = folded(text).join(" ");
    const next = [text, ...scopedRecents(all, recents.scope).filter((item) => folded(item).join(" ") !== same)].slice(0, RECENT_SEARCHES);
    writeStored(recents.key, JSON.stringify({ ...all, [recents.scope]: next }));
    setItems(next);
  }, [recents]);
  return { items, remember };
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
  return <span className="shrink-0 rounded-full border border-black/10 px-2 py-0.5 text-[11px] font-medium text-[#56635e] dark:border-white/15 dark:text-white/70">{children}</span>;
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

function HitGroup({ group, rows, handlers, showMore, showLess }: { group: WorkspaceSearchGroup; rows: number | null; handlers: RowHandlers; showMore: (count: number) => string; showLess: string }) {
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
        <button type="button" {...{ [HIT]: "" }} data-row-action aria-expanded={expanded} onClick={() => setExpanded((value) => !value)} className={`${ROW_CLASS} text-[13px] font-medium text-[#2f5a49] dark:text-[#8fcbb0]`}>
          {expanded ? showLess : showMore(hidden)}
        </button>
      ) : null}
    </div>
  );
}

function ShortcutGroups({ search, groups, onOpened }: { search: WorkspaceSearch; groups: readonly WorkspaceSearchGroup[]; onOpened: () => void }) {
  return <>{groups.map((group) => <HitGroup key={group.id} group={group} rows={null} handlers={{ onOpened }} showMore={search.copy.showMore} showLess={search.copy.showLess} />)}</>;
}

/** Before a query: what this browser searched lately, then where to go and what to do. */
export function WorkspaceSearchHome({ search, recent, onFill, onOpened }: { search: WorkspaceSearch; recent: readonly string[]; onFill: (query: string) => void; onOpened: () => void }) {
  return (
    <section aria-label={search.copy.region} data-testid="workspace-search-home" className="flex flex-col gap-3 px-3 pt-3">
      {recent.length ? (
        <div role="group" aria-label={search.copy.recent}>
          <div className="px-2 pb-1.5 pt-1"><span className={LABEL_CLASS}>{search.copy.recent}</span></div>
          {recent.map((text) => (
            <button key={text} type="button" {...{ [HIT]: "" }} data-row-action data-recent-search onClick={() => onFill(text)} className={ROW_CLASS}>
              <History className={`h-4 w-4 shrink-0 ${MUTED_CLASS}`} aria-hidden="true" />
              <span className="min-w-0 flex-1 truncate text-[14px] text-[#172b26] dark:text-white">{text}</span>
            </button>
          ))}
        </div>
      ) : null}
      <ShortcutGroups search={search} groups={search.shortcuts} onOpened={onOpened} />
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
}: RowHandlers & {
  search: WorkspaceSearch;
  state: WorkspaceSearchState;
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
      {records.map((group) => <HitGroup key={group.id} group={group} rows={WORKSPACE_GROUP_ROWS} handlers={handlers} showMore={copy.showMore} showLess={copy.showLess} />)}
    </section>
  );
}
