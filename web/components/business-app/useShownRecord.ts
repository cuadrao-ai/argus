"use client";

import { useCallback, useEffect, useRef } from "react";

/**
 * Whether the record a request was made for is still the one on screen when
 * its answer lands. An answer for a record the person has left must not move
 * them or speak for it.
 */
export function useShownRecord(id: string): (asked: string) => boolean {
  const shown = useRef<string | null>(id);
  useEffect(() => {
    shown.current = id;
    return () => { shown.current = null; };
  }, [id]);
  return useCallback((asked: string) => shown.current === asked, []);
}
