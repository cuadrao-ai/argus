"use client";

import {useState} from "react";
import {ChevronRight,Mail,MessageCircle} from "lucide-react";
import {useTranslation} from "react-i18next";
import ReceiptReadingPreview from "@/app/design-workspace/ReceiptReadingPreview";
import WorkspaceSetupPreview from "@/app/design-workspace/WorkspaceSetupPreview";
import {receptionPreviewEvent,useReceptionPreview} from "@/app/design-workspace/BusinessEmailAliasPreview";
import {useBusiness} from "./BusinessWorkspace";
import {BusinessEmailAddress,EmailHistory} from "./BusinessEmailDeliveries";
import ReceiptReadingControl from "./ReceiptReadingControl";
import {SURFACE_CARD} from "./foundation/surfaces";
import {quietButtonClass} from "./business-ui";

export default function BusinessReception() {
  const {t}=useTranslation();
  const {chosen}=useBusiness();
  const localPreview=process.env.NODE_ENV === "development" && process.env.NEXT_PUBLIC_MOCK_AUTH === "true";
  const [section,setSection]=useState<"history"|"whatsapp"|null>(null);
  const connection=useReceptionPreview(chosen?.space_id ?? "");
  return <div className="space-y-5" data-testid="business-reception">
    <div className={SURFACE_CARD}>
      <div className="mb-4 flex items-center gap-3"><Mail className="h-5 w-5 text-[#56635e] dark:text-white/70" aria-hidden="true"/><h2 className="text-[16px] font-medium text-[#172b26] dark:text-white">{t("business.reception.email_title")}</h2></div>
      <BusinessEmailAddress key={chosen?.space_id}/>
      <div className="mt-2"><button type="button" className={quietButtonClass} onClick={()=>setSection("history")} aria-expanded={section === "history"}>{t("business.reception.history_link")}<ChevronRight className="h-4 w-4" aria-hidden="true"/></button></div>
      {localPreview ? <button type="button" onClick={()=>setSection("whatsapp")} aria-expanded={section === "whatsapp"} className="mt-4 flex min-h-16 w-full items-center gap-3 border-t border-[#DCE0DA] pt-4 text-left text-[#172b26] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f5a49] dark:border-white/10 dark:text-white">
        <MessageCircle className="h-5 w-5 shrink-0 text-[#56635e] dark:text-white/70" aria-hidden="true"/>
        <span className="min-w-0 flex-1"><span className="block text-[16px] font-medium">WhatsApp</span><span className="mt-1 block text-[14px] text-[#56635e] dark:text-white/70">{connection.linked ? t("business.reception.whatsapp_connected",{last4:connection.last4 ?? "",business:chosen?.name}) : t("business.reception.whatsapp_connect",{business:chosen?.name})}</span></span><ChevronRight className="h-4 w-4 shrink-0" aria-hidden="true"/>
      </button> : null}
    </div>
    <div className={SURFACE_CARD}>{localPreview ? <ReceiptReadingPreview key={chosen?.space_id}/> : <ReceiptReadingControl key={chosen?.space_id} variant="inline"/>}</div>
    {section === "history" ? <EmailHistory onClose={()=>setSection(null)}/> : null}
    {section === "whatsapp" ? <WorkspaceSetupPreview reception="whatsapp" onProfileChange={()=>window.dispatchEvent(new Event(receptionPreviewEvent))} onClose={()=>{setSection(null);window.dispatchEvent(new Event(receptionPreviewEvent));}}/> : null}
  </div>;
}
