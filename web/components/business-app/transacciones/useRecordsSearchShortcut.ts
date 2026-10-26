"use client";

import { useEffect, type RefObject } from "react";
import { hasOpenOverlay } from "@/components/layout/overlayStack";

export function useRecordsSearchShortcut(input: RefObject<HTMLInputElement | null>) {
  useEffect(() => {
    const focusSearch = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.repeat || event.isComposing || event.altKey || event.shiftKey || !(event.metaKey || event.ctrlKey) || event.key.toLowerCase() !== "k") return;
      if (hasOpenOverlay() || document.querySelector('[aria-modal="true"]')) return;
      const field = input.current;
      if (!field || field.disabled || field.closest('[inert], [aria-hidden="true"]')) return;
      event.preventDefault();
      field.focus();
      field.select();
    };
    // The surface consumes search before the shell's global shortcut.
    window.addEventListener("keydown", focusSearch, true);
    return () => window.removeEventListener("keydown", focusSearch, true);
  }, [input]);
}
