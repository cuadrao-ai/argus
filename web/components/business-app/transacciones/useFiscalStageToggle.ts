"use client";

import { useCallback, useRef } from "react";
import type { ReviewFilter } from "./records-filter-preview-model";

export function useFiscalStageToggle(selected: readonly ReviewFilter[], apply: (review: ReviewFilter[]) => void) {
  const previous = useRef<ReviewFilter[] | null>(null);
  const clear = useCallback(() => { previous.current = null; }, []);
  const toggle = () => {
    if (selected.length === 1 && selected[0] === "fiscal") {
      const restore = previous.current ?? [];
      clear();
      apply(restore);
    } else {
      previous.current = [...selected];
      apply(["fiscal"]);
    }
  };
  return { toggle, clear };
}
