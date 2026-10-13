"use client";

import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import AdaptivePanel from "@/components/ui/AdaptivePanel";
import Switch from "@/components/ui/Switch";
import { inlineFailureTextClass } from "@/lib/failure-treatment";
import type { BusinessEmailAIReading, BusinessEmailIntake } from "@/lib/business-email";
import {
  canAgreeToReading,
  emailReadingProblem,
  getEmailIntake,
  readingModels,
  toggleEmailReading,
  type EmailReadingProblem,
} from "@/lib/business-email-consent-api";

/**
 * The owner's one switch for reading emailed receipts with AI. The disclosure
 * shown is the server's text, verbatim, with the provider and the model named
 * under it; the switch acts only on that exact text. Anyone with access reads
 * where it stands; only the owner can move it.
 */

export type EmailReadingViewProps = {
  intake: BusinessEmailIntake | null;
  loading: boolean;
  busy: boolean;
  problem: EmailReadingProblem | null;
  onToggle: () => void;
};

export function EmailReadingView({ intake, loading, busy, problem, onToggle }: EmailReadingViewProps) {
  const { t, i18n } = useTranslation();
  const reading = intake?.ai_reading ?? null;
  const address = intake?.enabled ? intake.receiving_address : null;
  return (
    <div className="space-y-5 p-5 text-sm text-black dark:text-white">
      <section className="rounded-2xl bg-black/5 p-4 dark:bg-white/5">
        <h3 className="font-medium">{t("settings.email_reading.address", "Receiving address")}</h3>
        {loading ? (
          <p role="status" className="mt-2">{t("settings.email_reading.loading", "Reading your permission…")}</p>
        ) : address ? (
          <p className="mt-2 select-all break-all font-mono" data-testid="email-reading-address">{address}</p>
        ) : (
          <p className="mt-2">{t("settings.email_reading.no_address", "This business has no address yet. Get one in the Inbox.")}</p>
        )}
      </section>
      {problem ? (
        <p role="alert" className={inlineFailureTextClass}>
          {t(`settings.email_reading.problem_${problem}`, "We could not save your answer. Try again.")}
        </p>
      ) : null}
      {reading ? (
        <section
          className="flex items-start justify-between gap-3 rounded-xl border border-black/[0.06] px-3.5 py-3 dark:border-white/[0.08]"
          data-testid="email-reading-consent"
        >
          <div className="min-w-0 space-y-1">
            <p className="text-[13px] font-medium text-black dark:text-white">
              {t("settings.email_reading.ai_title", "Read emailed receipts with AI")}
            </p>
            {reading.disclosure ? (
              <p className="whitespace-pre-wrap text-[11.5px] text-black/60 dark:text-white/60">{reading.disclosure}</p>
            ) : null}
            {reading.route ? (
              <p className="text-[11.5px] text-black/45 dark:text-white/45">
                {t("settings.email_reading.ai_models", "Provider: OpenRouter. Model: {{models}}.", { models: readingModels(reading).join(", ") })}
              </p>
            ) : null}
            <p className="text-[11.5px] text-black/45 dark:text-white/45" role="status" data-testid="email-reading-state">
              {reading.state === "on"
                ? t("settings.email_reading.ai_on", "Turned on {{date}} by {{name}}. You can turn it off at any time.", {
                    date: reading.consented_at ? new Date(reading.consented_at).toLocaleDateString(i18n.resolvedLanguage ?? "en", { dateStyle: "medium" }) : "",
                    name: reading.consented_by ?? "",
                  })
                : reading.state === "off"
                  ? t("settings.email_reading.ai_off", "Off. Receipts that arrive stay saved, unread.")
                  : t("settings.email_reading.ai_unseen", "Pending. Decide here or in the Inbox.")}
            </p>
            {!reading.owner ? (
              <p className="text-[11.5px] text-black/45 dark:text-white/45">{t("settings.email_reading.ai_owner_only", "Only the business owner can change this.")}</p>
            ) : !reading.available ? (
              <p className="text-[11.5px] text-black/45 dark:text-white/45">
                {t(`settings.email_reading.ai_reason_${reading.reason ?? "unavailable"}`, t("settings.email_reading.ai_reason_unavailable", "AI reading cannot be turned on right now."))}
              </p>
            ) : null}
            <p className="text-[11.5px] text-black/45 dark:text-white/45">{t("settings.email_reading.ai_approval", "You always approve money records yourself in Cuadrao.")}</p>
          </div>
          <Switch
            checked={reading.state === "on"}
            label={t("settings.email_reading.ai_title", "Read emailed receipts with AI")}
            disabled={busy || !reading.owner || (reading.state !== "on" && !canAgreeToReading(reading))}
            onChange={onToggle}
          />
        </section>
      ) : null}
    </div>
  );
}

export default function EmailReadingPanel({
  onClose,
  onBack,
  backLabel,
}: {
  onClose: () => void;
  onBack?: () => void;
  backLabel?: string;
}) {
  const { t, i18n } = useTranslation();
  const [intake, setIntake] = useState<BusinessEmailIntake | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<EmailReadingProblem | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setIntake(await getEmailIntake(i18n.language));
      setProblem(null);
    } catch (error) {
      setProblem(emailReadingProblem(error));
    } finally {
      setLoading(false);
    }
  }, [i18n.language]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function toggle() {
    const reading: BusinessEmailAIReading | null = intake?.ai_reading ?? null;
    if (!reading || !intake) return;
    setBusy(true);
    try {
      const next = await toggleEmailReading(reading, undefined, i18n.language);
      setIntake({ ...intake, ai_reading: next });
      setProblem(null);
    } catch (error) {
      const next = emailReadingProblem(error);
      setProblem(next);
      if (next === "stale") setIntake(await getEmailIntake(i18n.language).catch(() => intake));
    } finally {
      setBusy(false);
    }
  }

  return (
    <AdaptivePanel
      title={t("settings.email_reading.title", "Receipt email")}
      closeLabel={t("common.close", "Close")}
      onClose={onClose}
      onBack={onBack}
      backLabel={backLabel}
      width="md"
    >
      <EmailReadingView intake={intake} loading={loading} busy={busy} problem={problem} onToggle={() => void toggle()} />
    </AdaptivePanel>
  );
}
