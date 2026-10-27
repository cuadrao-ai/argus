"use client";

import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { ChevronDown, Copy, Plus, Settings } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useOverlayLayer } from "@/components/layout/overlayStack";
import { businessReceivingAddress } from "@/lib/business-email";
import { useBusiness } from "../BusinessWorkspace";
import { primaryButtonClass } from "../business-ui";
import { copyText, WrappingAddress } from "../foundation/CopyButton";
import { showToast } from "../foundation/toasts";
import styles from "./reception.module.css";

type AddressLoad = { source: ReturnType<typeof useBusiness>["source"]; revision: number; address: string | null; failed: boolean };

export default function ReceptionAddMenu() {
  const { t } = useTranslation();
  const { actions, chosen, source, revision, openPanel } = useBusiness();
  const [loaded, setLoaded] = useState<AddressLoad | null>(null);
  const [position, setPosition] = useState<{ right: number; top: number } | null>(null);
  const [copyFailed, setCopyFailed] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const id = useId();
  const open = position !== null;
  const current = loaded?.source === source && loaded.revision === revision ? loaded : null;
  const address = current?.address;
  const add = chosen?.role !== "accountant" ? actions.create.find(action => action.id === "upload_receipt") : undefined;
  const close = () => { setPosition(null); trigger.current?.focus(); };
  useEffect(() => {
    let live = true;
    source.emailIntake().then(intake => {
      if (live) setLoaded({ source, revision, address: businessReceivingAddress(intake), failed: false });
    }, () => { if (live) setLoaded({ source, revision, address: null, failed: true }); });
    return () => { live = false; };
  }, [source, revision]);
  useOverlayLayer({ isOpen: open, overlayId: id, containerRef: menu, trapFocus: false, onEscape: close, onOutsidePointerDown: event => { if (!trigger.current?.contains(event.target as Node)) setPosition(null); } });
  useEffect(() => {
    if (!open) return;
    (menu.current?.querySelector<HTMLButtonElement>("button:not(:disabled)") ?? menu.current)?.focus();
    const dismiss = () => setPosition(null);
    window.addEventListener("resize", dismiss);
    return () => window.removeEventListener("resize", dismiss);
  }, [open, current]);
  if (!add) return null;
  const setup = () => { close(); openPanel({ kind: "business", tab: "correo" }); };
  const copy = async () => {
    if (!address) return;
    if (await copyText(address)) { close(); showToast({ kind: "info", text: t("business.email.copied") }); }
    else setCopyFailed(true);
  };
  return <div className={styles.addSplit} data-testid="reception-add">
    <button type="button" data-testid="business-primary-upload" className={`${primaryButtonClass} rounded-r-none pl-4 pr-3`} onClick={add.run}><Plus size={16} aria-hidden="true" />{add.label}</button>
    <button ref={trigger} type="button" className={`${primaryButtonClass} min-w-11 rounded-l-none border-l border-[var(--cuadrao-cream)]/25 px-3`} aria-label={t("business.reception_preview.forward_options")} aria-haspopup="menu" aria-expanded={open} aria-controls={open ? id : undefined} onClick={() => {
      if (open) { close(); return; }
      const rect = trigger.current?.getBoundingClientRect();
      if (rect) { setCopyFailed(false); setPosition({ right: Math.max(16, window.innerWidth - rect.right), top: Math.min(rect.bottom + 8, Math.max(16, window.innerHeight - 240)) }); }
    }}><ChevronDown size={16} aria-hidden="true" /></button>
    {position ? createPortal(<div ref={menu} id={id} role="menu" tabIndex={-1} aria-label={t("business.reception_preview.forward_options")} className={styles.forwardMenu} style={position} onKeyDown={event => {
      if (["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) { event.preventDefault(); menu.current?.querySelector<HTMLButtonElement>("button:not(:disabled)")?.focus(); }
      if (event.key === "Tab") { event.preventDefault(); close(); }
    }}>
      <div className={styles.forwardInfo} role="presentation">
        <p>{t(!current ? "common.loading" : current.failed ? "business.email.address_failed" : address ? "business.email.forward_to" : "business.email.no_address")}</p>
        {address ? <p className={styles.forwardAddress}><WrappingAddress address={address} /></p> : null}
        {copyFailed ? <p role="alert">{t("business.email.copy_failed")}</p> : null}
      </div>
      {current ? <button type="button" role="menuitem" className={styles.forwardAction} onClick={address ? () => void copy() : setup}>{address ? <Copy size={18} aria-hidden="true" /> : <Settings size={18} aria-hidden="true" />}<span>{t(address ? "business.overview.copy_forward" : "business.reception_preview.setup_forward")}</span></button> : null}
    </div>, document.body) : null}
  </div>;
}
