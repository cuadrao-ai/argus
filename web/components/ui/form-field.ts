/**
 * One look for a labelled field: the account pages, the Comentarios sheet and the
 * Business forms built on `FormField.tsx`. Input text stays at 16px, the border is
 * the locked input grey, and the focus ring follows the field's own rounded-item corner.
 *
 * Autofill keeps the field's own surface in light and dark: the browser's tint is
 * held back by a transition that never finishes, and the text colour is set again
 * because the browser paints autofilled text with its own fill colour.
 */
export const fieldLabelClass = "block text-[15px] font-medium text-[#172b26] dark:text-white";

export const fieldClass =
  "mt-2 min-h-11 w-full rounded-item border border-[#7d8a84] bg-[var(--field-surface,white)] px-3 py-2.5 text-[16px] text-[#172b26] transition-colors placeholder:text-[#56635e]/70 hover:border-[#2f5a49] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--cuadrao-green)] aria-[invalid=true]:border-[#9e2f39]! disabled:cursor-not-allowed disabled:bg-[#eceeea] disabled:text-[#56635e] dark:disabled:bg-[#263b35] dark:disabled:text-white/70 autofill:[transition:background-color_600000s_0s,color_600000s_0s] autofill:[-webkit-text-fill-color:#172b26] autofill:caret-[#172b26] dark:border-white/25 dark:bg-transparent dark:text-white dark:placeholder:text-white/40 dark:hover:border-white/45 dark:aria-[invalid=true]:border-[#ec9aa0]! dark:autofill:[-webkit-text-fill-color:#ffffff] dark:autofill:caret-white";

const hintTone = "text-[#56635e] dark:text-white/65";
const errorTone = "text-[#9e2f39]! dark:text-[#ec9aa0]!";

export const fieldHintClass = `text-[14px] leading-relaxed ${hintTone}`;

/** An error under its field or its form, in the locked attention red. */
export const fieldErrorClass = `text-[14px] leading-snug ${errorTone}`;

/**
 * The line under a field, reserved before anything is written in it, so a hint
 * turning into an error has room. Pass reserveMessages for feedback that can wrap.
 */
export const fieldNoteClass = "mt-1.5 flex min-h-[22px] items-start gap-1.5 text-[14px] leading-[22px]";
export const fieldNoteTone = { hint: hintTone, error: errorTone, success: "text-[#2f5a49]! dark:text-[#8fcbb0]!" } as const;
