"use client";

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import type { BusinessEmailIntake } from "@/lib/business-email";
import { businessReceivingAddress } from "@/lib/business-email";
import { useBusiness } from "./BusinessWorkspace";
import { cardClass, secondaryButtonClass } from "./business-ui";

type Load = { status: "loading" } | { status: "error" } | { status: "ready"; data: BusinessEmailIntake };

export function EmailReceivingAddress({ intake, onActivate }: { intake: BusinessEmailIntake; onActivate: () => Promise<void> }) {
  const { t } = useTranslation();
  const address = businessReceivingAddress(intake);
  const [copy, setCopy] = useState<"idle" | "copied" | "failed">("idle");
  const [activation, setActivation] = useState<"idle" | "working" | "failed">("idle");
  if (!address) {
    return (
      <div className="space-y-2">
        <p className="text-[13px] text-black/55 dark:text-white/55">{t("business.email.no_address", "This business has no receiving address yet.")}</p>
        <button type="button" className={secondaryButtonClass} disabled={activation === "working"} onClick={async () => {
          setActivation("working");
          try { await onActivate(); setActivation("idle"); } catch { setActivation("failed"); }
        }}>{t("business.email.activate", "Get a receiving address")}</button>
        {activation === "failed" ? <p role="alert" className="text-[13px] text-black/70 dark:text-white/70">{t("business.email.activate_failed", "Email receiving is not available for this business yet.")}</p> : null}
      </div>
    );
  }
  return (
    <div className="space-y-2">
      <p className="text-[13px] text-black/55 dark:text-white/55">{t("business.email.forward_to", "Forward receipts to this address:")}</p>
      <div className="flex flex-wrap items-center gap-2">
        <span className="min-w-0 break-all text-[14px] font-medium text-black dark:text-white">{address}</span>
        <button type="button" className={secondaryButtonClass} onClick={async () => {
          try { await navigator.clipboard.writeText(address); setCopy("copied"); } catch { setCopy("failed"); }
        }}>{t("business.email.copy", "Copy address")}</button>
      </div>
      {copy !== "idle" ? <p role="status" className="text-[13px] text-black/55 dark:text-white/55">{copy === "copied" ? t("business.email.copied", "Address copied.") : t("business.email.copy_failed", "Could not copy. Select the address to copy it.")}</p> : null}
    </div>
  );
}

export default function InboxForwardingCard() {
  const { t } = useTranslation();
  const { source, revision } = useBusiness();
  const [intake, setIntake] = useState<Load>({ status: "loading" });
  useEffect(() => {
    let current = true;
    setIntake({ status: "loading" });
    source.emailIntake().then((data) => { if (current) setIntake({ status: "ready", data }); }).catch(() => { if (current) setIntake({ status: "error" }); });
    return () => { current = false; };
  }, [source, revision]);
  if (intake.status === "loading") return null;
  return (
    <section aria-label={t("business.email.forward_to", "Forward receipts to this address:")} data-testid="inbox-forwarding-card" className={`${cardClass} mt-6`}>
      {intake.status === "error" ? (
        <p role="alert" className="text-[13px] text-black/70 dark:text-white/70">{t("business.email.address_failed", "Could not load the receiving address.")}</p>
      ) : (
        <EmailReceivingAddress intake={intake.data} onActivate={async () => { const next = await source.createEmailAddress(); setIntake({ status: "ready", data: next }); }} />
      )}
    </section>
  );
}
