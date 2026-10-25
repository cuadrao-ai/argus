"use client";

import {useEffect,useId,useState} from "react";
import {useTranslation} from "react-i18next";
import {FormField,useFieldChecks} from "@/components/ui/FormField";
import {primaryButtonClass,quietButtonClass} from "@/components/business-app/business-ui";
import {aliasError,readReceptionPreview,saveReceptionAlias} from "./businessReceptionPreviewState";

const unavailableStorage = {length:0,key:()=>null,getItem:()=>null,setItem:()=>{throw new Error("storage_unavailable");}};
function storage() {
  // eslint-disable-next-line no-restricted-syntax -- Development-only bridge to the existing business-scoped guide store.
  try { return window.localStorage; } catch { return unavailableStorage; }
}

export const receptionPreviewEvent = "cuadrao-reception-preview-change";
export function useReceptionPreview(businessId: string) {
  const [snapshot,setSnapshot] = useState<{businessId:string;value:ReturnType<typeof readReceptionPreview>} | null>(null);
  useEffect(()=>{
    const refresh=()=>setSnapshot({businessId,value:readReceptionPreview(storage(),businessId)});
    refresh();window.addEventListener("storage",refresh);window.addEventListener(receptionPreviewEvent,refresh);
    return ()=>{window.removeEventListener("storage",refresh);window.removeEventListener(receptionPreviewEvent,refresh);};
  },[businessId]);
  return snapshot?.businessId === businessId ? snapshot.value : {address:null,linked:false,last4:null};
}
export default function BusinessEmailAliasPreview({businessId,defaultAddress,canEdit}:{businessId:string;defaultAddress:string;canEdit:boolean}) {
  const {t}=useTranslation();
  const saved=useReceptionPreview(businessId);
  const [open,setOpen]=useState(false);
  const [alias,setAlias]=useState("");
  const [failed,setFailed]=useState(false);
  const id=useId();
  const domain=defaultAddress.slice(defaultAddress.lastIndexOf("@")+1);
  const issue=()=>aliasError(storage(),businessId,alias.trim().toLowerCase(),domain);
  const checks=useFieldChecks({alias:()=>{const error=issue();return error ? t(error === "locked" ? "business.reception.alias_locked" : `workspace_setup_preview.alias_${error}`) : null;}},{alias});
  if(saved.address) return <p className="mt-2 text-[14px] text-[#56635e] dark:text-white/70">{t("business.reception.alias_locked")}</p>;
  if(!canEdit) return null;
  if(!open) return <button type="button" onClick={()=>setOpen(true)} className={`${quietButtonClass} mt-2`}>{t("business.reception.alias_customize")}</button>;
  return <form className="mt-4 space-y-3 border-t border-[#DCE0DA] pt-4 dark:border-white/10" noValidate onSubmit={event=>{
    event.preventDefault();if(!checks.submit()){document.getElementById(id)?.focus();return;}
    try{saveReceptionAlias(storage(),businessId,alias.trim().toLowerCase(),defaultAddress);window.dispatchEvent(new Event(receptionPreviewEvent));setOpen(false);}catch{setFailed(true);}
  }}>
    <FormField id={id} name="receiving-alias" label={t("workspace_setup_preview.alias_label")} placeholder={t("workspace_setup_preview.alias_example")} value={alias} required autoComplete="off" autoCapitalize="none" spellCheck={false} maxLength={32} onChange={event=>{setAlias(event.target.value);setFailed(false);}} onBlur={()=>checks.blur("alias")} error={checks.errorOf("alias")} hint={`@${domain}`} success={checks.isValid("alias") ? t("business.reception.alias_format_valid") : undefined} />
    <p className="text-[14px] leading-relaxed text-[#56635e] dark:text-white/70">{t("business.reception.alias_once")} {t("workspace_setup_preview.alias_change_note")}</p>
    {failed ? <p role="alert" className="text-[14px] text-[#9e2f39] dark:text-[#ec9aa0]">{t("workspace_setup_preview.draft_save_error")}</p> : null}
    <div className="flex flex-wrap gap-2"><button type="submit" className={primaryButtonClass}>{t("business.reception.alias_save")}</button><button type="button" className={quietButtonClass} onClick={()=>setOpen(false)}>{t("common.cancel")}</button></div>
  </form>;
}
