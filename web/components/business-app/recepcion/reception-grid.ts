import type { CSSProperties } from "react";
import { shownReceptionColumns, type ReceptionColumnKey, type ReceptionPreferences } from "./reception-columns";

export const SELECT_COLUMN_PX = 44;
const CURRENCY_COLUMN_PX = 80;
/** The widest Contenido gets in every tab, Eliminados included. Past it, the spare width goes to the actions. */
const CONTENT_CAP_PX = 360;

type Widths = { content: number; file: number; channel: number; sender: number; status: number; arrival: number; action: number };
/** The approved widths, on a canvas that holds them. */
const ROOMY: Widths = { content: 200, file: 104, channel: 150, sender: 200, status: 240, arrival: 126, action: 140 };
/** A laptop with the rail open: the same columns, tighter. A 1280 screen leaves 976px. */
const LAPTOP: Widths = { content: 180, file: 76, channel: 136, sender: 140, status: 168, arrival: 106, action: 140 };
/** Below 940px Canal and Enviado por share one column, where the first of the two stands. */
const SHARED: readonly ReceptionColumnKey[] = ["source", "sender"];
const MERGED: Widths = { content: 180, file: 76, channel: 0, sender: 150, status: 160, arrival: 106, action: 140 };

/**
 * The list's columns at each width, as the variables `reception.module.css` reads. The tracks follow the person's
 * order between the fixed places: the box column and Contenido first and the action track last, by position.
 * Contenido grows to its cap and Estado to its roomy width; every other data track is fixed. The action track takes
 * what is left.
 */
export function receptionGrid(preferences: ReceptionPreferences, { select: selectable }: { select: boolean }, amountWidth: string): CSSProperties {
  const shown = shownReceptionColumns(preferences);
  const select = selectable ? SELECT_COLUMN_PX : 0;
  const lay = (widths: Widths, merged: boolean) => {
    const track: Record<ReceptionColumnKey, [track: string, px: number]> = {
      file: [`${widths.file}px`, widths.file],
      source: merged ? [`${widths.sender}px`, widths.sender] : [`${widths.channel}px`, widths.channel],
      sender: [`${widths.sender}px`, widths.sender],
      amount: [amountWidth, 0],
      currency: [`${CURRENCY_COLUMN_PX}px`, CURRENCY_COLUMN_PX],
      status: [`minmax(${widths.status}px, ${ROOMY.status}px)`, widths.status],
      arrival: [`${widths.arrival}px`, widths.arrival],
    };
    const columns = (merged ? shown.filter(key => !SHARED.includes(key) || key === shown.find(other => SHARED.includes(other))) : shown).map(key => track[key]);
    const px = columns.reduce((sum, [, width]) => sum + width, select + widths.content + widths.action);
    return { tracks: [select ? `${select}px` : "", `minmax(${widths.content}px, ${CONTENT_CAP_PX}px)`, ...columns.map(([value]) => value), `minmax(${widths.action}px, 1fr)`].filter(Boolean).join(" "), minimum: `calc(${px}px${shown.includes("amount") ? ` + ${amountWidth}` : ""})` };
  };
  const roomy = lay(ROOMY, false);
  const laptop = lay(LAPTOP, false);
  const merged = lay(MERGED, true);
  return { "--content-cap": `${CONTENT_CAP_PX}px`, "--columns": roomy.tracks, "--table-min-width": roomy.minimum, "--laptop-columns": laptop.tracks, "--laptop-min-width": laptop.minimum, "--compact-columns": merged.tracks, "--compact-min-width": merged.minimum } as CSSProperties;
}

/** The column whose place in the row holds Canal, Enviado por and the phone's arrival: the first of them shown. */
export const originPlace = (shown: readonly ReceptionColumnKey[]) => shown.find(key => SHARED.includes(key)) ?? shown.find(key => key === "arrival");

/**
 * Where each shown column stands, from 1, as the `--col` its cell carries. The box and Contenido carry none, so they
 * stay first. Canal and Enviado por share the first of their two places below 940px.
 */
export function receptionPlaces(preferences: ReceptionPreferences) {
  const shown = shownReceptionColumns(preferences);
  const place = (key: ReceptionColumnKey) => shown.indexOf(key) + 1;
  const col = (index: number) => ({ "--col": index }) as CSSProperties;
  return { shown, has: (key: ReceptionColumnKey) => shown.includes(key), at: (key: ReceptionColumnKey) => col(place(key)), shared: col(Math.min(...SHARED.map(place).filter(Boolean), shown.length)), last: col(shown.length + 1) };
}
