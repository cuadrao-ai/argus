"use client";

import {useEffect,useState} from "react";
import {useTranslation} from "react-i18next";
import {InlineReading} from "@/components/business-app/ReceiptReadingControl";
import {useBusiness} from "@/components/business-app/BusinessWorkspace";
import {useBusinessConsent} from "@/components/business-app/business-consent-context";
import {normalizeEnabledLanguage,resolveLanguage} from "@/lib/language-features";
import {receptionPreviewEvent,useReceptionPreview} from "./BusinessEmailAliasPreview";
import {saveReceptionReading} from "./businessReceptionPreviewState";

export default function ReceiptReadingPreview() {
  const {chosen,source}=useBusiness();
  const consent=useBusinessConsent();
  const {i18n}=useTranslation();
  const language=normalizeEnabledLanguage(i18n.resolvedLanguage ?? resolveLanguage({}));
  const businessId=chosen?.space_id ?? "";
  const preview=useReceptionPreview(businessId);
  const [failed,setFailed]=useState(false);
  const [disclosure,setDisclosure]=useState("");
  useEffect(()=>{
    const controller=new AbortController();
    source.receiptReading?.(language,controller.signal).then(reading=>setDisclosure(reading.disclosure),()=>undefined);
    return ()=>controller.abort();
  },[source,language]);
  const canChange=chosen?.role === "owner";
  return <InlineReading reading={consent.accepted && businessId ? {enabled:preview.reading,can_change:canChange,available:true,disclosure} : null} failed={failed} onChange={async enabled=>{
    if(!consent.accepted || !canChange || !businessId)return;
    setFailed(false);
    try {
      // eslint-disable-next-line no-restricted-syntax -- Development-only receipt reading uses the existing business-scoped guide store.
      saveReceptionReading(window.localStorage,businessId,enabled);
      window.dispatchEvent(new Event(receptionPreviewEvent));
    }catch(error){setFailed(true);throw error;}
  }}/>;
}
