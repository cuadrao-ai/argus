import { useLayoutEffect, type RefObject } from "react";

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

const NOTE_BOX_MIN_LINES = 6;

/**
 * A note box's height: at least six lines, then as tall as its text (`content`, the scroll height plus borders), up
 * to the lines a full note fills at this width (plus one for a short last word). Only text past that scrolls.
 */
export function noteBoxHeight({ content, lineHeight, chrome, textWidth, charWidth }: { content: number; lineHeight: number; chrome: number; textWidth: number; charWidth: number }): { height: number; overflow: boolean } {
  const perLine = Math.max(1, Math.floor(textWidth / Math.max(1, charWidth)));
  const capLines = Math.max(NOTE_BOX_MIN_LINES, Math.ceil(NOTE_LIMIT / perLine) + 1);
  const min = NOTE_BOX_MIN_LINES * lineHeight + chrome;
  const max = capLines * lineHeight + chrome;
  return { height: Math.min(Math.max(content, min), max), overflow: content > max };
}

/** The average width of a character in this field's font, from a sample sentence; half the font size without a canvas. */
function averageCharWidth(style: CSSStyleDeclaration): number {
  const size = parseFloat(style.fontSize) || 16;
  try {
    const context = document.createElement("canvas").getContext("2d");
    if (!context) return size / 2;
    context.font = `${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
    const sample = "Pagué RD$1,500 de cemento en la ferretería, en efectivo, ayer.";
    return context.measureText(sample).width / sample.length || size / 2;
  } catch {
    return size / 2;
  }
}

/** Sizes a note textarea to its text by `noteBoxHeight`, at once and with no animation, and again when the width changes. */
export function useGrowingNoteBox(ref: RefObject<HTMLTextAreaElement | null>, value: string) {
  useLayoutEffect(() => {
    const field = ref.current;
    if (!field) return undefined;
    const fit = () => {
      const style = getComputedStyle(field);
      const px = (name: string) => parseFloat(style.getPropertyValue(name)) || 0;
      const size = px("font-size") || 16;
      const lineHeight = px("line-height") || size * 1.625;
      const borders = px("border-top-width") + px("border-bottom-width");
      const chrome = px("padding-top") + px("padding-bottom") + borders;
      field.style.height = "auto";
      const { height, overflow } = noteBoxHeight({ content: field.scrollHeight + borders, lineHeight, chrome, textWidth: field.clientWidth - px("padding-left") - px("padding-right"), charWidth: averageCharWidth(style) });
      field.style.height = `${height}px`;
      field.style.overflowY = overflow ? "auto" : "hidden";
    };
    fit();
    window.addEventListener("resize", fit);
    return () => window.removeEventListener("resize", fit);
  }, [ref, value]);
}
