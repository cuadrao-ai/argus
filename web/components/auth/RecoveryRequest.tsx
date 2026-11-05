"use client";

import { type FormEvent, useEffect, useRef, useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { ArrowLeft, LoaderCircle } from "lucide-react";
import { useTranslation } from "react-i18next";
import { FormField, useFieldChecks } from "@/components/ui/FormField";
import { RecoveryRequestError, requestPasswordRecovery } from "@/lib/auth-security";
import { prefilledEmail } from "@/lib/auth-link-error";
import { classifyFailure, EMAIL_RETRY_FALLBACK_SECONDS, runQuietRetries } from "@/lib/failure-screen";
import { inlineFailureTextClass } from "@/lib/failure-treatment";
import { useRetryAfterCountdown } from "@/lib/use-retry-after-countdown";
import { RecoveryShell } from "./RecoveryShell";
import { takeRecoveryEmail } from "./recovery-email";
import styles from "./recovery.module.css";

type RequestState = "idle" | "sending" | "sent" | "error" | "limited";

export function RecoveryRequest({ request = requestPasswordRecovery }: { request?: typeof requestPasswordRecovery }) {
  const { t } = useTranslation();
  const [email, setEmail] = useState("");
  const [screen, setScreen] = useState<"email" | "inbox">("email");
  const [state, setState] = useState<RequestState>("idle");
  const [waitUntil, setWaitUntil] = useState<number>();
  const pending = useRef(false);
  const field = useRef<HTMLInputElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const remaining = useRetryAfterCountdown(waitUntil);
  const required = t("auth.form.email_required");
  const invalid = t("auth.form.email_invalid");
  const checks = useFieldChecks({ email: values => !values.email.trim() ? required : field.current?.validity.typeMismatch ? invalid : null }, { email });

  useEffect(() => {
    const next = takeRecoveryEmail() || prefilledEmail(new URLSearchParams(window.location.search).get("email"));
    if (next) setEmail(next);
  }, []);
  useEffect(() => { if (screen === "inbox") heading.current?.focus({ preventScroll: true }); }, [screen]);

  async function submit(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault();
    if (pending.current || remaining > 0) return;
    if (screen === "email" && !checks.submit()) { field.current?.focus(); return; }
    pending.current = true;
    setState("sending");
    try {
      await runQuietRetries(() => request(email.trim()));
      setScreen("inbox");
      setState("sent");
      setWaitUntil(Date.now() + EMAIL_RETRY_FALLBACK_SECONDS * 1000);
    } catch (error) {
      if (classifyFailure(error) === "rate_limited") {
        const seconds = error instanceof RecoveryRequestError ? error.retryAfterSeconds : EMAIL_RETRY_FALLBACK_SECONDS;
        setWaitUntil(Date.now() + seconds * 1000);
        setState("limited");
      } else setState("error");
    } finally { pending.current = false; }
  }

  return <RecoveryShell>
    <Link href="/?auth=login" className={styles.secondary}><ArrowLeft aria-hidden="true" size={16} />{t("auth.recovery.back_to_sign_in")}</Link>
    {screen === "inbox" && <Image unoptimized src="/images/auth/confirmation-envelope.png" alt="" width={168} height={112} className={styles.art} />}
    <h1 ref={heading} tabIndex={-1} className={`font-display ${styles.title} ${screen === "inbox" ? styles.center : ""}`}>
      {t(screen === "inbox" ? "auth.recovery.inbox_title" : "auth.recovery.title")}
    </h1>
    <p role="status" className="sr-only">{state === "sent" ? t("auth.recovery.generic_sent") : ""}</p>
    {screen === "email" ? <>
      <p className={styles.description}>{t("auth.recovery.description")}</p>
      <form noValidate onSubmit={submit} aria-busy={state === "sending"} className={styles.form}>
        <FormField ref={field} id="recovery-email" type="email" label={t("auth.recovery.email_label")}
          placeholder={t("auth.form.email_hint")} autoComplete="email" autoCapitalize="none" spellCheck={false}
          required readOnly={state === "sending"} value={email}
          onChange={event => { setEmail(event.target.value); if (state === "error") setState("idle"); }}
          onBlur={() => checks.blur("email")} error={checks.errorOf("email")}
          reserveMessages={[required, invalid]} />
        <button type="submit" disabled={state === "sending" || remaining > 0} aria-busy={state === "sending"} className={`${styles.primary} auth-primary`}>
          {state === "sending" && <LoaderCircle aria-hidden="true" className="h-4 w-4 animate-spin motion-reduce:animate-none" />}
          {t(state === "sending" ? "auth.recovery.sending" : "auth.recovery.send")}
        </button>
        <div className={styles.feedback}>
          {state === "error" && <p role="alert" className={inlineFailureTextClass}>{t("auth.recovery.request_error")}</p>}
          {remaining > 0 && <>
            <p role="status" className="sr-only">{t("auth.recovery.rate_help")}</p>
            <p aria-live="off">{t("auth.recovery.resend_wait", { seconds: remaining })}</p>
          </>}
        </div>
      </form>
    </> : <div className={styles.center}>
      <p className={styles.description}>{t("auth.recovery.generic_sent")}</p>
      <p className={styles.email}>{email.trim()}</p>
      <p className={styles.help}>{t("auth.recovery.spam_help")}</p>
      <div className={styles.feedback}>
        {state === "error" && <p role="alert" className={inlineFailureTextClass}>{t("auth.recovery.request_error")}</p>}
        {state === "limited" && <p role="status">{t("auth.recovery.rate_help")}</p>}
      </div>
      <button type="button" disabled={state === "sending" || remaining > 0} aria-busy={state === "sending"}
        aria-live="off" onClick={() => void submit()} className={`${styles.primary} auth-primary`}>
        {state === "sending" ? t("auth.recovery.sending") : remaining > 0 ? t("auth.recovery.resend_wait", { seconds: remaining }) : t("auth.recovery.resend")}
      </button>
      <button type="button" disabled={state === "sending"} className={`${styles.secondary} mt-3`}
        onClick={() => { setScreen("email"); setState("idle"); checks.reset(); requestAnimationFrame(() => field.current?.focus()); }}>
        {t("auth.recovery.change_email")}
      </button>
    </div>}
  </RecoveryShell>;
}
