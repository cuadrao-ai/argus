/**
 * One canvas for every workspace screen, at most 75rem (1200px) wide and
 * left-aligned at the main area's 2rem gutter from the tablet stop up. 75rem
 * is a whole step of the 8px grid (8 × 150) that holds the 1100px ledger with
 * its padding. The top bar spans the same box, so search starts at the
 * canvas's left edge and the actions end at its right edge on every screen.
 * Below the tablet stop the phone layout's 1rem gutters stay.
 */
export const WORKSPACE_CANVAS_CLASS = "w-full tablet:max-w-[75rem]";
/** The bar's own padding: the left gutter, and on the right whatever the canvas leaves (2rem gutter + 75rem canvas = 77rem). */
export const WORKSPACE_BAR_PADDING_CLASS = "tablet:pl-8 tablet:pr-[max(2rem,calc(100%-77rem))]";
