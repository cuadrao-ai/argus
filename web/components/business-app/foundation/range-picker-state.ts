import { isoOf, monthOf, shiftDay } from "./DatePicker";

export type DateRange = { from: string; to: string };
export type RangePreset = "today" | "yesterday" | "last_7" | "last_30" | "last_quarter" | "custom";
export type RangeEdge = keyof DateRange;
export type RangeDraft = {
  range: DateRange;
  text: DateRange;
  phase: "start" | "end";
  cursor: string;
  hover: string | null;
  preset: RangePreset;
  drag: { edge: RangeEdge; anchor: string; before: DateRange; moved: boolean } | null;
};
export type RangeAction =
  | { type: "reset"; range: DateRange }
  | { type: "pick"; day: string }
  | { type: "hover"; day: string | null }
  | { type: "type"; edge: RangeEdge; text: string }
  | { type: "cursor"; day: string }
  | { type: "preset"; preset: RangePreset; today: string }
  | { type: "drag-start"; edge: RangeEdge }
  | { type: "drag-move"; day: string }
  | { type: "drag-end" }
  | { type: "drag-cancel" };

export const orderedRange = (a: string, b: string): DateRange => a <= b ? { from: a, to: b } : { from: b, to: a };
export const dateInputFormat = (locale: string) => locale.startsWith("en") ? "MM/DD/YYYY" : "DD/MM/AAAA";
export function formatRangeInput(day: string, locale: string): string {
  const [year, month, date] = day.split("-");
  return locale.startsWith("en") ? `${month}/${date}/${year}` : `${date}/${month}/${year}`;
}
export function parseRangeInput(text: string, locale: string): string | null {
  const match = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(text.trim());
  if (!match) return null;
  const [, first, second, year] = match;
  const [month, day] = locale.startsWith("en") ? [first, second] : [second, first];
  const iso = `${year}-${month}-${day}`;
  const parsed = new Date(`${iso}T12:00:00Z`);
  return Number(year) >= 1900 && !Number.isNaN(parsed.getTime()) && parsed.toISOString().slice(0, 10) === iso ? iso : null;
}
const rangeText = (range: DateRange, locale: string): DateRange => ({ from: formatRangeInput(range.from, locale), to: formatRangeInput(range.to, locale) });
export const createRangeDraft = (range: DateRange, locale: string): RangeDraft => ({ range, text: rangeText(range, locale), phase: "start", cursor: range.from, hover: null, preset: "custom", drag: null });
export function validDraftRange(state: RangeDraft, locale: string, maxDays = 366): DateRange | null {
  const from = parseRangeInput(state.text.from, locale);
  const to = parseRangeInput(state.text.to, locale);
  return from && to && from <= to && to <= shiftDay(from, maxDays - 1) ? { from, to } : null;
}
export function presetRange(preset: Exclude<RangePreset, "custom">, today: string): DateRange {
  if (preset === "today") return { from: today, to: today };
  if (preset === "yesterday") return { from: shiftDay(today, -1), to: shiftDay(today, -1) };
  if (preset === "last_7" || preset === "last_30") return { from: shiftDay(today, preset === "last_7" ? -6 : -29), to: today };
  const month = monthOf(today);
  const quarterStart = Math.floor(month.month / 3) * 3;
  return { from: isoOf(month.year, quarterStart - 3, 1), to: isoOf(month.year, quarterStart, 0) };
}
export function shiftMonth(day: string, delta: number): string {
  const current = monthOf(day);
  const last = isoOf(current.year, current.month + delta + 1, 0);
  return isoOf(current.year, current.month + delta, Math.min(Number(day.slice(8)), Number(last.slice(8))));
}
export function previewRange(state: RangeDraft): DateRange {
  return state.phase === "end" && state.hover && !state.drag ? orderedRange(state.range.from, state.hover) : state.range;
}
export function reduceRangeDraft(state: RangeDraft, action: RangeAction, locale: string): RangeDraft {
  const replace = (range: DateRange, extra: Partial<RangeDraft> = {}): RangeDraft => ({ ...state, range, text: rangeText(range, locale), preset: "custom", hover: null, ...extra });
  switch (action.type) {
    case "reset": return createRangeDraft(action.range, locale);
    case "pick": return state.phase === "start"
      ? replace({ from: action.day, to: action.day }, { phase: "end", cursor: action.day })
      : replace(orderedRange(state.range.from, action.day), { phase: "start", cursor: action.day });
    case "hover": return { ...state, hover: action.day };
    case "cursor": return { ...state, cursor: action.day, hover: state.phase === "end" ? action.day : null };
    case "type": {
      const parsed = parseRangeInput(action.text, locale);
      return { ...state, text: { ...state.text, [action.edge]: action.text }, range: parsed ? { ...state.range, [action.edge]: parsed } : state.range, cursor: parsed ?? state.cursor, phase: "start", hover: null, preset: "custom" };
    }
    case "preset": return action.preset === "custom" ? { ...state, preset: "custom" } : replace(presetRange(action.preset, action.today), { phase: "start", preset: action.preset, cursor: presetRange(action.preset, action.today).from });
    case "drag-start": return { ...state, drag: { edge: action.edge, anchor: state.range[action.edge === "from" ? "to" : "from"], before: state.range, moved: false }, hover: null };
    case "drag-move": return state.drag ? replace(orderedRange(state.drag.anchor, action.day), { phase: "start", cursor: action.day, drag: { ...state.drag, moved: state.drag.moved || action.day !== state.drag.before[state.drag.edge] } }) : state;
    case "drag-end": return { ...state, drag: null };
    case "drag-cancel": return state.drag ? replace(state.drag.before, { drag: null }) : state;
  }
}
