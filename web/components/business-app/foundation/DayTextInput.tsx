"use client";

import { useState } from "react";

export function dayText(iso: string): string {
  return iso ? iso.split("-").reverse().join("/") : "";
}

export function parseDayText(text: string): string | null {
  const parts = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(text);
  if (!parts) return null;
  const iso = `${parts[3]}-${parts[2]}-${parts[1]}`;
  const parsed = new Date(`${iso}T12:00:00Z`);
  return !Number.isNaN(parsed.getTime()) && parsed.toISOString().slice(0, 10) === iso ? iso : null;
}

export function DayTextInput({ value, onChange, className, disabled, required, ariaLabel, testId }: {
  value: string;
  onChange: (iso: string | null, invalid: boolean) => void;
  className: string;
  disabled?: boolean;
  required?: boolean;
  ariaLabel?: string;
  testId?: string;
}) {
  const [text, setText] = useState(() => dayText(value));
  return (
    <input
      type="text"
      inputMode="numeric"
      placeholder="dd/mm/aaaa"
      className={className}
      value={text}
      disabled={disabled}
      required={required}
      aria-label={ariaLabel}
      data-testid={testId}
      onChange={(event) => {
        const next = event.target.value;
        setText(next);
        const iso = parseDayText(next);
        onChange(iso, Boolean(next) && !iso);
      }}
    />
  );
}
