"use client";

import { useEffect, useState } from "react";
import type { BusinessCapture } from "@/lib/business-api";
import { useBusiness } from "../BusinessWorkspace";
import { loadFailure, type LoadFailure } from "../bandeja-sources";

export function useDeletedNotes(active: boolean) {
  const { source, revision } = useBusiness();
  const [attempt, setAttempt] = useState(0);
  const [items, setItems] = useState<BusinessCapture[] | null>(null);
  const [truncated, setTruncated] = useState(false);
  const [failure, setFailure] = useState<LoadFailure | null>(null);
  useEffect(() => {
    if (!active) return;
    let live = true;
    void source.captures("", 50, "eliminados").then(page => {
      if (live) { setItems(page.items); setTruncated(page.has_more === true); setFailure(null); }
    }, error => { if (live) setFailure(loadFailure(error)); });
    return () => { live = false; };
  }, [active, source, revision, attempt]);
  return { items, failure, truncated, retry: () => setAttempt(value => value + 1) };
}
