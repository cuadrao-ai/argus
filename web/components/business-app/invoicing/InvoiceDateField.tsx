"use client";

import { AlertCircle } from "lucide-react";
import { DatePicker } from "../foundation/DatePicker";
import { fieldLabelClass, fieldNoteClass, fieldNoteTone } from "@/components/ui/form-field";

export default function InvoiceDateField({ id, label, value, error, onChange, onBlur, due = false }: { due?: boolean; id: string; label: string; value: string; error: string | null; onChange: (value: string) => void; onBlur: () => void }) {
  return <div role="group" aria-labelledby={`${id}-label`} aria-describedby={error ? `${id}-error` : undefined} onBlur={onBlur}>
    <label id={`${id}-label`} htmlFor={id} className={fieldLabelClass}>{label}</label>
    <DatePicker shortcuts={due ? "due" : "past"} id={id} label={label} value={value} invalid={Boolean(error)} describedBy={error ? `${id}-error` : undefined} onChange={iso => onChange(iso ?? "")} />
    <p id={`${id}-error`} aria-live="polite" className={`${fieldNoteClass} ${fieldNoteTone.error}`}>{error ? <><AlertCircle size={16} aria-hidden="true" />{error}</> : null}</p>
  </div>;
}
