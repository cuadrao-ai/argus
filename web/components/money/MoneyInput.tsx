"use client";

import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  currencyChange,
  currencySymbol,
  displayForValue,
  editMoney,
  fallbackEdit,
  formatMoney,
  localeUsesCommaDecimal,
  moneyPlaceholder,
  moneyProblemFromServer,
  nextRenderedHistory,
  readMoney,
  textForParentValue,
  type MoneyEditInput,
  type MoneyProblem,
  type MoneyRules,
} from "@/lib/money-entry";

export type MoneyInputChange = { value: string | null; invalid: boolean };

type MoneyInputProps = {
  /** The field's name without the currency; the accessible label adds it. */
  label: string;
  /** ISO code; empty while the user has not chosen one. */
  currency: string;
  /** Canonical dot-decimal value, or null for empty. */
  value: string | null;
  onValueChange: (change: MoneyInputChange) => void;
  allowNegative?: boolean;
  disabled?: boolean;
  /** A backend recording error code such as amount_precision. */
  serverError?: string | null;
  /** Read after the label, such as "Needed"; the visible label cannot reach the input. */
  description?: string | null;
  testId?: string;
};

const INSERTS = new Set(["insertText", "insertReplacementText", "insertFromPaste", "insertFromDrop", "insertFromYank"]);
const DELETES: Record<string, "backward" | "forward"> = {
  deleteContentBackward: "backward",
  deleteContentForward: "forward",
  deleteByCut: "backward",
  deleteByDrag: "backward",
  deleteContent: "backward",
};

export default function MoneyInput({
  label,
  currency,
  value,
  onValueChange,
  allowNegative = false,
  disabled = false,
  serverError = null,
  description = null,
  testId,
}: MoneyInputProps) {
  const { t } = useTranslation();
  const id = useId();
  const messageId = `${id}-message`;
  const descriptionId = `${id}-description`;
  const inputRef = useRef<HTMLInputElement>(null);
  const pendingCaret = useRef<number | null>(null);
  const rulesFor = (code: string): MoneyRules => ({
    currency: code,
    allowNegative,
    commaDecimal: typeof navigator !== "undefined" && localeUsesCommaDecimal(navigator.language),
  });
  const rules = rulesFor(currency);
  const [text, setText] = useState(() => displayForValue(value, rules));
  const [problem, setProblem] = useState<MoneyProblem | null>(null);
  const [currencyNote, setCurrencyNote] = useState(false);
  const [seenValue, setSeenValue] = useState(value);
  const [parentReplacements, setParentReplacements] = useState(0);
  if (value !== seenValue) {
    setSeenValue(value);
    const replaced = textForParentValue(text, value, rules);
    if (replaced !== null) {
      setParentReplacements((count) => count + 1);
      setText(replaced);
      setProblem(null);
      setCurrencyNote(false);
    }
  }

  // Texts this field has rendered, so an undo or redo that restores one is
  // recognized as the field's own grouping.
  const rendered = useRef<string[]>([]);
  const seenReplacements = useRef(0);
  useLayoutEffect(() => {
    const parentReplaced = seenReplacements.current !== parentReplacements;
    seenReplacements.current = parentReplacements;
    rendered.current = nextRenderedHistory(rendered.current, text, parentReplaced);
  }, [text, parentReplacements]);

  const commit = (next: string, caret: number | null, nextProblem: MoneyProblem | null) => {
    pendingCaret.current = caret;
    setText(next);
    setProblem(nextProblem);
    setCurrencyNote(false);
    const reading = readMoney(next, rules);
    onValueChange({ value: reading.value, invalid: reading.problem !== null });
  };

  // The native beforeinput listener is attached once and reads the current render through this ref.
  const latest = useRef({ text, rules, onValueChange, commit });
  useLayoutEffect(() => {
    latest.current = { text, rules, onValueChange, commit };
  });

  const seenCurrency = useRef(currency);
  useEffect(() => {
    if (seenCurrency.current === currency) return;
    const previous = seenCurrency.current;
    seenCurrency.current = currency;
    const change = currencyChange(latest.current.text, previous, latest.current.rules);
    setProblem(change.problem);
    setCurrencyNote(change.note);
    latest.current.onValueChange({ value: change.value, invalid: change.invalid });
  }, [currency]);

  useLayoutEffect(() => {
    const input = inputRef.current;
    if (pendingCaret.current === null || !input || document.activeElement !== input) return;
    input.setSelectionRange(pendingCaret.current, pendingCaret.current);
    pendingCaret.current = null;
  });

  useEffect(() => {
    const input = inputRef.current;
    if (!input) return;
    const onBeforeInput = (event: InputEvent) => {
      if (event.isComposing) return;
      let edit: MoneyEditInput;
      if (INSERTS.has(event.inputType)) {
        edit = { type: "insert", text: event.data ?? event.dataTransfer?.getData("text/plain") ?? "" };
      } else if (DELETES[event.inputType]) {
        edit = { type: "delete", direction: DELETES[event.inputType] };
      } else {
        return;
      }
      event.preventDefault();
      const { text: current, rules: currentRules, commit: apply } = latest.current;
      const start = input.selectionStart ?? current.length;
      const end = input.selectionEnd ?? start;
      const result = editMoney(current, start, end, edit, currentRules);
      if (result.kind === "accept") apply(result.display, result.caret, result.problem);
      else if (result.kind === "reject") setProblem(result.problem);
    };
    input.addEventListener("beforeinput", onBeforeInput);
    return () => input.removeEventListener("beforeinput", onBeforeInput);
  }, []);

  const onChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const raw = event.target.value;
    const result = fallbackEdit(raw, event.target.selectionStart ?? raw.length, rules, rendered.current);
    if (result.kind === "accept") commit(result.display, result.caret, null);
    else if (result.kind === "reject") setProblem(result.problem);
  };

  const onBlur = () => {
    const reading = readMoney(text, rules);
    if (reading.problem) {
      setProblem(reading.problem);
      return;
    }
    const formatted = formatMoney(text, rules);
    if (formatted !== text) commit(formatted, null, null);
  };

  const shown = problem ?? moneyProblemFromServer(serverError, currency);
  const symbol = currencySymbol(currency);
  const accessibleLabel = currency
    ? t("money.label", "{{label}} in {{currency}}", { label, currency: symbol === currency ? currency : `${currency} (${symbol})` })
    : label;

  return (
    <div>
      <div
        className={`mt-1.5 flex min-h-11 w-full items-center gap-2 rounded-[12px] border bg-white px-3 transition-colors focus-within:ring-[0.125rem] dark:bg-[#141517] ${
          shown
            ? "border-[#9e2f39]/60 focus-within:ring-[#9e2f39]/15 dark:border-[#ec9aa0]/60"
            : "border-[#7d8a84] focus-within:ring-black/10"
        } ${disabled ? "bg-black/[0.03] dark:bg-white/[0.03]" : ""}`}
      >
        {symbol ? (
          <span aria-hidden="true" className="shrink-0 text-[16px] tabular-nums text-[#56635e] dark:text-white/60">
            {symbol}
          </span>
        ) : null}
        <input
          ref={inputRef}
          type="text"
          inputMode="decimal"
          autoComplete="off"
          spellCheck={false}
          className="min-w-0 flex-1 bg-transparent py-2 text-[16px] tabular-nums text-black outline-none placeholder:text-black/30 disabled:text-black/50 dark:text-white dark:placeholder:text-white/30"
          value={text}
          placeholder={moneyPlaceholder(currency)}
          onChange={onChange}
          onBlur={onBlur}
          disabled={disabled}
          aria-label={accessibleLabel}
          aria-invalid={shown ? true : undefined}
          aria-describedby={description ? `${descriptionId} ${messageId}` : messageId}
          data-testid={testId}
        />
      </div>
      {description ? (
        <span id={descriptionId} className="sr-only">
          {description}
        </span>
      ) : null}
      <p
        id={messageId}
        aria-live="polite"
        className={
          shown
            ? "mt-1 text-[13px] text-[#9e2f39] dark:text-[#ec9aa0]"
            : currencyNote
              ? "mt-1 text-[13px] text-black/55 dark:text-white/55"
              : ""
        }
      >
        {shown
          ? moneyMessage(shown, t)
          : currencyNote
            ? t("money.same_amount", "Same amount, no conversion.")
            : ""}
      </p>
    </div>
  );
}

type Translate = ReturnType<typeof useTranslation>["t"];

function moneyMessage(problem: MoneyProblem, t: Translate): string {
  switch (problem.code) {
    case "invalid":
      return t("money.invalid", "Use digits and one decimal point.");
    case "decimal_twice":
      return t("money.decimal_twice", "An amount has only one decimal point.");
    case "negative":
      return t("money.negative", "Enter a positive amount.");
    case "grouping":
      return t("money.grouping", "Check the thousands commas, as in 1,250.50.");
    case "decimal_comma":
      return t("money.decimal_comma", "Use a point for decimals, as in 1,250.50.");
    case "precision":
      return problem.digits === 0
        ? t("money.precision_none", "{{currency}} has no decimals.", { currency: problem.currency })
        : t("money.precision", "{{currency}} allows up to {{count}} decimals.", { currency: problem.currency, count: problem.digits });
    case "too_long":
      return t("money.too_long", "Use at most {{count}} digits before the decimal point.", { count: problem.digits });
    case "out_of_range":
      return t("money.out_of_range", "This amount is too large to record.");
    case "ambiguous_currency":
      return t("money.ambiguous_currency", "$ could mean RD$ or US$. Enter the amount without a symbol, or with RD$ or US$.");
    case "currency_mismatch":
      return t("money.currency_mismatch", "This amount is in {{field}}, not {{typed}}.", {
        field: problem.field,
        typed: problem.typed,
      });
    case "zero":
      return t("money.zero", "Enter an amount greater than 0.");
  }
}
