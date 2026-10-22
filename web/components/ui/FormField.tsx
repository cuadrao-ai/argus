"use client";

import {
  type InputHTMLAttributes,
  type MouseEvent,
  type ReactNode,
  type Ref,
  type SelectHTMLAttributes,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import { AlertCircle, Check, Circle, Eye, EyeOff } from "lucide-react";
import { useTranslation } from "react-i18next";
import { PASSWORD_MIN_LENGTH, PASSWORD_RULES, readPassword, type PasswordStrength } from "@/lib/password-strength";
import { fieldClass, fieldLabelClass, fieldNoteClass, fieldNoteTone } from "./form-field";

/** One rule per field: the message that says how to fix the value, or null when it is fine. */
export type FieldRules<Name extends string> = Record<Name, (values: Record<Name, string>) => string | null>;

/**
 * When a field's error shows. A field stays quiet while the person types; leaving it
 * with something written checks it, and a failed submit checks every field. Once a
 * field has shown an error it is checked on every keystroke, so the error clears the
 * moment the value is fixed. Errors are derived from the values, never stored.
 */
export function useFieldChecks<Name extends string>(rules: FieldRules<Name>, values: Record<Name, string>) {
  const names = Object.keys(rules) as Name[];
  const [live, setLive] = useState<ReadonlySet<Name>>(() => new Set());
  const [attempt, setAttempt] = useState(0);
  const [checked, setChecked] = useState<Partial<Record<Name, string>>>({});
  const reset = useCallback(() => {
    setLive(new Set());
    setChecked({});
    setAttempt(0);
  }, [setLive, setChecked, setAttempt]);
  const errorOf = (name: Name) => (live.has(name) ? rules[name](values) : null);
  const broken = names.filter((name) => errorOf(name) !== null);
  return {
    errorOf,
    isValid: (name: Name) => values[name] !== "" && rules[name](values) === null
      && (live.has(name) || checked[name] === values[name]),
    blur(name: Name) {
      if (values[name] === "") return;
      setChecked((was) => ({ ...was, [name]: values[name] }));
      if (rules[name](values) !== null) setLive((was) => new Set(was).add(name));
    },
    /** Checks every field. False when one is broken; the caller chooses where to move focus. */
    submit(): boolean {
      const failing = names.filter((name) => rules[name](values) !== null);
      if (failing.length === 0) return true;
      setLive((was) => new Set([...was, ...failing]));
      setAttempt((count) => count + 1);
      return false;
    },
    reset,
    /** The fields the summary lists after a failed submit; empty once every field is fixed. */
    summary: attempt > 0 ? broken : [],
    attempt,
  };
}

type FrameProps = {
  id: string;
  label: ReactNode;
  hint?: ReactNode;
  error?: string | null;
  success?: string;
  /** Candidate messages reserve their wrapped height without entering the accessibility tree. */
  reserveMessages?: readonly string[];
};

/** The label above, the control, and one reserved line under it that holds the hint or the error. */
function FieldFrame({ id, label, hint, error, success, reserveMessages, children, coach }: FrameProps & { children: ReactNode; coach?: ReactNode }) {
  return (
    <div>
      <label htmlFor={id} className={fieldLabelClass}>
        {label}
      </label>
      {children}
      {coach}
      {reserveMessages?.length === 0 && !hint && !error && !success ? null : <div className="grid">
        {reserveMessages?.map((message) => (
          <p key={message} aria-hidden="true" className={`${fieldNoteClass} invisible col-start-1 row-start-1`}>
            <span className="h-4 w-4 shrink-0" />{message}
          </p>
        ))}
        <p id={noteId(id)} aria-live="polite" className={`${fieldNoteClass} col-start-1 row-start-1 ${error ? fieldNoteTone.error : success ? fieldNoteTone.success : fieldNoteTone.hint}`}>
          {error ? <AlertCircle className="mt-[3px] h-4 w-4 shrink-0" aria-hidden="true" /> : null}
          {error || success || hint}
        </p>
      </div>}
    </div>
  );
}

const noteId = (id: string) => `${id}-note`;

function controlProps(id: string, hint: ReactNode, error: string | null | undefined) {
  return {
    id,
    "aria-invalid": error ? true : undefined,
    "aria-describedby": error || hint ? noteId(id) : undefined,
  } as const;
}

type InputProps = Omit<InputHTMLAttributes<HTMLInputElement>, "id" | "type" | "className"> & {
  ref?: Ref<HTMLInputElement>;
  /** Never "number": a code or a postal code is not a quantity, so it stays text with inputMode="numeric". */
  type?: "text" | "email" | "tel" | "url" | "search";
};

/** A text field. Codes and numbers that are not quantities pass inputMode="numeric" and stay text. */
export function FormField({ id, label, hint, error, success, reserveMessages, ...input }: FrameProps & InputProps) {
  return (
    <FieldFrame id={id} label={label} hint={hint} error={error} success={success} reserveMessages={reserveMessages}>
      <div className="relative">
        <input type="text" {...input} {...controlProps(id, success || hint, error)} className={`${fieldClass}${success && !error ? " pr-11" : ""}`} />
        {success && !error ? <Check aria-hidden="true" className="pointer-events-none absolute bottom-3 right-3 h-5 w-5 text-[#2f5a49] dark:text-[#8fcbb0]" /> : null}
      </div>
    </FieldFrame>
  );
}

export function SelectField({
  id,
  label,
  hint,
  error,
  success,
  reserveMessages,
  children,
  ...select
}: FrameProps & Omit<SelectHTMLAttributes<HTMLSelectElement>, "id" | "className">) {
  return (
    <FieldFrame id={id} label={label} hint={hint} error={error} success={success} reserveMessages={reserveMessages}>
      <select {...select} {...controlProps(id, success || hint, error)} className={fieldClass}>
        {children}
      </select>
    </FieldFrame>
  );
}

type PasswordProps = Omit<InputHTMLAttributes<HTMLInputElement>, "id" | "type" | "className" | "autoComplete" | "value"> & {
  /** A new password gets the strength meter, the live checklist and the rules a password manager reads. */
  autoComplete: "current-password" | "new-password";
  value: string;
  advice?: string;
  coaching?: "always" | "on-focus";
  hideIcon?: ReactNode;
};

/** The one show and hide control for a password, sitting inside the field's right edge. */
export function PasswordVisibilityToggle({ controls, shown, onToggle, hideIcon }: { controls: string; shown: boolean; onToggle: () => void; hideIcon?: ReactNode }) {
  const { t } = useTranslation();
  return (
    <button
      type="button"
      aria-controls={controls}
      aria-label={shown ? t("auth.password.hide", "Hide password") : t("auth.password.show", "Show password")}
      onClick={onToggle}
      className="absolute bottom-0 right-0 inline-flex h-11 w-11 items-center justify-center rounded-full text-[#56635e] transition-colors hover:text-[#172b26] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-[-4px] focus-visible:outline-[var(--cuadrao-green)] dark:text-white/65 dark:hover:text-white"
    >
      {shown ? hideIcon ?? <EyeOff className="h-5 w-5" aria-hidden="true" /> : <Eye className="h-5 w-5" aria-hidden="true" />}
    </button>
  );
}

/**
 * A password field. Paste always works. A new password coaches while it is typed:
 * a meter in plain words and a checklist that ticks live. Coaching is never an
 * error; errors still wait for the person to leave the field or submit.
 */
export function PasswordField({ id, label, hint, error, success, reserveMessages, advice, coaching = "always", hideIcon, ...input }: FrameProps & PasswordProps) {
  const [shown, setShown] = useState(false);
  const passwordInput = useRef<HTMLInputElement>(null);
  const [engaged, setEngaged] = useState(false);
  const fresh = input.autoComplete === "new-password";
  const coachId = `${id}-coach`;
  const showCoach = fresh && (coaching === "always" || engaged || input.value !== "" || Boolean(error));
  const described = [showCoach ? coachId : null, error || success || hint ? noteId(id) : null].filter(Boolean).join(" ") || undefined;
  return (
    <FieldFrame id={id} label={label} hint={hint} error={error} success={success} reserveMessages={reserveMessages} coach={showCoach ? <PasswordCoach id={coachId} value={input.value} advice={advice} progressive={coaching === "on-focus"} /> : null}>
      <div className="relative">
        <input
          ref={passwordInput}
          type={shown ? "text" : "password"}
          spellCheck={false}
          autoCapitalize="none"
          {...(fresh ? { passwordrules: PASSWORD_RULES } : {})}
          {...input}
          onFocus={(event) => { setEngaged(true); input.onFocus?.(event); }}
          {...controlProps(id, hint, error)}
          aria-describedby={described}
          className={`${fieldClass} pr-12`}
        />
        <PasswordVisibilityToggle controls={id} shown={shown} hideIcon={hideIcon} onToggle={() => {
          passwordInput.current?.focus({ preventScroll: true });
          setShown((was) => !was);
        }} />
      </div>
    </FieldFrame>
  );
}

const METER: Record<PasswordStrength, { fill: string; width: string }> = {
  empty: { fill: "", width: "w-0" },
  weak: { fill: "bg-[#9e2f39] dark:bg-[#ec9aa0]", width: "w-1/4" },
  almost: { fill: "bg-[#b0861a] dark:bg-[#e6cf8a]", width: "w-2/3" },
  strong: { fill: "bg-[var(--cuadrao-green)] dark:bg-[#8fcbb0]", width: "w-full" },
};

function PasswordCoach({ id, value, advice, progressive }: { id: string; value: string; advice?: string; progressive: boolean }) {
  const { t } = useTranslation();
  const reading = readPassword(value);
  const words: Record<PasswordStrength, string> = {
    empty: "",
    weak: t("auth.password.strength_weak", "Weak"),
    almost: t("auth.password.strength_almost", "Almost there"),
    strong: t("auth.password.strength_strong", "Strong"),
  };
  const checklist = [
    { key: "length", met: reading.longEnough, text: t("auth.password.min_length", { min: PASSWORD_MIN_LENGTH, defaultValue: "At least {{min}} characters" }) },
    { key: "pattern", met: value !== "" && !reading.predictable, text: advice ?? t("auth.password.no_patterns", "No common words, runs or repeats") },
  ];
  return (
    <div id={id} data-testid="password-coach" data-strength={reading.strength} className="mt-2">
      <div data-testid="password-strength-reading" aria-hidden={progressive && value === "" ? true : undefined}
        className={`flex min-h-[22px] items-center gap-3 ${progressive && value === "" ? "invisible" : ""}`}>
        <div aria-hidden="true" className="h-1.5 flex-1 overflow-hidden rounded-full bg-[#DCE0DA] dark:bg-white/10">
          <div className={`h-full rounded-full transition-[width,background-color] duration-200 ease-out motion-reduce:transition-none ${METER[reading.strength].fill} ${METER[reading.strength].width}`} />
        </div>
        <p aria-live="polite" className="min-w-[6.5rem] shrink-0 text-right text-[14px] font-medium leading-[22px] text-[#56635e] dark:text-white/65">
          {reading.strength === "empty" ? "" : `${t("auth.password.strength", "Strength")}: ${words[reading.strength]}`}
        </p>
      </div>
      <ul className="mt-1">
        {checklist.map((item) => (
          <li key={item.key} data-met={item.met} className={`flex min-h-[22px] items-center gap-1.5 text-[14px] leading-[22px] ${item.met ? "text-[#2f5a49] dark:text-[#8fcbb0]" : "text-[#56635e] dark:text-white/65"}`}>
            {item.met ? <Check className="h-4 w-4 shrink-0" aria-hidden="true" /> : <Circle className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />}
            <span>
              {item.text}
              <span className="sr-only">{item.met ? ` (${t("auth.password.met", "done")})` : ""}</span>
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * After a failed submit: one box at the top of the form that links to every broken
 * field. It takes focus when it opens, and a link moves focus into its field.
 */
export function ErrorSummary({
  title,
  items,
}: {
  title: string;
  items: { id: string; label: string }[];
}) {
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    box.current?.focus();
  }, []);
  if (items.length === 0) return null;
  const go = (event: MouseEvent<HTMLAnchorElement>, id: string) => {
    event.preventDefault();
    const field = document.getElementById(id);
    field?.focus();
    field?.scrollIntoView({ block: "center" });
  };
  return (
    <div
      ref={box}
      tabIndex={-1}
      role="alert"
      data-testid="form-error-summary"
      className="rounded-item border border-[#9e2f39]/30 bg-[#f6dfe0]/60 px-4 py-3 text-[#9e2f39] outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--cuadrao-green)] dark:border-[#ec9aa0]/30 dark:bg-[#ec9aa0]/10 dark:text-[#ec9aa0]"
    >
      <p className="flex items-start gap-2 text-[15px] font-medium">
        <AlertCircle className="mt-[3px] h-4 w-4 shrink-0" aria-hidden="true" />
        {title}
      </p>
      <ul className="ml-6">
        {items.map((item) => (
          <li key={item.id}>
            <a
              href={`#${item.id}`}
              onClick={(event) => go(event, item.id)}
              className="inline-flex min-h-11 items-center rounded-mark text-[15px] underline underline-offset-4 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--cuadrao-green)]"
            >
              {item.label}
            </a>
          </li>
        ))}
      </ul>
    </div>
  );
}
