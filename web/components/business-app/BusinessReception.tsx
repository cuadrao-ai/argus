"use client";

import {useTranslation} from "react-i18next";
import ReceiptReadingPreview from "@/app/design-workspace/ReceiptReadingPreview";
import {useBusiness} from "./BusinessWorkspace";
import {BusinessEmailAddress} from "./BusinessEmailDeliveries";
import EmailSenders from "./EmailSenders";
import ReceiptReadingControl from "./ReceiptReadingControl";
import {SURFACE_CARD} from "./foundation/surfaces";
import {CHANNEL_ICON} from "./foundation/channel-icons";

const EmailIcon=CHANNEL_ICON.email;

export default function BusinessReception() {
  const {t}=useTranslation();
  const {chosen}=useBusiness();
  const localPreview=process.env.NODE_ENV === "development" && process.env.NEXT_PUBLIC_MOCK_AUTH === "true";
  return <div className="space-y-6" data-testid="business-reception">
    {/* One channel, one card: its icon and name, then what it needs. A later channel copies this shape. */}
    <section className={SURFACE_CARD}>
      <div className="mb-4 flex items-center gap-3"><EmailIcon size={20} className="shrink-0 text-[#56635e] dark:text-white/70" aria-hidden="true"/><h2 className="font-display text-[21px] font-medium text-[#172b26] dark:text-white">{t("business.reception.email_title")}</h2></div>
      <BusinessEmailAddress key={chosen?.space_id}/>
    </section>
    <div className={SURFACE_CARD}><EmailSenders key={chosen?.space_id}/></div>
    <div className={SURFACE_CARD}>{localPreview ? <ReceiptReadingPreview key={chosen?.space_id}/> : <ReceiptReadingControl key={chosen?.space_id} variant="inline"/>}</div>
  </div>;
}
