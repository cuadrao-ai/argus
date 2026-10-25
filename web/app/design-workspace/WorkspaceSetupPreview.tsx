"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { primaryButtonClass, secondaryButtonClass, quietButtonClass, dangerButtonClass, dangerConfirmButtonClass } from "@/components/business-app/business-ui";
import { BusinessEmailAddress } from "@/components/business-app/BusinessEmailDeliveries";
import { CopyButton } from "@/components/business-app/foundation/CopyButton";
import { useTranslation } from "react-i18next";
import { TABLET_MIN_WIDTH_PX } from "@/lib/responsive-layout";
import InvitationAccessPicker from "./InvitationAccessPicker";
import InvitationPreviewModal from "./InvitationPreviewModal";
import { fieldClass, fieldLabelClass } from "@/components/ui/form-field";
import AdaptivePanel from "@/components/ui/AdaptivePanel";
import { useBusiness } from "@/components/business-app/BusinessWorkspace";


function PreviewCopy({ slot }: { slot: HTMLElement }) {
  const [failed, setFailed] = useState(false);
  const label = slot.dataset.copyLabel || "";
  return <span onClickCapture={() => setFailed(false)}>
    <CopyButton value={slot.dataset.copyValue || ""} label={label}
      copiedLabel={slot.dataset.copySuccess || ""} failedLabel={slot.dataset.copyError || ""}
      onFailed={() => setFailed(true)} className={secondaryButtonClass}>
      {label}
    </CopyButton>
    {failed ? <span className="block pt-2 text-sm text-[#9e2f39] dark:text-[#ec9aa0]" role="alert">{slot.dataset.copyError}</span> : null}
  </span>;
}

/** Local review adapter. The sketch remains the single source for the card. */
export default function WorkspaceSetupPreview({ invitation, profileInvoicing, reception, embedded = false, onClose, onProfileChange }: { invitation?: boolean; profileInvoicing?: boolean; reception?: "whatsapp"; embedded?: boolean; onClose?: () => void; onProfileChange?: () => void } = {}) {
  const frame = useRef<HTMLIFrameElement>(null);
  const [height, setHeight] = useState(410);
  const [copySlots, setCopySlots] = useState<HTMLElement[]>([]);
  const [accessSlots, setAccessSlots] = useState<HTMLElement[]>([]);
  const [emailSlot, setEmailSlot] = useState<HTMLElement | null>(null);
  const dossierFrame = useRef<HTMLIFrameElement>(null);
  const [dossier, setDossier] = useState<"whatsapp" | "invoicing" | null>(profileInvoicing ? "invoicing" : reception ?? null);
  const [dossierHeight, setDossierHeight] = useState(700);
  const { t, i18n } = useTranslation();
  const { actions, bridge, chosen, records, renamePreviewBusiness } = useBusiness();
  const memberEmail = bridge?.memberEmail;
  const context = useMemo(() => chosen ? {
    businessId: chosen.space_id,
    name: chosen.name,
    country: records?.workspace?.country ?? null,
    shared: chosen.role !== "owner",
    documentReceived: Boolean(records?.inbox?.length),
    currentMember: memberEmail ? { email: memberEmail, permission: chosen.role } : null,
  } : null, [memberEmail, chosen, records?.workspace?.country, records?.inbox]);
  const invitationFixture = typeof window !== "undefined" && invitation ? new URLSearchParams(window.location.search).get("inviteResult") : null;
  const fixtureQuery = ["partial", "error"].includes(invitationFixture ?? "") ? `&inviteResult=${invitationFixture}` : "";
  const scope = chosen ? `?business=${encodeURIComponent(chosen.space_id)}` : "";
  const upload = chosen?.role !== "accountant"
    ? actions.create.find((action) => action.id === "upload_receipt")
    : undefined;
  const inheritControls = useCallback(() => {
    const buttonLevels: Record<string, string> = {
      primary: primaryButtonClass,
      secondary: secondaryButtonClass,
      quiet: quietButtonClass,
      danger: dangerButtonClass,
      dangerConfirm: dangerConfirmButtonClass,
    };
    const slots: HTMLElement[] = [];
    for (const target of [frame.current, dossierFrame.current]) {
      const doc = target?.contentDocument;
      if (!doc?.body) continue;
      // Share the app stylesheet and the button class exports across the frame.
      for (const sheet of document.querySelectorAll<HTMLLinkElement>('link[rel="stylesheet"]')) {
        if (Array.from(doc.querySelectorAll<HTMLLinkElement>('link[data-app-styles]')).some(link => link.href === sheet.href)) continue;
        const link = doc.createElement("link");
        link.rel = "stylesheet"; link.href = sheet.href; link.dataset.appStyles = "";
        doc.head.prepend(link);
      }
      const appType = getComputedStyle(document.body);
      for (const token of ["--font-inter", "--font-space-grotesk"]) {
        const value = appType.getPropertyValue(token).trim();
        if (value) doc.documentElement.style.setProperty(token, value);
      }
      doc.documentElement.classList.toggle("dark", document.documentElement.classList.contains("dark"));
      for (const el of doc.querySelectorAll<HTMLElement>('[data-button-level],button.primary,button.secondary,button.textbtn')) {
        const level = el.dataset.buttonLevel || (el.classList.contains("primary") ? "primary" : el.classList.contains("secondary") ? "secondary" : "quiet");
        el.dataset.buttonLevel = level;
        const classes = buttonLevels[level];
        if (classes) el.className = `${el.closest(".invite-surface .formfoot")
          ? classes.replace("rounded-full", "rounded-lg")
          : classes} text-[16px]`;
      }
      for (const input of doc.querySelectorAll<HTMLInputElement>("#inviteemail, [data-recipient-email]")) input.className = fieldClass;
      for (const label of doc.querySelectorAll<HTMLElement>('label[for="inviteemail"]')) label.className = fieldLabelClass;
      for (const link of doc.querySelectorAll<HTMLAnchorElement>('a.wa-open')) {
        link.className = `wa-open ${window.innerWidth < TABLET_MIN_WIDTH_PX ? primaryButtonClass : secondaryButtonClass} text-[16px]`;
      }
      for (const slot of doc.querySelectorAll<HTMLElement>('[data-copy-value]')) {
        if (!slot.dataset.copyMounted) { slot.replaceChildren(); slot.dataset.copyMounted = "true"; }
        slots.push(slot);
      }
    }
    const access = Array.from(frame.current?.contentDocument?.querySelectorAll<HTMLElement>("[data-invite-permission]") ?? []);
    setAccessSlots(previous => previous.length === access.length && previous.every((slot, i) => slot === access[i]) ? previous : access);
    setEmailSlot(frame.current?.contentDocument?.querySelector<HTMLElement>("[data-business-email]") ?? null);
    setCopySlots(previous => previous.length === slots.length && previous.every((slot, i) => slot === slots[i]) ? previous : slots);
  }, []);
  const syncAppearance = useCallback(() => {
    inheritControls();
    const homeCard = document.querySelector<HTMLElement>('[data-testid="month-close-checklist"], [data-testid="month-close-income"]');
    const modal = invitation ? document.querySelector<HTMLElement>("[data-invitation-modal]") : null;
    const surface = modal ? getComputedStyle(modal).backgroundColor : homeCard ? getComputedStyle(homeCard).backgroundColor : undefined;
    for (const target of [frame.current, dossierFrame.current]) target?.contentWindow?.postMessage({
      type: "workspace-preview-theme",
      context,
      surface,
      language: i18n.resolvedLanguage || i18n.language,
      mobile: window.innerWidth < TABLET_MIN_WIDTH_PX,
      dark: document.documentElement.classList.contains("dark"),
      font: getComputedStyle(document.body).fontFamily,
    }, window.location.origin);
  }, [i18n.resolvedLanguage, i18n.language, inheritControls, context, invitation]);
  useEffect(() => {
    const receive = (event: MessageEvent) => {
      if (event.origin !== window.location.origin) return;
      const fromGuide = Boolean(event.source) && event.source === frame.current?.contentWindow;
      const fromDossier = Boolean(event.source) && event.source === dossierFrame.current?.contentWindow;
      if (!fromGuide && !fromDossier) return;
      if (event.data?.type === "workspace-preview-pointerdown") {
        // Frame events do not bubble into the parent overlay registry.
        (fromDossier ? dossierFrame.current : frame.current)?.dispatchEvent(
          new PointerEvent("pointerdown", { bubbles: true }),
        );
        return;
      }
      if (event.data?.type === "workspace-preview-rename" && event.data.businessId === chosen?.space_id && typeof event.data.name === "string") renamePreviewBusiness?.(event.data.name);
      if (event.data?.type === "workspace-preview-ready") syncAppearance();
      if (event.data?.type === "workspace-preview-render") { inheritControls(); if (fromDossier) onProfileChange?.(); }
      if (fromGuide && event.data?.type === "workspace-preview-whatsapp-settings") setDossier("whatsapp");
      if (fromGuide && event.data?.type === "workspace-preview-invoicing") setDossier("invoicing");
      if (event.data?.type === "workspace-preview-close-dossier") {
        if (fromGuide && invitation) onClose?.();
        if (fromDossier) { setDossier(null); if(profileInvoicing || reception) onClose?.(); }
      }
      if (fromDossier && event.data?.type === "workspace-preview-whatsapp-connected") { setDossier(null); if (reception) onClose?.(); }
      if (event.data?.type === "workspace-preview-upload") {
        upload?.run();
        frame.current?.contentWindow?.postMessage({
          type: "workspace-preview-upload-result", available: Boolean(upload),
        }, window.location.origin);
      }
      if (event.data?.type === "workspace-preview-height" && Number.isFinite(event.data.height)) {
        (fromDossier ? setDossierHeight : setHeight)(Math.max(64, Math.min(5000, event.data.height)));
      }
    };
    window.addEventListener("message", receive);
    return () => window.removeEventListener("message", receive);
  }, [upload, syncAppearance, inheritControls, chosen?.space_id, renamePreviewBusiness, invitation, profileInvoicing, reception, onClose, onProfileChange]);
  useEffect(() => {
    const observer = new MutationObserver(syncAppearance);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class", "style"] });
    syncAppearance();
    window.addEventListener("resize", syncAppearance);
    return () => { observer.disconnect(); window.removeEventListener("resize", syncAppearance); };
  }, [syncAppearance]);
  const guide = <iframe
    ref={frame}
    key={chosen?.space_id ?? "unselected"}
    src={`/design-workspace/card${scope}${invitation ? `${scope ? "&" : "?"}surface=invite${fixtureQuery}` : ""}`}
    title={t(invitation ? "workspace_setup_preview.batch_title" : "workspace_setup_preview.setup")}
    onLoad={syncAppearance}
    className={`${invitation ? "" : "mb-8 "}block w-full border-0`}
    style={{ height }}
  />;
  const dossierContent = <iframe key={`${chosen?.space_id ?? "unselected"}:${dossier}`} ref={dossierFrame} src={`/design-workspace/card${scope}${scope ? "&" : "?"}surface=${dossier}${profileInvoicing ? "&entry=profile" : ""}`} title={dossier === "whatsapp" ? "WhatsApp" : t("workspace_setup_preview.invoice_title")} onLoad={syncAppearance} className="block w-full border-0" style={{ height: dossierHeight }} />;
  return <>{accessSlots.filter(slot => slot.isConnected).map(slot => createPortal(<InvitationAccessPicker slot={slot} />, slot, slot.dataset.key ?? "access"))}{emailSlot?.isConnected ? createPortal(<BusinessEmailAddress />, emailSlot) : null}{copySlots.filter(slot => slot.isConnected).map((slot, index) => createPortal(<PreviewCopy slot={slot} />, slot, String(index)))}{invitation ? <InvitationPreviewModal frame={frame} onClose={() => onClose?.()}>{guide}</InvitationPreviewModal> : profileInvoicing || reception ? null : guide}
    {dossier ? embedded ? dossierContent : <AdaptivePanel title={dossier === "whatsapp" ? "WhatsApp" : t("workspace_setup_preview.invoice_title")} closeLabel={t("common.close", "Close")} onClose={() => {setDossier(null);if(profileInvoicing || reception)onClose?.();}} width="lg" snaps={["full"]} initialSnap="full">
      {dossierContent}
    </AdaptivePanel> : null}
  </>;
}
