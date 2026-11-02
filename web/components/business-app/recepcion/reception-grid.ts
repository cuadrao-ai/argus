import type { CSSProperties } from "react";
import type { ReceptionPreferences } from "./ReceptionControls";

export const SELECT_COLUMN_PX = 44;

type Widths = { content: number; file: number; channel: number; sender: number; status: number; arrival: number; action: number };
/** The approved widths, on a canvas that holds them. */
const ROOMY: Widths = { content: 200, file: 104, channel: 150, sender: 180, status: 240, arrival: 126, action: 136 };
/** A laptop with the rail open: the same columns, tighter. A 1280 screen leaves 976px. */
const LAPTOP: Widths = { content: 180, file: 76, channel: 124, sender: 124, status: 168, arrival: 106, action: 116 };
/** Below 940px Canal and Remitente share one column. */
const MERGED: Widths = { content: 180, file: 76, channel: 0, sender: 150, status: 160, arrival: 106, action: 116 };

/** The list's columns at each width, as the variables `reception.module.css` reads. */
export function receptionGrid(preferences: ReceptionPreferences, selectable: boolean, amountWidth: string, currencyWidth: number): CSSProperties {
  const money = { columns: [preferences.amount ? amountWidth : "", preferences.currency ? `${currencyWidth}px` : ""], px: preferences.currency ? currencyWidth : 0, amount: preferences.amount ? ` + ${amountWidth}` : "" };
  const lay = (widths: Widths, merged: boolean) => {
    const channel = !merged && preferences.source ? widths.channel : 0;
    const sender = preferences.sender || (merged && preferences.source) ? widths.sender : 0;
    const arrival = preferences.arrival ? widths.arrival : 0;
    const select = selectable ? SELECT_COLUMN_PX : 0;
    const tracks = [
      select ? `${select}px` : "",
      `minmax(${widths.content}px, 1.2fr)`,
      `${widths.file}px`,
      channel ? `${channel}px` : "",
      sender ? `minmax(${sender}px, ${widths === ROOMY ? "240px" : "0.6fr"})` : "",
      ...money.columns,
      `minmax(${widths.status}px, 0.8fr)`,
      arrival ? `${arrival}px` : "",
      `${widths.action}px`,
    ];
    return { tracks: tracks.filter(Boolean).join(" "), minimum: `calc(${select + widths.content + widths.file + channel + sender + widths.status + arrival + widths.action + money.px}px${money.amount})` };
  };
  const roomy = lay(ROOMY, false);
  const laptop = lay(LAPTOP, false);
  const merged = lay(MERGED, true);
  return { "--columns": roomy.tracks, "--table-min-width": roomy.minimum, "--laptop-columns": laptop.tracks, "--laptop-min-width": laptop.minimum, "--compact-columns": merged.tracks, "--compact-min-width": merged.minimum } as CSSProperties;
}
