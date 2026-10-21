"use client";

import { type FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { useTranslation } from "react-i18next";

import { RecoveryEmailWait } from "@/components/status/RecoveryEmailWait";
import { ServerErrorScreen } from "@/components/status/ServerErrorScreen";
import { RecoveryRequestError, requestPasswordRecovery } from "@/lib/auth-security";
import { prefilledEmail } from "@/lib/auth-link-error";
import { classifyFailure, EMAIL_RETRY_FALLBACK_SECONDS, referenceCode, runQuietRetries } from "@/lib/failure-screen";
import { inlineFailureTextClass } from "@/lib/failure-treatment";
import { useRetryAfterCountdown } from "@/lib/use-retry-after-countdown";

export default function ForgotPasswordPage() {
  const { t } = useTranslation();
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState<"idle" | "submitting" | "sent" | "error" | "limited" | "server">(
    "idle",
  );
  const [waitUntil, setWaitUntil] = useState<number | undefined>(undefined);
  const [reference, setReference] = useState("");
  const remaining = useRetryAfterCountdown(waitUntil);

  useEffect(() => {
    const next = prefilledEmail(new URLSearchParams(window.location.search).get("email"));
    if (next) setEmail(next);
  }, []);

  const submit = async (event?: FormEvent<HTMLFormElement>) => {
    event?.preventDefault();
    if (remaining > 0) return;
    setStatus("submitting");
    try {
      await runQuietRetries(() => requestPasswordRecovery(email));
      setStatus("sent");
    } catch (error) {
      const kind = classifyFailure(error);
      if (kind === "rate_limited") {
        const seconds = error instanceof RecoveryRequestError
          ? error.retryAfterSeconds
          : EMAIL_RETRY_FALLBACK_SECONDS;
        setWaitUntil(Date.now() + seconds * 1000);
        setStatus("limited");
        return;
      }
      if (kind === "unavailable" || kind === "server") {
        setReference(referenceCode(error));
        setStatus("server");
        return;
      }
      setStatus("error");
    }
  };

  if (status === "server") {
    return <ServerErrorScreen reference={reference} onRetry={() => void submit()} />;
  }

  return (
    <main data-auth-brand="cuadrao" className="flex min-h-[100dvh] items-center justify-center bg-[var(--auth-paper)] px-6 py-12">
      <section className="w-full max-w-md rounded-[20px] border border-[var(--auth-line)] bg-[var(--auth-paper)] p-7">
        <Link
          href="/?auth=login"
          className="inline-flex min-h-11 items-center text-sm font-medium text-[var(--auth-muted)] hover:text-[var(--auth-pine)]"
        >
          {t("auth.recovery.back_to_sign_in", "Back to sign in")}
        </Link>
        <h1 className="mt-6 font-display text-3xl font-medium tracking-tight text-[var(--auth-ink)]">
          {t("auth.recovery.title", "Recover your account")}
        </h1>
        <p className="mt-2 text-sm leading-relaxed text-[var(--auth-muted)]">
          {t(
            "auth.recovery.description",
            "Enter your email and we’ll send recovery instructions if the account is eligible.",
          )}
        </p>

        {status === "sent" ? (
          <div
            role="status"
            className="mt-6 rounded-[18px] border border-[var(--auth-line)] bg-[var(--auth-sage)] p-4 text-sm leading-relaxed text-[var(--auth-ink)]"
          >
            {t(
              "auth.recovery.generic_sent",
              "If an eligible account exists for that email, recovery instructions will arrive shortly.",
            )}
          </div>
        ) : (
          <form onSubmit={submit} className="mt-6 space-y-3">
            <label className="block text-sm font-medium text-[var(--auth-ink)]">
              {t("auth.recovery.email_label", "Email address")}
              <input
                type="email"
                required
                autoComplete="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                className="mt-2 w-full rounded-[20px] border bg-transparent px-5 py-[14px] text-[16px] text-[var(--auth-ink)] outline-none"
              />
            </label>
            {status === "limited" && waitUntil ? <RecoveryEmailWait availableAtMs={waitUntil} /> : null}
            {status === "error" && (
              <p role="alert" className={`text-sm ${inlineFailureTextClass}`}>
                {t(
                  "auth.recovery.request_error",
                  "We couldn’t start recovery. Wait a moment and try again.",
                )}
              </p>
            )}
            <button
              type="submit"
              disabled={status === "submitting" || remaining > 0}
              className="w-full rounded-full auth-primary bg-[var(--auth-pine)] text-[var(--auth-on-pine)] hover:bg-[var(--auth-pine-hover)] min-h-11 px-5 py-3 font-display font-medium disabled:opacity-50"
            >
              {status === "submitting"
                ? t("auth.recovery.sending", "Sending...")
                : t("auth.recovery.send", "Send recovery instructions")}
            </button>
          </form>
        )}
      </section>
    </main>
  );
}
