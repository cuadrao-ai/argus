"use client";

import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import AdaptivePanel from "@/components/ui/AdaptivePanel";
import CopyCodeButton from "@/components/settings/CopyCodeButton";
import { inlineFailureTextClass } from "@/lib/failure-treatment";
import {
  createWhatsAppLinkCode,
  getWhatsAppLink,
  unlinkWhatsApp,
  whatsAppLinkProblem,
  type WhatsAppAIConsent,
  type WhatsAppLinkCode,
  type WhatsAppLinkProblem,
  type WhatsAppLinkStatus,
} from "@/lib/whatsapp-link-api";

const button =
  "min-h-11 rounded-xl border border-black/10 px-4 py-2 text-sm disabled:cursor-not-allowed disabled:opacity-40 dark:border-white/15";
const primary = `${button} bg-black text-white dark:bg-white dark:text-black`;

export type WhatsAppLinkViewProps = {
  status: WhatsAppLinkStatus | null;
  code: WhatsAppLinkCode | null;
  loading: boolean;
  busy: boolean;
  problem: WhatsAppLinkProblem | null;
  confirmingUnlink: boolean;
  consent?: WhatsAppAIConsent | null;
  onToggleAI?: () => void;
  onCreateCode: () => void;
  onAskUnlink: (ask: boolean) => void;
  onUnlink: () => void;
  onRefresh: () => void;
};

export function WhatsAppLinkView({
  status,
  code,
  loading,
  busy,
  problem,
  confirmingUnlink,
  onCreateCode,
  onAskUnlink,
  onUnlink,
  onRefresh,
}: WhatsAppLinkViewProps) {
  const { t } = useTranslation();
  const blocked = problem === "unavailable" || problem === "space_missing";
  return (
    <div className="space-y-5 p-5 text-sm text-black dark:text-white">
      <section className="rounded-2xl bg-black/5 p-4 dark:bg-white/5">
        <h3 className="font-medium">{t("settings.whatsapp.number", "Linked number")}</h3>
        {loading ? (
          <p role="status" className="mt-2">{t("settings.whatsapp.loading", "Reading your link…")}</p>
        ) : status?.linked ? (
          <p className="mt-2">{t("settings.whatsapp.linked", "Number ending in {{last4}}", { last4: status.last4 ?? "••••" })}</p>
        ) : (
          <p className="mt-2">{t("settings.whatsapp.unlinked", "No number is linked.")}</p>
        )}
      </section>
      {problem ? (
        <p role="alert" className={inlineFailureTextClass}>
          {t(`settings.whatsapp.problem_${problem}`, "WhatsApp could not be reached. Try again.")}
        </p>
      ) : null}
      {code ? (
        <section className="space-y-3 rounded-2xl border border-black/10 p-4 dark:border-white/10">
          <p>{t("settings.whatsapp.send_steps", "Send this message from your own WhatsApp to the Cuadrao number. The code works once and expires soon.")}</p>
          <div className="flex items-start gap-2">
            <p className="min-w-0 flex-1 select-all break-all font-mono text-base" data-testid="whatsapp-link-message">{code.message_text}</p>
            <CopyCodeButton text={code.message_text} />
          </div>
          {code.wa_me_url ? (
            <a className={`${primary} inline-flex items-center`} href={code.wa_me_url} target="_blank" rel="noopener noreferrer">
              {t("settings.whatsapp.open", "Open WhatsApp")}
            </a>
          ) : (
            <p className="text-black/60 dark:text-white/60">{t("settings.whatsapp.no_link", "Open WhatsApp and send the message above to the Cuadrao number.")}</p>
          )}
          <button type="button" className={button} onClick={onRefresh} disabled={loading || busy}>
            {t("settings.whatsapp.check", "I sent it, check")}
          </button>
        </section>
      ) : null}
      {status?.linked ? <section className="rounded-xl border border-black/10 p-4 dark:border-white/10">
        <p>{t("business.activity.all_channels", "Receipt reading is managed for your Business across email, WhatsApp and uploads.")}</p>
        <a href="/biz?view=inbox" className={`${button} mt-3 inline-flex items-center`}>{t("business.activity.open_settings", "Open receipt reading settings")}</a>
      </section> : null}
      <div className="flex flex-wrap gap-2">
        {!status?.linked ? (
          <button type="button" className={primary} onClick={onCreateCode} disabled={loading || busy || blocked}>
            {t(code ? "settings.whatsapp.new_code" : "settings.whatsapp.create", code ? "Get a new code" : "Get a link code")}
          </button>
        ) : null}
        {status?.linked ? (
          <button type="button" className={button} onClick={() => onAskUnlink(true)} disabled={busy}>
            {t("settings.whatsapp.unlink", "Unlink number")}
          </button>
        ) : null}
      </div>
      {confirmingUnlink ? (
        <div className="space-y-3 rounded-xl border border-black/10 p-3 dark:border-white/10">
          <p>{t("settings.whatsapp.confirm_unlink", "Unlink your number? New messages will no longer be accepted from it. Receipts already received stay in your Inbox.")}</p>
          <div className="flex gap-2">
            <button type="button" className={button} onClick={onUnlink} disabled={busy}>{t("settings.whatsapp.confirm", "Confirm")}</button>
            <button type="button" className={button} onClick={() => onAskUnlink(false)}>{t("settings.whatsapp.cancel", "Cancel")}</button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

export default function WhatsAppLinkModal({
  onClose,
  onBack,
  backLabel,
}: {
  onClose: () => void;
  onBack?: () => void;
  backLabel?: string;
}) {
  const { t, i18n } = useTranslation();
  const [status, setStatus] = useState<WhatsAppLinkStatus | null>(null);
  const [code, setCode] = useState<WhatsAppLinkCode | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<WhatsAppLinkProblem | null>(null);
  const [confirmingUnlink, setConfirmingUnlink] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const next = await getWhatsAppLink();
      setStatus(next);
      setProblem(null);
      if (next.linked) {
        setCode(null);
      }
    } catch (error) {
      setProblem(whatsAppLinkProblem(error));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function createCode() {
    setBusy(true);
    try {
      setCode(await createWhatsAppLinkCode(i18n.resolvedLanguage?.startsWith("es") ? "es-419" : "en"));
      setProblem(null);
    } catch (error) {
      setProblem(whatsAppLinkProblem(error));
    } finally {
      setBusy(false);
    }
  }

  async function unlink() {
    setBusy(true);
    try {
      await unlinkWhatsApp();
      setConfirmingUnlink(false);
      await refresh();
    } catch (error) {
      setProblem(whatsAppLinkProblem(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <AdaptivePanel
      title={t("settings.whatsapp.title", "WhatsApp")}
      closeLabel={t("common.close", "Close")}
      onClose={onClose}
      onBack={onBack}
      backLabel={backLabel}
      width="md"
    >
      <WhatsAppLinkView
        {...{ status, code, loading, busy, problem, confirmingUnlink }}
        onCreateCode={() => void createCode()}
        onAskUnlink={setConfirmingUnlink}
        onUnlink={() => void unlink()}
        onRefresh={() => void refresh()}
      />
    </AdaptivePanel>
  );
}
