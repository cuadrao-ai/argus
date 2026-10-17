"use client";

import { useEffect, useId, useRef, useState, useSyncExternalStore, type FormEvent, type ReactNode } from "react";
import { ArrowRight, Check } from "lucide-react";
import { businessPath } from "@/lib/site-routes";
import { businessContent, type BusinessLocale } from "./content";
import { newSubmissionId } from "./submission-id";
import { checkPhone, cleanPhoneInput } from "./phone";
import {
  EMPTY_PROFILE,
  NOTE_MAX,
  PHONE_MAX,
  SOURCE_MAX,
  buildInquiryMessage,
  type InquiryChannel,
  type InquiryProfile,
  type InquiryRole,
} from "./inquiry-summary";
import styles from "./business.module.css";

type Field = "name" | "email" | "description";
type FormValues = Record<Field, string>;
type SendState =
  | { status: "idle" }
  | { status: "sending" }
  | { status: "sent"; values: FormValues }
  | { status: "error"; kind: "unavailable" | "rateLimited" | "rejected" };

const EMPTY_VALUES: FormValues = { name: "", email: "", description: "" };
const subscribeToHydration = (): (() => void) => () => {};
const clientSnapshot = (): boolean => true;
const serverSnapshot = (): boolean => false;
const REQUIRED_FIELDS = ["name", "email"] as const;
const REQUEST_TIMEOUT_MS = 15_000;

export function ContactForm({ locale }: { locale: BusinessLocale }) {
  const copy = businessContent[locale].contact;
  const hydrated = useSyncExternalStore(
    subscribeToHydration,
    clientSnapshot,
    serverSnapshot,
  );
  const [values, setValues] = useState<FormValues>(EMPTY_VALUES);
  const [profile, setProfile] = useState<InquiryProfile>(EMPTY_PROFILE);
  const [phoneError, setPhoneError] = useState(false);
  const [errors, setErrors] = useState<Partial<Record<Field, string>>>({});
  const [state, setState] = useState<SendState>({ status: "idle" });
  const form = useRef<HTMLFormElement>(null);
  const confirmation = useRef<HTMLHeadingElement>(null);
  const pending = useRef(false);
  // A retry of the same text reuses its id so the server can recognise it. Any
  // edit is a different message and gets a new id.
  const attempt = useRef<{ id: string; signature: string } | null>(null);

  useEffect(() => {
    if (state.status === "sent") confirmation.current?.focus();
  }, [state.status]);

  async function submit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (pending.current) return;
    const nextErrors: Partial<Record<Field, string>> = {};
    for (const field of REQUIRED_FIELDS) {
      if (!values[field].trim()) nextErrors[field] = copy.required;
    }
    const emailInput = form.current?.elements.namedItem(
      "email",
    ) as HTMLInputElement | null;
    if (values.email.trim() && emailInput?.validity.typeMismatch)
      nextErrors.email = copy.invalidEmail;
    setErrors(nextErrors);
    const first = REQUIRED_FIELDS.find((field) => nextErrors[field]);
    if (first) {
      (
        form.current?.elements.namedItem(first) as HTMLInputElement | null
      )?.focus();
      return;
    }

    const phone = profile.channel === "whatsapp" ? checkPhone(profile.phone) : { status: "empty" as const };
    if (phone.status === "invalid") {
      setPhoneError(true);
      (form.current?.elements.namedItem("phone") as HTMLInputElement | null)?.focus();
      return;
    }
    const message = buildInquiryMessage(
      { ...profile, phone: phone.status === "valid" ? phone.display : "" },
      values.description,
    );
    const signature = JSON.stringify({ ...values, message });
    if (attempt.current?.signature !== signature) {
      attempt.current = { id: newSubmissionId(), signature };
    }
    const website =
      (form.current?.elements.namedItem("website") as HTMLInputElement | null)
        ?.value ?? "";
    pending.current = true;
    setState({ status: "sending" });
    try {
      const response = await fetch("/api/inquiries", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...values,
          description: message,
          locale,
          submissionId: attempt.current.id,
          website,
        }),
        signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
      });
      if (response.status === 202) {
        attempt.current = null;
        setState({ status: "sent", values });
      } else {
        setState({
          status: "error",
          kind:
            response.status === 429
              ? "rateLimited"
              : response.status === 400
                ? "rejected"
                : "unavailable",
        });
      }
    } catch {
      setState({ status: "error", kind: "unavailable" });
    } finally {
      pending.current = false;
    }
  }

  const sending = state.status === "sending";
  const failure = state.status === "error" ? copy[state.kind] : null;

  return (
    <div className={styles.formArea}>
      {state.status === "sent" ? (
        <section className={styles.review} aria-labelledby="contact-sent-title">
          <span className={styles.sentMark}>
            <Check size={22} aria-hidden="true" />
          </span>
          <h2 id="contact-sent-title" ref={confirmation} tabIndex={-1}>
            {copy.successTitle}
          </h2>
          <p>{copy.successBody}</p>
          <p className={styles.nextStep}>{copy.nextStep}</p>
          <dl>
            {([...REQUIRED_FIELDS, "description"] as const).map((field) => (
              <div key={field}>
                <dt>{copy[field]}</dt>
                <dd>{state.values[field].trim() || copy.empty}</dd>
              </div>
            ))}
          </dl>
        </section>
      ) : (
        <form
          ref={form}
          onSubmit={submit}
          noValidate
          aria-busy={sending}
          aria-describedby="contact-privacy"
          className={styles.demoForm}
        >
          <noscript>
            <p className={styles.localNotice}>{copy.noScript}</p>
          </noscript>
          <fieldset className={styles.formFields} disabled={!hydrated}>
            <div className={styles.fieldRow}>
            {REQUIRED_FIELDS.map((field) => (
              <div className={styles.field} key={field}>
                <label htmlFor={`contact-${field}`}>{copy[field]}</label>
                <input
                  id={`contact-${field}`}
                  name={field}
                  type={field === "email" ? "email" : "text"}
                  autoComplete={field}
                  maxLength={field === "email" ? 254 : 120}
                  required
                  placeholder={copy[`${field}Placeholder`]}
                  value={values[field]}
                  aria-invalid={!!errors[field]}
                  aria-describedby={
                    errors[field] ? `contact-${field}-error` : undefined
                  }
                  readOnly={sending}
                  onChange={(event) => {
                    setValues({ ...values, [field]: event.target.value });
                    if (errors[field])
                      setErrors({ ...errors, [field]: undefined });
                  }}
                />
                {errors[field] && (
                  <p id={`contact-${field}-error`} className={styles.fieldError}>
                    {errors[field]}
                  </p>
                )}
              </div>
            ))}
            </div>
            <ChoiceGroup label={copy.roleLabel} optional={copy.optional}>
              {(Object.keys(copy.roleOptions) as InquiryRole[]).map((role) => (
                <Choice
                  key={role}
                  type="radio"
                  name="role"
                  checked={profile.role === role}
                  disabled={sending}
                  onChange={() => setProfile({ ...profile, role })}
                >
                  {copy.roleOptions[role]}
                </Choice>
              ))}
            </ChoiceGroup>
            <div className={styles.field}>
              <label htmlFor="contact-description">
                {copy.description} <span>{copy.optional}</span>
              </label>
              <p id="contact-description-hint" className={styles.fieldHint}>
                {copy.descriptionHint}
              </p>
              <textarea
                id="contact-description"
                name="description"
                aria-describedby="contact-description-hint"
                rows={4}
                maxLength={NOTE_MAX}
                placeholder={copy.descriptionPlaceholder}
                value={values.description}
                readOnly={sending}
                onChange={(event) =>
                  setValues({ ...values, description: event.target.value })
                }
              />
              {NOTE_MAX - values.description.length <= 100 && (
                <p className={styles.fieldHint}>
                  {copy.charsLeft(NOTE_MAX - values.description.length)}
                </p>
              )}
            </div>
            <ChoiceGroup label={copy.channelLabel} optional={copy.optional}>
              {(Object.keys(copy.channelOptions) as InquiryChannel[]).map((channel) => (
                <Choice
                  key={channel}
                  type="radio"
                  name="channel"
                  checked={profile.channel === channel}
                  disabled={sending}
                  onChange={() => {
                    setProfile({ ...profile, channel });
                    if (channel !== "whatsapp") setPhoneError(false);
                  }}
                >
                  {copy.channelOptions[channel]}
                </Choice>
              ))}
              {profile.channel === "whatsapp" && (
                <input
                  id="contact-phone"
                  name="phone"
                  type="tel"
                  autoComplete="tel"
                  inputMode="tel"
                  maxLength={PHONE_MAX}
                  aria-label={copy.phone}
                  placeholder={copy.phonePlaceholder}
                  value={profile.phone}
                  aria-invalid={phoneError}
                  aria-describedby={phoneError ? "contact-phone-error" : undefined}
                  readOnly={sending}
                  onChange={(event) => {
                    setProfile({ ...profile, phone: cleanPhoneInput(event.target.value) });
                    if (phoneError) setPhoneError(false);
                  }}
                  onBlur={() => {
                    const result = checkPhone(profile.phone);
                    if (result.status === "valid") {
                      setProfile({ ...profile, phone: result.display });
                    } else {
                      setPhoneError(result.status === "invalid");
                    }
                  }}
                />
              )}
            </ChoiceGroup>
            {phoneError && (
              <p id="contact-phone-error" className={styles.phoneError} role="alert">
                {copy.invalidPhone}
              </p>
            )}
            <div className={styles.field}>
              <label htmlFor="contact-source">
                {copy.sourceLabel} <span>{copy.optional}</span>
              </label>
              <p id="contact-source-hint" className={styles.fieldHint}>
                {copy.sourceHint}
              </p>
              <input
                id="contact-source"
                name="source"
                type="text"
                maxLength={SOURCE_MAX}
                aria-describedby="contact-source-hint"
                placeholder={copy.sourcePlaceholder}
                value={profile.source}
                readOnly={sending}
                onChange={(event) =>
                  setProfile({ ...profile, source: event.target.value })
                }
              />
            </div>
            <label className={styles.pilotRow}>
              <input
                type="checkbox"
                name="pilot"
                checked={profile.pilot}
                disabled={sending}
                onChange={(event) =>
                  setProfile({ ...profile, pilot: event.target.checked })
                }
              />
              <span>{copy.pilot}</span>
            </label>
            <div className={styles.srOnly} aria-hidden="true">
              <label htmlFor="contact-website">Website</label>
              <input
                id="contact-website"
                name="website"
                type="text"
                tabIndex={-1}
                autoComplete="off"
                defaultValue=""
              />
            </div>
            {Object.keys(errors).some((field) => errors[field as Field]) && (
              <p className={styles.srOnly} role="alert">
                {copy.errors}
              </p>
            )}
            {failure && (
              <p id="contact-failure" className={styles.formFailure} role="alert">
                {failure}
              </p>
            )}
            <button
              type="submit"
              disabled={!hydrated}
              aria-disabled={sending}
              className={styles.button}
            >
              {sending ? copy.sending : copy.submit}
              <ArrowRight size={18} aria-hidden="true" />
            </button>
            <p className={styles.nextStep}>{copy.nextStep}</p>
          </fieldset>
        </form>
      )}
      <p id="contact-privacy" className={styles.formPrivacy}>
        {copy.privacy}{" "}
        <a href={businessPath(locale, "privacy")}>{copy.privacyLink}</a>
      </p>
    </div>
  );
}

function ChoiceGroup({
  label,
  optional,
  children,
}: {
  label: string;
  optional: string;
  children: ReactNode;
}) {
  const id = useId();
  return (
    <div className={styles.choiceGroup} role="group" aria-labelledby={id}>
      <span id={id} className={styles.choiceLabel}>
        {label} <span>{optional}</span>
      </span>
      <div className={styles.choices}>{children}</div>
    </div>
  );
}

function Choice({
  type,
  name,
  checked,
  disabled,
  onChange,
  children,
}: {
  type: "radio" | "checkbox";
  name: string;
  checked: boolean;
  disabled: boolean;
  onChange: (checked: boolean) => void;
  children: ReactNode;
}) {
  return (
    <label className={styles.choice}>
      <input
        type={type}
        name={name}
        checked={checked}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
      />
      <span>{children}</span>
    </label>
  );
}
