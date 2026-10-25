"use client";

import {useEffect,useId,useState} from "react";
import {useTranslation} from "react-i18next";
import {ErrorSummary,FormField,useFieldChecks,type FieldRules} from "@/components/ui/FormField";
import {secondaryButtonClass} from "@/components/business-app/business-ui";
import {normalizeBusinessProvidedDetails,providedDetailFields,providedDetailLimits,validateBusinessProvidedDetails,type BusinessProvidedDetails,type ProvidedDetailField} from "./businessProfilePreviewState";

export default function BusinessProfileDetails({saved,canEdit,onSave,group="all",onDirtyChange,initialDraft,onDraftChange}:{saved:BusinessProvidedDetails;canEdit:boolean;onSave:(details:BusinessProvidedDetails)=>BusinessProvidedDetails;group?:"all"|"contact"|"presence";onDirtyChange?:(dirty:boolean)=>void;initialDraft?:BusinessProvidedDetails|null;onDraftChange?:(draft:BusinessProvidedDetails)=>void}) {
  const {t} = useTranslation();
  const [draft,setDraft] = useState(initialDraft ?? saved);
  useEffect(()=>{onDraftChange?.(draft);},[draft,onDraftChange]);
  const [feedback,setFeedback] = useState<"saved"|"failed"|null>(null);
  const id = useId();
  const visibleFields = providedDetailFields.filter(field=>group === "all" || (group === "presence" ? field === "website" || field === "description" : field !== "website" && field !== "description"));
  const errors = validateBusinessProvidedDetails(normalizeBusinessProvidedDetails(draft));
  const message = (field:ProvidedDetailField) => errors[field] ? t(`business.settings.profile_error_${errors[field]}`,{count:providedDetailLimits[field]}) : null;
  const rules = Object.fromEntries(providedDetailFields.map(field=>[field,()=>visibleFields.includes(field) ? message(field) : null])) as FieldRules<ProvidedDetailField>;
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
      value={draft[field]} disabled={!canEdit}
      type={field === "email" ? "email" : field === "website" ? "url" : field === "phone" ? "tel" : "text"}
      autoComplete={field === "email" ? "email" : field === "website" ? "url" : field === "phone" ? "tel" : field === "address" ? "street-address" : field === "province" ? "address-level1" : field === "municipality" ? "address-level2" : "off"}
      autoCapitalize={hasFormatCheck ? "none" : undefined} spellCheck={hasFormatCheck ? false : undefined}
      maxLength={providedDetailLimits[field]} error={checks.errorOf(field)} success={success} reserveMessages={reserveMessages}
      onBlur={()=>checks.blur(field)} onChange={event=>{setDraft(current=>({...current,[field]:event.target.value}));setFeedback(null);}} />;
  });
  return <section aria-label={t(group === "presence" ? "business.settings.profile_presence_title" : "business.settings.profile_contact_title")}>
    <p className="mb-5 mt-1 text-[14px] text-[#56635e] dark:text-white/70">{t("business.settings.profile_details_hint")}</p>
    <form noValidate className="space-y-4" onSubmit={event=>{
      event.preventDefault();if(!canEdit)return;
      if(!checks.submit())return;
      try { const next=onSave({...saved,...Object.fromEntries(visibleFields.map(field=>[field,draft[field]]))});setDraft(next);checks.reset();setFeedback("saved"); }
      catch { setFeedback("failed"); }
    }}>
      <ErrorSummary key={checks.attempt} title={t("common.form_summary")} items={checks.summary.map(field=>({id:`${id}-${field}`,label:t(`business.settings.profile_${field}`)}))} />
      {group !== "presence" ? <>{fields(["address"])}<div className="grid gap-4">{fields(["province","municipality"])}</div><div className="grid gap-4">{fields(["email","phone"])}</div></> : null}
      {group !== "contact" ? fields(["website","description"]) : null}
      {canEdit ? <div className="flex min-h-11 flex-wrap items-center gap-3"><button type="submit" className={secondaryButtonClass} disabled={unchanged}>{t("business.dgii.save_profile")}</button><p role={feedback === "failed" ? "alert" : "status"} className={`text-[14px] ${feedback === "failed" ? "text-[#9e2f39] dark:text-[#ec9aa0]" : "text-[#56635e] dark:text-white/70"}`}>{feedback ? t(`business.settings.profile_details_${feedback}`) : ""}</p></div> : null}
    </form>
  </section>;
}
