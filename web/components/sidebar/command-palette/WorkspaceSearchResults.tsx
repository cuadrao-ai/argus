"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Loader2, MessageSquareWarning } from "lucide-react";
import type { WorkspaceSearch, WorkspaceSearchGroup } from "@/components/chat/ChatWorkspace";
import { panelFailureIconClass } from "@/lib/failure-treatment";
import { searchQueryIsIndexable } from "@/lib/search-text";

const DEBOUNCE_MS = 200;
const HIT = "data-workspace-hit";

export type WorkspaceSearchState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "failed" }
  | { status: "ready"; groups: readonly WorkspaceSearchGroup[] };

/**
 * Runs the workspace's own search beside the conversation search, on the same
 * debounce and the same "keep typing" threshold. Only the latest query's
 * answer is kept.
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
  const hasHits = state.status === "ready" && state.groups.length > 0;
  /** Nothing of the workspace's is showing or still coming. */
  const quiet = state.status === "idle" || (state.status === "ready" && !hasHits);
  return { state, retry, hasHits, quiet };
}

/**
 * Up and Down walk the workspace hits, then hand over to the conversation rows
 * below them. Returns whether it moved focus. The palette's own keys run
 * otherwise, so Enter on a hit stays the hit's own click.
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

export function WorkspaceSearchResults({
  search,
  state,
  retry,
  onOpened,
}: {
  search: WorkspaceSearch;
  state: WorkspaceSearchState;
  retry: () => void;
  onOpened: () => void;
}) {
  const { copy } = search;
  if (state.status === "idle") return null;
  if (state.status === "loading") {
    return (
      <div role="status" className="flex items-center gap-2 px-5 pt-4 text-[13px] text-black/45 dark:text-white/45">
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
        {copy.loading}
      </div>
    );
  }
  if (state.status === "failed") {
    return (
      <div role="alert" className="flex flex-wrap items-center gap-2 px-5 pt-4 text-[13px] text-black/55 dark:text-white/55">
        <MessageSquareWarning className={`h-4 w-4 ${panelFailureIconClass}`} aria-hidden="true" />
        <span>{copy.failed}</span>
        <button
          type="button"
          data-row-action
          onClick={retry}
          className="min-h-11 rounded-full px-3 font-medium text-black/70 underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-black/20 dark:text-white/70 dark:focus-visible:ring-white/25"
        >
          {copy.retry}
        </button>
      </div>
    );
  }
  if (state.groups.length === 0) return null;
  return (
    <section aria-label={copy.region} data-testid="workspace-search-results" className="flex flex-col gap-3 px-3 pt-3">
      {state.groups.map((group) => (
        <div key={group.id} role="group" aria-label={group.label}>
          <div className="px-2 pb-1.5 pt-1">
            <span className="font-display text-[11px] font-semibold uppercase tracking-wider text-black/40 dark:text-white/40">
              {group.label}
            </span>
          </div>
          {group.error ? <p role="alert" className="px-3 py-2 text-[13px] text-black/60 dark:text-white/60">{group.error}</p> : null}
          {group.hits.map((hit) => {
            const Icon = hit.icon;
            return (
              <button
                key={hit.id}
                type="button"
                {...{ [HIT]: "" }}
                data-row-action
                onClick={() => {
                  onOpened();
                  hit.open();
                }}
                className="flex min-h-11 w-full items-center gap-3 rounded-[12px] px-3 py-2.5 text-left outline-none transition-colors hover:bg-black/[0.03] focus:bg-black/5 focus:ring-2 focus:ring-black/20 dark:hover:bg-white/[0.03] dark:focus:bg-white/5 dark:focus:ring-white/25"
              >
                <Icon className="h-4 w-4 shrink-0 text-black/45 dark:text-white/45" aria-hidden="true" />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[14px] font-medium text-black dark:text-white">{hit.title}</span>
                  <span className="block truncate text-[12px] text-black/45 dark:text-white/45">{hit.detail}</span>
                </span>
                {hit.amount ? (
                  <span className="shrink-0 text-[14px] font-medium tabular-nums text-black/80 dark:text-white/80">
                    {hit.amount}
                  </span>
                ) : null}
              </button>
            );
          })}
        </div>
      ))}
    </section>
  );
}
