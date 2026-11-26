"use client";

import { useContext, useEffect, useId, useState, type ReactNode } from "react";
import { Clock, ExternalLink, Info, LoaderCircle, MessageCirclePlus } from "lucide-react";
import Image from "next/image";
import { useTranslation } from "react-i18next";
import { BusinessContext } from "@/components/business-app/business-context";
import { primaryButtonClass, secondaryButtonClass } from "@/components/business-app/business-ui";
import { CHANNEL_ICON } from "@/components/business-app/foundation/channel-icons";
import SettingsSurface from "@/components/settings/SettingsSurface";
import CopyCodeButton from "@/components/settings/CopyCodeButton";
import { inlineFailureTextClass } from "@/lib/failure-treatment";
import {
  createWhatsAppLinkCode, getWhatsAppLink, unlinkWhatsApp, whatsAppLinkProblem,
  type WhatsAppLinkCode, type WhatsAppLinkProblem, type WhatsAppLinkStatus,
} from "@/lib/whatsapp-link-api";

const muted = "text-sm leading-5 text-[#56635e] dark:text-white/70";
const box = "flex items-start gap-3 rounded-surface bg-[#F7F5EE] p-4 dark:bg-[#1f2225]";
const title = "text-base font-medium";
const number = "inline-grid h-6 w-6 shrink-0 place-items-center rounded-full border border-[var(--surface-divider)] text-[13px] tabular-nums";
const key = (name: string) => `settings.whatsapp.${name}`;

function Intro({ blocked }: { blocked: boolean }) {
  const { t } = useTranslation();
  const setupHeading = useId();
  const WhatsApp = CHANNEL_ICON.whatsapp;
  return <>
    <div className="flex items-start gap-4">
      <span className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-[#F7F5EE] dark:bg-[#1f2225]"><WhatsApp size={24} aria-hidden="true" /></span>
      <div className="space-y-1"><h3 className={title}>{t(key("intro_title"))}</h3><p className={muted}>{t(key("intro_body"))}</p>
        {!blocked && <p className={muted}>{t(key("intro_held"))}</p>}
      </div>
    </div>
    {blocked ? <>
      <div className={box} role="status"><Info size={20} className="shrink-0" aria-hidden="true" /><div>
        <h3 id={setupHeading} className={title}>{t(key("setup_title"))}</h3><p className={`${muted} mt-1`}>{t(key("setup_body"))}</p>
      </div></div>
      <ol aria-labelledby={setupHeading} className="divide-y divide-[var(--surface-divider)] rounded-surface bg-[#F7F5EE] px-4 dark:bg-[#1f2225]">
        {["fiscal_identity", "receipt_reading"].map((step, i) => <li key={step} className="flex items-center gap-3 py-3">
          <span className={number} aria-hidden="true">{i + 1}</span>{t(`business.home_setup.steps.${step}.title`)}
        </li>)}
      </ol>
    </> : <div className={box}><MessageCirclePlus size={20} className="shrink-0" aria-hidden="true" /><p className={muted}>{t(key("consent_notice"))}</p></div>}
  </>;
}

function QR({ code, expired = false }: { code: WhatsAppLinkCode; expired?: boolean }) {
  const { t } = useTranslation();
  if (!code.qr_data_url) return null;
  return <div className="relative hidden shrink-0 self-start overflow-hidden rounded-item border border-[var(--surface-divider)] bg-white tablet:block">
    <Image src={code.qr_data_url} unoptimized width={148} height={148} alt={expired ? "" : t(key("scan_title"))} className={expired ? "opacity-20" : undefined}/>
    {expired && <Clock aria-hidden="true" className="absolute top-1/2 left-1/2 h-10 w-10 -translate-1/2 rounded-full border bg-white p-2 text-[#56635e]" />}
  </div>;
}

function CodeMessage({ code, expired = false }: { code: WhatsAppLinkCode; expired?: boolean }) {
  return <div className="flex min-h-11 items-center gap-2 rounded-item border border-[var(--surface-divider)] py-1 pr-1 pl-3">
    <code data-testid="whatsapp-link-message" className={`min-w-0 flex-1 break-all font-mono tracking-wide ${expired ? "text-[#85918c] line-through" : "select-all"}`}>{code.message_text}</code>
    {!expired && <CopyCodeButton text={code.message_text} />}
  </div>;
}

function OpenWhatsApp({ url, mobile = false }: { url: string; mobile?: boolean }) {
  const { t } = useTranslation();
  return <a href={url} target="_blank" rel="noopener noreferrer" className={mobile ? `${primaryButtonClass} w-full tablet:hidden` : `${secondaryButtonClass} shrink-0 whitespace-nowrap max-tablet:hidden`}>
    {t(key("open"))}<ExternalLink size={16} aria-hidden="true" />
  </a>;
}

function Waiting({ code, seconds }: { code: WhatsAppLinkCode; seconds: number }) {
  const { t } = useTranslation();
  const time = `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
  return <>
    {code.wa_me_url && <>
      <div className="space-y-3 tablet:hidden"><h3 className={title}>{t(key("mobile_title"))}</h3>
        <p className={muted}>{t(key("mobile_steps"))}</p><OpenWhatsApp url={code.wa_me_url} mobile />
      </div>
      <h3 className={`${title} hidden tablet:block`}>{t(key("scan_title"))}</h3>
    </>}
    <div className="flex gap-6">
      <QR code={code} /><div className="min-w-0 flex-1 space-y-4">
        {code.qr_data_url && <ol className="hidden space-y-3 tablet:block">
          {["scan_camera", "scan_send", "scan_return"].map((step, i) => <li key={step} className="flex gap-3">
            <span className={number} aria-hidden="true">{i + 1}</span>{t(key(step))}
          </li>)}
        </ol>}
        <div className="flex items-center gap-2 text-sm"><LoaderCircle size={18} aria-hidden="true" className="text-[var(--cuadrao-green)] motion-safe:animate-spin" />
          <span role="status">{t(key("waiting"))}</span><span role="timer" className={`${muted} ml-auto tabular-nums`}>{t(key("expires_in"), { time })}</span>
        </div>
      </div>
    </div>
    <div className="space-y-2 max-tablet:border-t max-tablet:border-[var(--surface-divider)] max-tablet:pt-5">
      <p className={muted}>{t(key("send_steps"))}</p><CodeMessage code={code} />
    </div>
  </>;
}

type Frame = { onClose: () => void; onBack?: () => void; backLabel?: string };
type Issued = { code: WhatsAppLinkCode; seconds: number };
const remaining = (expires: string) => Math.max(0, Math.ceil((Date.parse(expires) - Date.now()) / 1000));

export default function WhatsAppLinkModal(frame: Frame) {
  const { t, i18n } = useTranslation();
  const business = useContext(BusinessContext);
  const [status, setStatus] = useState<WhatsAppLinkStatus | null>(null);
  const [issued, setIssued] = useState<Issued | null>(null);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<WhatsAppLinkProblem | null>(null);
  const [confirmUnlink, setConfirmUnlink] = useState(false);
  const code = issued?.code;
  const language = i18n.resolvedLanguage?.startsWith("es") ? "es-419" : "en";
  const notice: unknown = i18n.getResource(language, "common", key("consent_notice"));

  useEffect(() => {
    const request = new AbortController();
    getWhatsAppLink(request.signal).then((next) => {
      if (!request.signal.aborted) setStatus(next);
    }).catch((error) => {
      if (!request.signal.aborted) setProblem(whatsAppLinkProblem(error));
    });
    return () => request.abort();
  }, []);

  useEffect(() => {
    if (!code || !remaining(code.expires_at)) return;
    const request = new AbortController();
    let nextPoll = Date.now() + 3000;
    let reading = false;
    const timer = setInterval(async () => {
      const seconds = remaining(code.expires_at);
      setIssued((current) => current?.code === code ? { code, seconds } : current);
      if (!seconds) {
        clearInterval(timer);
        request.abort();
        return;
      }
      if (Date.now() < nextPoll || reading) return;
      reading = true;
      nextPoll = Date.now() + 3000;
      try {
        const next = await getWhatsAppLink(request.signal);
        if (request.signal.aborted) return;
        setStatus(next);
        setProblem(null);
        if (next.linked || !next.receiving_businesses.length) setIssued(null);
      } catch (error) {
        if (request.signal.aborted) return;
        const failure = whatsAppLinkProblem(error);
        setProblem(failure);
        if (failure === "unavailable" || failure === "setup_required") setIssued(null);
      } finally {
        reading = false;
      }
    }, 1000);
    return () => { clearInterval(timer); request.abort(); };
  }, [code]);

  async function createCode() {
    if (typeof notice !== "string" || !notice) return;
    setBusy(true);
    try {
      const next = await createWhatsAppLinkCode(language, notice);
      setIssued({ code: next, seconds: remaining(next.expires_at) });
      setProblem(null);
    } catch (error) {
      setIssued(null);
      setProblem(whatsAppLinkProblem(error));
    } finally {
      setBusy(false);
    }
  }

  async function unlink() {
    setBusy(true);
    try {
      await unlinkWhatsApp();
      setConfirmUnlink(false);
      setStatus(await getWhatsAppLink());
      setProblem(null);
    } catch (error) {
      setProblem(whatsAppLinkProblem(error));
    } finally {
      setBusy(false);
    }
  }

  const cancel = <button type="button" className={secondaryButtonClass} onClick={() => { setIssued(null); setProblem(null); }}>{t(key("cancel"))}</button>;
  const create = (label: string) => <button type="button" disabled={busy || !notice} className={primaryButtonClass} onClick={createCode}>{t(key(label))}</button>;
  const blocked = problem === "setup_required" || status?.receiving_businesses.length === 0;
  let body: ReactNode;
  let footer: ReactNode;
  if (status?.linked) {
    body = <>
      <section className={box}><div><h3 className={title}>{t(key("number"))}</h3><p>{t(key("linked"), { last4: status.last4 })}</p></div></section>
      <section className="space-y-2 rounded-surface border border-[var(--surface-divider)] p-4">
        <p>{t("business.activity.all_channels")}</p><a href="/biz?view=inbox" className={secondaryButtonClass}>{t("business.activity.open_settings")}</a>
      </section>
      {confirmUnlink && <p>{t(key("confirm_unlink"))}</p>}
    </>;
    footer = confirmUnlink ? <>
      <button className={secondaryButtonClass} disabled={busy} onClick={unlink}>{t(key("confirm"))}</button>
      <button className={secondaryButtonClass} onClick={() => setConfirmUnlink(false)}>{t(key("cancel"))}</button>
    </> : <button className={secondaryButtonClass} onClick={() => setConfirmUnlink(true)}>{t(key("unlink"))}</button>;
  } else if (issued && issued.seconds > 0) {
    body = <Waiting code={issued.code} seconds={issued.seconds} />;
    footer = <>{issued.code.wa_me_url && <><p className={`${muted} min-w-0 flex-1 max-tablet:hidden`}>{t(key("desktop_prompt"))}</p>
      <OpenWhatsApp url={issued.code.wa_me_url} /></>}{cancel}</>;
  } else if (issued) {
    body = <>
      <div className={box} role="status"><Clock className="shrink-0" size={20} aria-hidden="true" /><div><h3 className={title}>{t(key("expired_title"))}</h3><p className={muted}>{t(key("expired_body"))}</p></div></div>
      <div className="flex items-center gap-6"><QR code={issued.code} expired /><div className="min-w-0 flex-1 space-y-3"><p className={muted}>{t(key("expired_message"))}</p><CodeMessage code={issued.code} expired />
        <div className="hidden tablet:block">{create("new_code")}</div>
      </div></div>
    </>;
    footer = <><div className="grid tablet:hidden">{create("new_code")}</div>{cancel}</>;
  } else if (problem === "rate_limited") {
    footer = <>{create("new_code")}{cancel}</>;
  } else if (blocked) {
    body = <Intro blocked />;
    footer = <a href="/biz?view=business&tab=datos" className={primaryButtonClass} onClick={(event) => {
      if (!business) return;
      event.preventDefault();
      frame.onClose();
      business.openPanel({ kind: "business", tab: "datos" });
    }}>{t("business.switcher.settings")}</a>;
  } else if (status && problem !== "unavailable") {
    body = <Intro blocked={false} />;
    footer = create("link_phone");
  } else if (!problem) {
    body = <p role="status">{t(key("loading"))}</p>;
  }
  return <SettingsSurface {...frame} title={t(key("title"))} closeLabel={t("common.close")} width="md"
    footer={footer && <div className="flex flex-col gap-3 tablet:flex-row tablet:items-center tablet:justify-end">{footer}</div>}>
    <div className="space-y-[21px] px-4 py-5 text-base text-[#172b26] tablet:px-6 dark:text-white">
      {problem && problem !== "setup_required" && <p role="alert" className={inlineFailureTextClass}>{t(key(`problem_${problem}`))}</p>}
      {body}
    </div>
  </SettingsSurface>;
}
