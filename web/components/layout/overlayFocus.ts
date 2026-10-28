/**
 * Which elements a trapped layer may move focus between.
 *
 * Shared so the registry and the focus hook cannot disagree about what counts
 * as focusable, which is the kind of drift that lets Tab fall out of a dialog
 * through an element only one of them could see.
 */

/*
 * `tabindex="-1"` is excluded everywhere, not only on the catch-all.
 *
 * A trap moves focus itself rather than letting the browser do it, so opting an
 * element out of the native tab order means nothing unless the trap agrees.
 * That is why marking the backdrops non-tabbable did not stop Shift+Tab landing
 * on one: they are buttons, and `button:not([disabled])` still matched.
 */
const NOT_OPTED_OUT = ':not([tabindex="-1"])';

export const FOCUSABLE_SELECTOR = [
  `a[href]${NOT_OPTED_OUT}`,
  `button:not([disabled])${NOT_OPTED_OUT}`,
  `input:not([disabled]):not([type='hidden'])${NOT_OPTED_OUT}`,
  `select:not([disabled])${NOT_OPTED_OUT}`,
  `textarea:not([disabled])${NOT_OPTED_OUT}`,
  `summary${NOT_OPTED_OUT}`,
  "[contenteditable]:not([contenteditable='false']):not([tabindex='-1'])",
  "[tabindex]:not([tabindex='-1'])",
].join(",");

export function focusableWithin(container: HTMLElement | null): HTMLElement[] {
  if (!container) return [];
  return Array.from(
    container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
  ).filter((element) => element.offsetParent !== null);
}

/** Wraps at both ends so focus never escapes an open modal. */
export function nextFocusIndex({
  count,
  currentIndex,
  direction,
}: {
  count: number;
  currentIndex: number;
  direction: "focus-next" | "focus-previous";
}): number {
  if (count <= 0) return -1;
  if (direction === "focus-next") {
    return currentIndex >= count - 1 || currentIndex < 0 ? 0 : currentIndex + 1;
  }
  return currentIndex <= 0 ? count - 1 : currentIndex - 1;
}
