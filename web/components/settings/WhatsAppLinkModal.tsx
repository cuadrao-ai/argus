"use client";

import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import AdaptivePanel from "@/components/ui/AdaptivePanel";
import { inlineFailureTextClass } from "@/lib/failure-treatment";
import {
  canEnableAI,
  consentModels,
  createWhatsAppLinkCode,
  enableWhatsAppAI,
  getWhatsAppAIConsent,
  getWhatsAppLink,
  revokeWhatsAppAI,
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
  agreed?: boolean;
  onAgree?: (agreed: boolean) => void;
  onEnableAI?: () => void;
  onRevokeAI?: () => void;
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
  consent = null,
  agreed = false,
  onAgree = () => {},
  onEnableAI = () => {},
  onRevokeAI = () => {},
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
          <p className="select-all break-all font-mono text-base" data-testid="whatsapp-link-message">{code.message_text}</p>
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
      {status?.linked && consent ? (
        <section className="space-y-3 rounded-2xl border border-black/10 p-4 dark:border-white/10" data-testid="whatsapp-ai-consent">
          <h3 className="font-medium">{t("settings.whatsapp.ai_title", "AI reading of your messages")}</h3>
          <p>
            {consent.enabled
              ? t("settings.whatsapp.ai_on", "AI reading is on for this number.")
              : t("settings.whatsapp.ai_off", "AI reading is off. Cuadrao cannot answer your messages yet.")}
          </p>
          {!consent.available && !consent.enabled ? (
            <p role="status">{t(`settings.whatsapp.ai_reason_${consent.reason ?? "unavailable"}`, t("settings.whatsapp.ai_reason_unavailable", "AI reading cannot be turned on right now."))}</p>
          ) : null}
          {canEnableAI(consent) ? (
            <>
              <p className="whitespace-pre-wrap rounded-xl bg-black/5 p-3 dark:bg-white/5">{consent.disclosure}</p>
              <p className="text-black/60 dark:text-white/60">
                {t("settings.whatsapp.ai_models", "Provider: OpenRouter. Models: {{models}}.", { models: consentModels(consent).join(", ") })}
              </p>
              <label className="flex min-h-11 cursor-pointer items-start gap-3 py-2">
                <input type="checkbox" className="mt-1 h-4 w-4 shrink-0" checked={agreed} disabled={busy} onChange={(event) => onAgree(event.target.checked)} />
                <span>{t("settings.whatsapp.ai_agree", "I read this and I allow AI to read my WhatsApp messages for my business.")}</span>
              </label>
              <button type="button" className={primary} onClick={onEnableAI} disabled={!agreed || busy}>
                {t("settings.whatsapp.ai_enable", "Turn on AI reading")}
              </button>
            </>
          ) : null}
          {consent.enabled ? (
            <button type="button" className={button} onClick={onRevokeAI} disabled={busy}>
              {t("settings.whatsapp.ai_revoke", "Turn off AI reading")}
            </button>
          ) : null}
          <p className="text-black/60 dark:text-white/60">{t("settings.whatsapp.ai_approval", "You always approve money records yourself in Cuadrao.")}</p>
        </section>
      ) : null}
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
  const [consent, setConsent] = useState<WhatsAppAIConsent | null>(null);
  const [agreed, setAgreed] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const next = await getWhatsAppLink();
      setStatus(next);
      setProblem(null);
      if (next.linked) {
        setCode(null);
        setConsent(await getWhatsAppAIConsent().catch(() => null));
      } else {
        setConsent(null);
      }
      setAgreed(false);
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

  async function changeAI(action: () => Promise<WhatsAppAIConsent | void>) {
    setBusy(true);
    try {
      const next = await action();
      setConsent(next ?? (await getWhatsAppAIConsent()));
      setAgreed(false);
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
        {...{ status, code, loading, busy, problem, confirmingUnlink, consent, agreed }}
        onAgree={setAgreed}
        onEnableAI={() => consent && canEnableAI(consent) && void changeAI(() => enableWhatsAppAI(consent.disclosure_token, crypto.randomUUID()))}
        onRevokeAI={() => void changeAI(() => revokeWhatsAppAI())}
        onCreateCode={() => void createCode()}
        onAskUnlink={setConfirmingUnlink}
        onUnlink={() => void unlink()}
        onRefresh={() => void refresh()}
      />
    </AdaptivePanel>
  );
}
