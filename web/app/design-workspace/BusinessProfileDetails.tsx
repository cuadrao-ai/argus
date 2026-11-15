"use client";

import {useCallback,useEffect,useId,useRef,useState} from "react";
import {createPortal} from "react-dom";
import {useTranslation} from "react-i18next";
import {ErrorSummary,FormField} from "@/components/ui/FormField";
import {primaryButtonClass,secondaryButtonClass} from "@/components/business-app/business-ui";
import {refusedFields} from "@/lib/business-profile-api";
import {normalizeBusinessProvidedDetails,providedDetailFields,providedDetailLimits,type BusinessProvidedDetails,type ProvidedDetailField} from "./businessProfilePreviewState";

/** What the server said about one typed value. The form holds no format rule of its own. */
type Answer = {value:string;code:string|null};
type Refused = Partial<Record<ProvidedDetailField,string>>;
const errorCopy: Record<string,string> = {invalid_business_email:"profile_error_email",invalid_business_website:"profile_error_website",invalid_business_phone_empty:"profile_error_phone_empty",invalid_business_phone_length:"profile_error_phone_length",invalid_business_phone_format:"profile_error_phone_format",invalid_business_phone_region:"profile_error_phone_region",string_too_long:"profile_error_length"};
const formatCopy: Partial<Record<ProvidedDetailField,string>> = {email:"profile_format_email",website:"profile_format_website",phone:"profile_format_phone_placeholder"};
const FIXING_DELAY_MS = 300;

/** Asks the server about one field at a time. A newer question for a field drops the older one. */
function useServerAnswers(onCheck:((typed:Partial<BusinessProvidedDetails>,signal:AbortSignal)=>Promise<Refused>)|undefined) {
  const [answers,setAnswers] = useState<Partial<Record<ProvidedDetailField,Answer>>>({});
  const asking = useRef<Partial<Record<ProvidedDetailField,{stop:AbortController;timer:ReturnType<typeof setTimeout>}>>>({});
  const stop = useCallback(()=>{for(const ask of Object.values(asking.current)){ask.stop.abort();clearTimeout(ask.timer);}},[]);
  useEffect(()=>stop,[stop]);
  const ask = (field:ProvidedDetailField,value:string,delay=0) => {
    if(!onCheck)return;
    const previous=asking.current[field];previous?.stop.abort();clearTimeout(previous?.timer);
    const controller=new AbortController();
    const timer=setTimeout(()=>{
      // No answer shows nothing here; Save asks the same rules again.
      void onCheck({[field]:value},controller.signal).then(refused=>{if(!controller.signal.aborted)setAnswers(was=>({...was,[field]:{value,code:refused[field]??null}}));},()=>{});
    },delay);
    asking.current[field]={stop:controller,timer};
  };
  return {answers,setAnswers,ask,stop};
}

export default function BusinessProfileDetails({saved,canEdit,onSave,onCheck,onSaved,group="all",onDirtyChange,initialDraft,onDraftChange,footerTarget}:{saved:BusinessProvidedDetails;canEdit:boolean;onSave:(details:BusinessProvidedDetails)=>BusinessProvidedDetails|Promise<BusinessProvidedDetails>;onCheck?:(typed:Partial<BusinessProvidedDetails>,signal:AbortSignal)=>Promise<Refused>;onSaved?:()=>void;group?:"all"|"contact"|"presence";onDirtyChange?:(dirty:boolean)=>void;initialDraft?:BusinessProvidedDetails|null;onDraftChange?:(draft:BusinessProvidedDetails)=>void;footerTarget?:HTMLElement|null}) {
  const {t} = useTranslation();
  const [draft,setDraft] = useState(initialDraft ?? saved);
  useEffect(()=>{onDraftChange?.(draft);},[draft,onDraftChange]);
  const [feedback,setFeedback] = useState<"saved"|"failed"|"conflict"|null>(null);
  const [saving,setSaving] = useState(false);
  const {answers,setAnswers,ask,stop:stopAsking} = useServerAnswers(onCheck);
  const [attempt,setAttempt] = useState(0);
  const form = useRef<HTMLFormElement>(null);
  const mounted = useRef(true);
  useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;};},[]);
  // The summary takes focus when it opens, so the first refused field takes it on the next frame.
  useEffect(()=>{
    if(!attempt)return;
    const frame=requestAnimationFrame(()=>form.current?.querySelector<HTMLElement>('[aria-invalid="true"]')?.focus());
    return()=>cancelAnimationFrame(frame);
  },[attempt]);
  const id = useId();
  const visibleFields = providedDetailFields.filter(field=>group === "all" || (group === "presence" ? field === "website" || field === "description" : field !== "website" && field !== "description"));
  const errorOf = (field:ProvidedDetailField) => {
    const code=answers[field]?.code;
    return code ? t(`business.settings.${errorCopy[code] ?? "profile_details_failed"}`,{count:providedDetailLimits[field]}) : null;
  };
  const refusedNow = attempt > 0 ? visibleFields.filter(field=>answers[field]?.code) : [];
  const normalized = normalizeBusinessProvidedDetails(draft);
  const unchanged = visibleFields.every(field=>normalized[field] === saved[field]);
  useEffect(()=>{onDirtyChange?.(!unchanged);},[unchanged,onDirtyChange]);
  const fields = (names:ProvidedDetailField[]) => names.map(field=>{
    const format = formatCopy[field];
    const answer = answers[field];
    const success = format && draft[field] && answer && !answer.code && answer.value === draft[field] ? t(`business.settings.${format}`) : undefined;
    const reserveMessages = format ? [...Object.keys(errorCopy).filter(code=>code.startsWith(`invalid_business_${field}`)).map(code=>t(`business.settings.${errorCopy[code]}`)),t("business.settings.profile_error_length",{count:providedDetailLimits[field]}),t(`business.settings.${format}`)] : [];
    return <FormField key={field} id={`${id}-${field}`} name={`profile-${field}`}
      label={t(`business.settings.profile_${field}`)} placeholder={t(`business.settings.profile_placeholder_${field}`)}
      value={draft[field]} disabled={!canEdit || saving}
      type={field === "email" ? "email" : field === "website" ? "url" : field === "phone" ? "tel" : "text"}
      autoComplete={field === "email" ? "email" : field === "website" ? "url" : field === "phone" ? "tel" : field === "address" ? "street-address" : field === "province" ? "address-level1" : field === "municipality" ? "address-level2" : "off"}
      autoCapitalize={format ? "none" : undefined} spellCheck={format ? false : undefined}
      maxLength={providedDetailLimits[field]} error={errorOf(field)} success={success} reserveMessages={reserveMessages}
      onBlur={()=>{if(draft[field] !== saved[field] && draft[field] !== answer?.value)ask(field,draft[field]);}}
      onChange={event=>{const value=event.target.value;setDraft(current=>({...current,[field]:value}));setFeedback(null);if(answer?.code)ask(field,value,FIXING_DELAY_MS);}} />;
  });
  const saveButton = <button style={footerTarget === undefined ? undefined : {borderRadius:"var(--radius-item)"}} type="submit" form={`${id}-form`} className={footerTarget === undefined ? secondaryButtonClass : `${primaryButtonClass} h-12 w-full`} disabled={unchanged || saving}>{t(footerTarget === undefined ? "business.dgii.save_profile" : "business.settings.profile_save_changes")}</button>;
  const status = <p role={feedback === "failed"||feedback === "conflict" ? "alert" : "status"} className={`${feedback ? "" : "sr-only"} text-[14px] ${feedback === "failed"||feedback === "conflict" ? "text-[#9e2f39] dark:text-[#ec9aa0]" : "text-[#56635e] dark:text-white/70"}`}>{feedback ? t(feedback==="conflict"?"identity.business_profile_conflict":`business.settings.profile_details_${feedback}`) : ""}</p>;
  const actions = footerTarget === undefined ? <div className="flex min-h-11 flex-wrap items-center gap-3">{saveButton}{status}</div> : <div className="flex flex-col gap-2">{status}{saveButton}</div>;
  return <section aria-label={t(group === "presence" ? "business.settings.profile_presence_title" : "business.settings.profile_contact_title")}>
    {footerTarget === undefined ? <p className="mb-5 mt-1 text-[14px] text-[#56635e] dark:text-white/70">{t("business.settings.profile_details_hint")}</p> : null}
    <form ref={form} id={`${id}-form`} noValidate className="space-y-4" onSubmit={async event=>{
      event.preventDefault();if(!canEdit || saving)return;
      setSaving(true);setFeedback(null);stopAsking();
      try {
        const next=await onSave({...saved,...Object.fromEntries(visibleFields.map(field=>[field,draft[field]]))});
        if(!mounted.current)return;
        setDraft(next);setAnswers({});setAttempt(0);
        if(onSaved)onSaved();else setFeedback("saved");
      }
      catch(error) {
        if(!mounted.current)return;
        const refused=refusedFields(error),refusedHere=visibleFields.filter(field=>refused[field]);
        if(refusedHere.length){setAnswers(was=>({...was,...Object.fromEntries(refusedHere.map(field=>[field,{value:draft[field],code:refused[field]}]))}));setAttempt(count=>count+1);}
        else setFeedback(error&&typeof error==="object"&&"status" in error&&error.status===409?"conflict":"failed");
      }
      finally {if(mounted.current)setSaving(false);}
    }}>
      <ErrorSummary key={attempt} title={t("common.form_summary")} items={refusedNow.map(field=>({id:`${id}-${field}`,label:t(`business.settings.profile_${field}`)}))} />
      {group !== "presence" ? <>{fields(["address"])}<div className="grid gap-4">{fields(["province","municipality"])}</div><div className="grid gap-4">{fields(["email","phone"])}</div></> : null}
      {group !== "contact" ? fields(["website","description"]) : null}
      {canEdit ? footerTarget === undefined ? actions : footerTarget ? createPortal(actions,footerTarget) : null : null}
    </form>
  </section>;
}
