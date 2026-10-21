"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { WorkspaceSearch } from "@/components/chat/ChatWorkspace";
import { readStored, writeStored } from "@/lib/browser-storage";
import { foldedWords } from "./search-fold";

export const RECENT_SEARCHES = 5;

/** `id` is the server's handle; a query only this browser remembers has none. */
export type RecentSearch = Readonly<{ id: string | null; q: string }>;

export type RecentSearches = Readonly<{
  items: readonly RecentSearch[];
  remember: (query: string) => void;
  remove: (item: RecentSearch) => void;
  clear: () => void;
}>;

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

const same = (a: string, b: string) => foldedWords(a).join(" ") === foldedWords(b).join(" ");
const local = (recents: WorkspaceSearch["recents"] | null): RecentSearch[] =>
  recents ? scopedRecents(storedRecents(recents), recents.scope).map((q) => ({ id: null, q })) : [];

function writeLocal(recents: WorkspaceSearch["recents"], next: string[]) {
  writeStored(recents.key, JSON.stringify({ ...storedRecents(recents), [recents.scope]: next.slice(0, RECENT_SEARCHES) }));
}

/**
 * The queries remembered for one scope, newest first. This browser always
 * keeps its own copy; when the server remembers them too, its list replaces
 * the local one, and a server that cannot answer leaves the local list as is.
 */
export function useRecentSearches(recents: WorkspaceSearch["recents"] | null): RecentSearches {
  const [items, setItems] = useState<RecentSearch[]>(() => local(recents));
  const server = recents?.server;
  const key = recents?.key;
  const scope = recents?.scope;
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    return () => { alive.current = false; };
  }, []);

  const pull = useCallback(async () => {
    if (!server) return;
    try {
      const rows = await server.list();
      if (alive.current) setItems(rows.slice(0, RECENT_SEARCHES).map(({ id, q }) => ({ id, q })));
    } catch {
      // The local list stays.
    }
  }, [server]);

  useEffect(() => {
    setItems(local(recents));
    void pull();
    // Another Business is another list.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, scope, pull]);

  const remember = useCallback((query: string) => {
    const text = query.trim();
    if (!recents || !text) return;
    const next = [text, ...scopedRecents(storedRecents(recents), recents.scope).filter((item) => !same(item, text))];
    writeLocal(recents, next);
    setItems((current) => [{ id: null, q: text }, ...current.filter((item) => !same(item.q, text))].slice(0, RECENT_SEARCHES));
    if (server) server.add(text).then(pull, () => undefined);
  }, [pull, recents, server]);

  const remove = useCallback((item: RecentSearch) => {
    if (!recents) return;
    writeLocal(recents, scopedRecents(storedRecents(recents), recents.scope).filter((text) => !same(text, item.q)));
    setItems((current) => current.filter((row) => row !== item));
    if (server && item.id) server.remove(item.id).then(pull, pull);
  }, [pull, recents, server]);

  const clear = useCallback(() => {
    if (!recents) return;
    writeLocal(recents, []);
    setItems([]);
    if (server) server.clear().then(pull, pull);
  }, [pull, recents, server]);

  return { items, remember, remove, clear };
}
