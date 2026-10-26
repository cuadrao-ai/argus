"use client";

import { useEffect, useRef } from "react";
import RangePicker, { useRangePickerDraft } from "./RangePicker";
import { reduceRangeDraft, validDraftRange, type DateRange, type RangeAction } from "./range-picker-state";

export type DayRange = DateRange;
type Phase = "start" | "end";

/** Kept for callers that use the original restart-on-earlier-day rule. */
export function pickDay(range: DayRange, phase: Phase, day: string): { range: DayRange; phase: Phase } {
  if (phase === "start" || day < range.from) return { range: { from: day, to: day }, phase: "end" };
  return { range: { from: range.from, to: day }, phase: "start" };
}

/** Embedded callers own confirmation; changes update their existing draft. */
export function RangeCalendar({ value, onChange, maxDays, label }: { value: DayRange; onChange: (range: DayRange) => void; maxDays: number; label: string }) {
  const session = useRangePickerDraft(value, onChange, maxDays);
  const emitted = useRef(value);
  const { dispatch, locale, state } = session;
  useEffect(() => {
    if (value.from === emitted.current.from && value.to === emitted.current.to) return;
    emitted.current = value;
    if (value.from && value.to) dispatch({ type: "reset", range: value });
  }, [dispatch, value]);
  const change = (action: RangeAction) => {
    dispatch(action);
    if (!["pick", "type", "preset", "drag-move", "drag-cancel"].includes(action.type)) return;
    const next = validDraftRange(reduceRangeDraft(state, action, locale), locale, maxDays) ?? { from: "", to: "" };
    emitted.current = next;
    onChange(next);
  };
  return <div data-testid="range-calendar" role="group" aria-label={label}><RangePicker session={{ ...session, dispatch: change }} embedded /></div>;
}
