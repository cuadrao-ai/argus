"use client";

import { useCallback, useRef } from "react";
import type { PreviewFilters } from "./records-filter-preview-model";

type ReadySelection = Pick<PreviewFilters, "ready">;

export function useFiscalStageToggle(selected: ReadySelection, apply: (selection: ReadySelection) => void) {
  const previous = useRef<ReadySelection | null>(null);
  const clear = useCallback(() => { previous.current = null; }, []);
  const toggle = () => {
    if (selected.ready === false) {
      const restore = previous.current ?? { ready: null };
      clear();
      apply(restore);
    } else {
      previous.current = { ready: selected.ready };
      apply({ ready: false });
    }
  };
  return { toggle, clear };
}
