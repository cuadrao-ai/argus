"use client";

import {useEffect,useId,useRef,useState} from "react";
import {createPortal} from "react-dom";
import {useTranslation} from "react-i18next";
import {ErrorSummary,FormField,useFieldChecks,type FieldRules} from "@/components/ui/FormField";
import {primaryButtonClass,secondaryButtonClass} from "@/components/business-app/business-ui";
import {normalizeBusinessProvidedDetails,providedDetailFields,providedDetailLimits,validateBusinessProvidedDetails,type BusinessProvidedDetails,type ProvidedDetailField} from "./businessProfilePreviewState";

export default function BusinessProfileDetails({saved,canEdit,onSave,group="all",onDirtyChange,initialDraft,onDraftChange,footerTarget}:{saved:BusinessProvidedDetails;canEdit:boolean;onSave:(details:BusinessProvidedDetails)=>BusinessProvidedDetails|Promise<BusinessProvidedDetails>;group?:"all"|"contact"|"presence";onDirtyChange?:(dirty:boolean)=>void;initialDraft?:BusinessProvidedDetails|null;onDraftChange?:(draft:BusinessProvidedDetails)=>void;footerTarget?:HTMLElement|null}) {
  const {t} = useTranslation();
  const [draft,setDraft] = useState(initialDraft ?? saved);
  useEffect(()=>{onDraftChange?.(draft);},[draft,onDraftChange]);
  const [feedback,setFeedback] = useState<"saved"|"failed"|"conflict"|null>(null);
  const [saving,setSaving] = useState(false);
  const mounted = useRef(true);
  useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;};},[]);
  const id = useId();
  const visibleFields = providedDetailFields.filter(field=>group === "all" || (group === "presence" ? field === "website" || field === "description" : field !== "website" && field !== "description"));
  const errors = validateBusinessProvidedDetails(normalizeBusinessProvidedDetails(draft));
  const message = (field:ProvidedDetailField) => errors[field] ? t(`business.settings.profile_error_${errors[field]}`,{count:providedDetailLimits[field]}) : null;
  const rules = {} as FieldRules<ProvidedDetailField>;
  for (const field of providedDetailFields) rules[field] = () => visibleFields.includes(field) ? message(field) : null;
  const checks = useFieldChecks(rules,draft);
  const normalized = normalizeBusinessProvidedDetails(draft);
  const unchanged = visibleFields.every(field=>normalized[field] === saved[field]);
  useEffect(()=>{onDirtyChange?.(!unchanged);},[unchanged,onDirtyChange]);
  const fields = (names:ProvidedDetailField[]) => names.map(field=>{
    const hasFormatCheck = field === "email" || field === "website";
    const success = hasFormatCheck && normalized[field] && checks.isValid(field) ? t(`business.settings.profile_format_${field}`) : undefined;
    const reserveMessages = hasFormatCheck ? [t(`business.settings.profile_error_${field}`),t("business.settings.profile_error_length",{count:providedDetailLimits[field]}),t(`business.settings.profile_format_${field}`)] : [];
    return <FormField key={field} id={`${id}-${field}`} name={`profile-${field}`}
      label={t(`business.settings.profile_${field}`)} placeholder={t(`business.settings.profile_placeholder_${field}`)}
      value={draft[field]} disabled={!canEdit || saving}
      type={field === "email" ? "email" : field === "website" ? "url" : field === "phone" ? "tel" : "text"}
      autoComplete={field === "email" ? "email" : field === "website" ? "url" : field === "phone" ? "tel" : field === "address" ? "street-address" : field === "province" ? "address-level1" : field === "municipality" ? "address-level2" : "off"}
      autoCapitalize={hasFormatCheck ? "none" : undefined} spellCheck={hasFormatCheck ? false : undefined}
      maxLength={providedDetailLimits[field]} error={checks.errorOf(field)} success={success} reserveMessages={reserveMessages}
      onBlur={()=>checks.blur(field)} onChange={event=>{setDraft(current=>({...current,[field]:event.target.value}));setFeedback(null);}} />;
  });
  const saveButton = <button style={footerTarget === undefined ? undefined : {borderRadius:"var(--radius-item)"}} type="submit" form={`${id}-form`} className={footerTarget === undefined ? secondaryButtonClass : `${primaryButtonClass} h-12 w-full`} disabled={unchanged || saving}>{t(footerTarget === undefined ? "business.dgii.save_profile" : "business.settings.profile_save_changes")}</button>;
  const status = <p role={feedback === "failed"||feedback === "conflict" ? "alert" : "status"} className={`${feedback ? "" : "sr-only"} text-[14px] ${feedback === "failed"||feedback === "conflict" ? "text-[#9e2f39] dark:text-[#ec9aa0]" : "text-[#56635e] dark:text-white/70"}`}>{feedback ? t(feedback==="conflict"?"identity.business_profile_conflict":`business.settings.profile_details_${feedback}`) : ""}</p>;
  const actions = footerTarget === undefined ? <div className="flex min-h-11 flex-wrap items-center gap-3">{saveButton}{status}</div> : <div className="flex flex-col gap-2">{status}{saveButton}</div>;
  return <section aria-label={t(group === "presence" ? "business.settings.profile_presence_title" : "business.settings.profile_contact_title")}>
    {footerTarget === undefined ? <p className="mb-5 mt-1 text-[14px] text-[#56635e] dark:text-white/70">{t("business.settings.profile_details_hint")}</p> : null}
    <form id={`${id}-form`} noValidate className="space-y-4" onSubmit={async event=>{
      event.preventDefault();if(!canEdit || saving)return;
      if(!checks.submit())return;
      setSaving(true);setFeedback(null);
      try { const next=await onSave({...saved,...Object.fromEntries(visibleFields.map(field=>[field,draft[field]]))});if(mounted.current){setDraft(next);checks.reset();setFeedback("saved");} }
      catch(error) { if(mounted.current)setFeedback(error&&typeof error==="object"&&"status" in error&&error.status===409?"conflict":"failed"); }
      finally {if(mounted.current)setSaving(false);}
    }}>
      <ErrorSummary key={checks.attempt} title={t("common.form_summary")} items={checks.summary.map(field=>({id:`${id}-${field}`,label:t(`business.settings.profile_${field}`)}))} />
      {group !== "presence" ? <>{fields(["address"])}<div className="grid gap-4">{fields(["province","municipality"])}</div><div className="grid gap-4">{fields(["email","phone"])}</div></> : null}
      {group !== "contact" ? fields(["website","description"]) : null}
      {canEdit ? footerTarget === undefined ? actions : footerTarget ? createPortal(actions,footerTarget) : null : null}
    </form>
  </section>;
}
