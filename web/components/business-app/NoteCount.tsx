/** The longest note a person writes, typed in Agregar or on a record; the server's `NOTE_MAX_LENGTH`. */
export const NOTE_LIMIT = 500;

/** Characters as the server counts them: code points, so an emoji is one. */
export const noteLength = (text: string) => Array.from(text).length;

/** Text cut to the limit, never through the middle of a character. */
export const withinNoteLimit = (text: string) => (noteLength(text) > NOTE_LIMIT ? Array.from(text).slice(0, NOTE_LIMIT).join("") : text);

/** The "n/500" line under a note field; its field names it with `aria-describedby`. */
export default function NoteCount({ id, count }: { id: string; count: number }) {
  return <div id={id} className="mt-1 text-right text-[13px] tabular-nums text-[#56635e] dark:text-white/55">{count}/{NOTE_LIMIT}</div>;
}
