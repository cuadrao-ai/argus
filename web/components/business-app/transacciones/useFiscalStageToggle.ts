"use client";

import { useCallback, useRef } from "react";
import type { PreviewFilters } from "./records-filter-preview-model";

type FiscalSelection = Pick<PreviewFilters, "fiscal_data" | "review">;

export function useFiscalStageToggle(selected: FiscalSelection, apply: (selection: FiscalSelection) => void) {
  const previous = useRef<FiscalSelection | null>(null);
  const clear = useCallback(() => { previous.current = null; }, []);
  const toggle = () => {
    if (selected.fiscal_data === "missing" && selected.review.length === 0) {
      const restore = previous.current ?? { fiscal_data: null, review: [] };
      clear();
      apply(restore);
    } else {
      previous.current = { fiscal_data: selected.fiscal_data, review: [...selected.review] };
      apply({ fiscal_data: "missing", review: [] });
    }
  };
  return { toggle, clear };
}
