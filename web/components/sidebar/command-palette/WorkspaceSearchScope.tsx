"use client";

import { useMemo, useState, type KeyboardEvent } from "react";
import { ListFilter, X } from "lucide-react";
import type { WorkspaceSearch, WorkspaceSearchScope } from "@/components/chat/ChatWorkspace";

/**
 * A workspace search that starts scoped to the list on screen (Business Bandeja, Registros). The scope keeps its
 * list's kinds of results and its actions, and no screens, since the list is where the person already is.
 * Removing the scope (its chip's ×, or Backspace in an empty field) searches everything for the rest of the visit.
 * A scope that keeps no kinds of results (a Facturación section) has nothing to ask the server, so `searchesRecords`
 * is false and the window runs no search: only the filter row and the scope's own actions show.
 */
export function useWorkspaceSearchScope(search: WorkspaceSearch | null) {
  const [removed, setRemoved] = useState(false);
  const scope = removed ? null : search?.scope ?? null;
  const scopedSearch = useMemo(() => {
    if (!search || !scope) return search;
    const { groups, actions } = scope;
    return {
      ...search,
      find: async (text: string) => (await search.find(text)).filter((group) => groups.includes(group.id)),
      shortcuts: search.shortcuts.flatMap((group) => (group.id === "actions" ? [{ ...group, hits: group.hits.filter((hit) => actions.includes(hit.id)) }] : [])),
    };
  }, [search, scope]);
  const searchesRecords = !scope || scope.groups.length > 0;
  return { scope, scopedSearch, searchesRecords, remove: () => setRemoved(true) };
}

/** In a scope, Backspace on an empty field removes it and Enter filters the list by the query, then closes. */
export function scopeKeyDown(scope: WorkspaceSearchScope | null, query: string, remove: () => void, close: () => void) {
  if (!scope) return undefined;
  return (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Backspace" && !query) { event.preventDefault(); remove(); }
    else if (event.key === "Enter" && query.trim() && scope.apply && !event.nativeEvent.isComposing) { event.preventDefault(); event.stopPropagation(); scope.apply(query.trim()); close(); }
  };
}

export function WorkspaceScopeChip({ scope, onRemove }: { scope: WorkspaceSearchScope; onRemove: () => void }) {
  return (
    <span data-testid="workspace-search-scope" className="inline-flex shrink-0 items-center gap-0.5 rounded-mark bg-black/5 py-0.5 pl-2 pr-0.5 text-[14px] font-medium text-[#172b26] dark:bg-white/10 dark:text-white">
      {scope.chip}
      <button type="button" aria-label={scope.clearLabel} onClick={onRemove} className="inline-flex h-8 w-8 items-center justify-center rounded-[6px] text-[#56635e] hover:bg-black/5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#2f5a49] dark:text-white/70 dark:hover:bg-white/10">
        <X className="h-3.5 w-3.5" aria-hidden="true" />
      </button>
    </span>
  );
}

/** The scoped window's first row: hand the query to the list on screen and close, as Enter does. */
export function ScopeFilterRow({ label, onApply }: { label: string; onApply: () => void }) {
  return (
    <div className="px-3 pt-3">
      <button type="button" data-workspace-hit="" data-testid="workspace-search-filter-list" onClick={onApply} className="flex min-h-11 w-full items-center gap-3 rounded-item px-3 text-left text-[15px] font-medium text-[#172b26] hover:bg-black/[0.04] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#2f5a49] dark:text-white dark:hover:bg-white/[0.05]">
        <ListFilter className="h-4 w-4 shrink-0 text-[#56635e] dark:text-white/70" aria-hidden="true" />
        <span className="min-w-0 flex-1 truncate">{label}</span>
        <kbd className="shrink-0 rounded-mark border border-black/10 px-1.5 font-sans text-[12px] text-[#56635e] dark:border-white/15 dark:text-white/60">↵</kbd>
      </button>
    </div>
  );
}
