"use client";

import { useEffect, useState } from "react";
import type { BusinessCapture } from "@/lib/business-api";
import { useBusiness } from "../BusinessWorkspace";
import { loadFailure, type LoadFailure } from "../bandeja-sources";

export function useDeletedNotes(active: boolean) {
  const { source, revision } = useBusiness();
  const [attempt, setAttempt] = useState(0);
  const [items, setItems] = useState<BusinessCapture[] | null>(null);
  const [failure, setFailure] = useState<LoadFailure | null>(null);
  useEffect(() => {
    if (!active) return;
    let live = true;
    const read = async () => {
      const notes: BusinessCapture[] = [];
      let offset = 0;
      let hasMore = true;
      while (live && hasMore) {
        const page = await source.captures("", 50, "eliminados", offset);
        notes.push(...page.items);
        offset += page.items.length;
        hasMore = page.has_more === true;
      }
      return notes;
    };
    void read().then(notes => {
      if (live) { setItems(notes); setFailure(null); }
    }, error => { if (live) setFailure(loadFailure(error)); });
    return () => { live = false; };
  }, [active, source, revision, attempt]);
  return { items, failure, retry: () => setAttempt(value => value + 1) };
}
