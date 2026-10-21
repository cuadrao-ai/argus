/**
 * One look for a labelled field outside the Business workspace's own forms:
 * the account pages and the Comentarios sheet. Input text stays at 16px, the
 * border is the locked input grey, and the focus ring follows the field's own
 * rounded-item corner.
 */
export const fieldLabelClass = "block text-[15px] font-medium text-[#172b26] dark:text-white";

export const fieldClass =
  "mt-2 min-h-11 w-full rounded-item border border-[#7d8a84] bg-white px-3 py-2.5 text-[16px] text-[#172b26] transition-colors placeholder:text-[#56635e]/70 hover:border-[#2f5a49] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--cuadrao-green)] aria-[invalid=true]:border-[#9e2f39] dark:border-white/25 dark:bg-transparent dark:text-white dark:placeholder:text-white/40 dark:hover:border-white/45 dark:aria-[invalid=true]:border-[#ec9aa0]";

export const fieldHintClass = "text-[14px] leading-relaxed text-[#56635e] dark:text-white/65";

/** An error under its field or its form, in the locked attention red. */
export const fieldErrorClass = "text-[14px] leading-snug text-[#9e2f39] dark:text-[#ec9aa0]";
