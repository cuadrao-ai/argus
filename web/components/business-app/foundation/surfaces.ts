/** A Business card: white, a 1px hairline, radius 20, padding 24, never a shadow. */
export const SURFACE_CARD = "rounded-[20px] border border-[#DCE0DA] bg-[#FFFEFA] p-6 dark:border-white/10 dark:bg-[#1f2225]";

const PILL_BUTTON = "inline-flex min-h-11 items-center justify-center gap-2 rounded-full px-4 text-[15px] font-medium leading-5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f5a49] disabled:opacity-40";

/** The one primary action of a view: green fill. */
export const PRIMARY_BUTTON = `${PILL_BUTTON} bg-[#2f5a49] text-[#FFFEFA] hover:bg-[#1d4236] disabled:hover:bg-[#2f5a49]`;

/** White with the input outline and ink text. */
export const SECONDARY_BUTTON = `${PILL_BUTTON} border border-[#7d8a84] bg-[#FFFEFA] text-[#172b26] dark:bg-[#1f2225] dark:text-white`;
