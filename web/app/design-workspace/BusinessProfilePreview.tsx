"use client";

import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { Check, Info, Plus } from "lucide-react";
import { useTranslation } from "react-i18next";
import { BusinessContext, invoicingShown, useBusiness } from "@/components/business-app/BusinessWorkspace";
import BusinessFiscalProfile, {type FiscalProfileDraft} from "@/components/business-app/BusinessFiscalProfile";
import { useRegistryLookup } from "@/components/business-app/DgiiRegistryStatus";
import { RowActionLabel } from "@/components/business-app/foundation/RowAction";
import { SURFACE_CARD } from "@/components/business-app/foundation/surfaces";
import IdentityEditor from "@/components/identity/IdentityEditor";
import {useIdentityAppearance} from "@/components/identity/IdentityMark";
import {saveAppearance,IDENTITY_EVENT,DEFAULT_APPEARANCE} from "@/lib/identity-appearance";
import { BusinessMark } from "@/components/business-app/BusinessSwitcher";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import AdaptivePanel from "@/components/ui/AdaptivePanel";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { Tooltip } from "@/components/ui/Tooltip";
import AccessRolePicker from "./AccessRolePicker";
import { invitationStorageKeys } from "./businessAccessPreviewState";
import { profileChecklist, readBusinessProfilePreview, saveBusinessProfilePreview, saveBusinessProvidedDetails, seedProfilePreview, type ProfileChecklistKey, type BusinessProvidedDetails } from "./businessProfilePreviewState";
import {canManageBusiness, quietButtonClass} from "@/components/business-app/business-ui";
import { formatBusinessName } from "@/components/business-app/business-format";
import BusinessProfileDetails from "./BusinessProfileDetails";
import WorkspaceSetupPreview from "./WorkspaceSetupPreview";
import { useBusinessProfile } from "@/components/business-app/useBusinessProfile";
import { businessAppearanceState,businessSettingsRequest,subscribeBusinessAppearance } from "@/lib/business-profile-api";
import type { FiscalProfile, FiscalProfileSaved } from "@/lib/business-dgii";
import {referenceCode} from "@/lib/failure-screen";
import {ReferenceCode} from "@/components/status/ReferenceCode";
import { SettingsColumns } from "@/components/business-app/foundation/SettingsLayout";

const changedEvent = "workspace-preview-profile-changed";
const emptyStorage = {getItem:()=>null,setItem:()=>{}};
// eslint-disable-next-line no-restricted-syntax -- The development-only profile reuses the business-scoped guide store.
const storage = () => typeof window === "undefined" ? emptyStorage : window.localStorage;
type ProfileSection = "appearance" | "identity" | "contact" | "presence" | "invoicing";
type Selection = {section:ProfileSection|null;trigger?:HTMLElement};
const checklistSection: Record<ProfileChecklistKey,ProfileSection> = {name:"identity",taxId:"identity",legalName:"identity",country:"identity",address:"contact",email:"contact",phone:"contact",website:"presence",description:"presence"};

export default function BusinessProfilePreview() {
  const {chosen} = useBusiness();
  return <BusinessProfileContent key={chosen?.space_id ?? ""} />;
}

function BusinessProfileContent() {
  const workspace = useBusiness();
  const {chosen,records,renamePreviewBusiness,reload:reloadWorkspace} = workspace;
  const {t} = useTranslation();
  const {isBelowDesktop} = useResponsiveLayout();
  const businessId = chosen?.space_id ?? "";
  const name = chosen?.name ?? "";
  const previewAppearance = useIdentityAppearance(`business:${businessId}`) ?? DEFAULT_APPEARANCE;
  const live = workspace.source.mode === "live";
  const server = useBusinessProfile(businessId,live&&Boolean(businessId),reloadWorkspace);
  const retryProfile=server.retry;
  const refuseProfile=server.refuse;
  const [fiscal,setFiscal] = useState<FiscalProfile|null>(null);
  const [fiscalFailed,setFiscalFailed] = useState(false);
  const [fiscalReference,setFiscalReference]=useState<string|null>(null);
  const fiscalRequest=useRef<AbortController|null>(null);
  const fiscalRefused=useRef(false);
  const fetchFiscal=useCallback(async<T extends FiscalProfile=FiscalProfile>(options:RequestInit={})=>{
    fiscalRequest.current?.abort();
    const controller=new AbortController();fiscalRequest.current=controller;
    try{
      const value=await businessSettingsRequest<T>("/business/fiscal-profile",{...options,signal:controller.signal});
      if(!fiscalRefused.current){setFiscal(value);setFiscalFailed(false);}
      return value;
    }catch(error){
      if(!controller.signal.aborted){
        setFiscalFailed(true);setFiscalReference(referenceCode(error));
        if(refuseProfile(error)){fiscalRefused.current=true;setFiscal(null);}
      }
      throw error;
    }
  },[refuseProfile]);
  useEffect(()=>{
    if(!live||!businessId||server.refused)return;
    void fetchFiscal().catch(()=>{});
    return()=>fiscalRequest.current?.abort();
  },[live,businessId,server.refused,fetchFiscal]);
  const appearance = previewAppearance;
  const appearanceState=useSyncExternalStore(subscribeBusinessAppearance,()=>businessAppearanceState(businessId),()=>null);
  const imagePending=live&&server.profile?.appearance.kind==="image"&&appearanceState!=="ready";
  const failureReference=server.reference??fiscalReference;
  const country = records.workspace?.country;
  const canEdit = canManageBusiness(chosen) && !(live && server.refused);
  const [footerTarget,setFooterTarget] = useState<HTMLDivElement|null>(null);
  const [selected,setSelected] = useState<ProfileSection|null>(null);
  const [fiscalDraft,setFiscalDraft] = useState<FiscalProfileDraft|null>(null);
  const [providedDraft,setProvidedDraft] = useState<BusinessProvidedDetails|null>(null);
  const [dirty,setDirty] = useState(false);
  const [pending,setPending] = useState<Selection|null>(null);
  const opener = useRef<HTMLElement|null>(null);
  useEffect(()=>{
    if(!server.refused)return;
    fiscalRefused.current=true;fiscalRequest.current?.abort();setFiscal(null);
    setSelected(null);setFiscalDraft(null);setProvidedDraft(null);setDirty(false);setPending(null);
  },[server.refused]);
  const refresh = useCallback(()=>window.dispatchEvent(new Event(changedEvent)),[]);
  const subscribe = useCallback((listener:()=>void) => {
    window.addEventListener("storage",listener);window.addEventListener(changedEvent,listener);
    return ()=>{window.removeEventListener("storage",listener);window.removeEventListener(changedEvent,listener);};
  },[]);
  useEffect(()=>{if(!live&&seedProfilePreview(storage(),businessId))refresh();},[live,businessId,refresh]);
  const snapshot = useCallback(()=>live?"":storage().getItem(invitationStorageKeys(businessId).guide) ?? "",[businessId,live]);
  const raw = useSyncExternalStore(subscribe,snapshot,()=>"");
  const previewProfile = useMemo(()=>{void raw;return readBusinessProfilePreview(live?emptyStorage:storage(),businessId,name,country);},[raw,businessId,name,country,live]);
  // The legal name has one owner, the server's fiscal profile; the local preview has none.
  const legalName = fiscal?.legal_name?.value ?? null;
  const {lookup:registryLookup,retry:retryRegistry} = useRegistryLookup(live && fiscal?.can_edit && !legalName ? fiscal.tax_id : null);
  const profile = live && server.profile ? {...previewProfile,name:server.profile.name??"",country:server.profile.country,taxId:fiscal?.tax_id??null,legalName,providedDetails:server.profile.details,checklist:profileChecklist({name:server.profile.name??"",country:server.profile.country,taxId:fiscal?.tax_id??null,legalName},server.profile.details,registryLookup?.status === "done" ? registryLookup.answer : null)} : previewProfile;
  const title = formatBusinessName(profile.name,t("business.overview.title","My business"));
  const taxType = profile.taxId?.type;
  const taxValue = profile.taxId?.value;
  const {lookupRegistry,saveLegalName}=workspace.source;
  const localSource = useMemo(()=>({...workspace.source,
    fiscalProfile:async()=>live ? fetchFiscal() : ({name:profile.name,tax_id:taxType && taxValue ? {type:taxType,value:taxValue} : null,legal_name:null,can_edit:canEdit}),
    saveFiscalProfile:async(input:Parameters<typeof saveBusinessProfilePreview>[2],key:string)=>{
      if(!canEdit) throw new Error("permission_denied");
      if(live){const next=await fetchFiscal<FiscalProfileSaved>({method:"PATCH",headers:{"Idempotency-Key":key},body:JSON.stringify(input)});reloadWorkspace();retryProfile();return next;}
      saveBusinessProfilePreview(storage(),businessId,input);
      renamePreviewBusiness?.(input.name);
      refresh();
      return {name:input.name,tax_id:input.tax_id,legal_name:null,can_edit:canEdit,retyped_drafts:0};
    },
    // The registry check and the confirmed legal name are the server's; the local preview has neither.
    lookupRegistry:live ? lookupRegistry : undefined,
    saveLegalName:live && saveLegalName ? async(input:Parameters<typeof saveLegalName>[0],key:string)=>{const next=await saveLegalName(input,key);setFiscal(next);return next;} : undefined,
  }),[workspace.source,lookupRegistry,saveLegalName,reloadWorkspace,retryProfile,profile.name,taxType,taxValue,canEdit,businessId,renamePreviewBusiness,refresh,live,fetchFiscal]);
  const formContext = useMemo(()=>({...workspace,source:localSource,reload:()=>{}}),[workspace,localSource]);
  const countryLabel = profile.country ? t(`workspace_setup_preview.country_${profile.country.toLowerCase()}`,{defaultValue:profile.country}) : null;
  const labels: Record<ProfileChecklistKey,string> = {
    name:t("workspace_setup_preview.business_name"),taxId:t("business.settings.profile_checklist_tax_id"),legalName:t("workspace_setup_preview.legal_name"),country:t("workspace_setup_preview.operating_country"),address:t("business.settings.profile_address"),email:t("business.settings.profile_email"),phone:t("business.settings.profile_phone"),website:t("business.settings.profile_website"),description:t("business.settings.profile_description"),
  };
  const details = profile.providedDetails;
  const sections: {key:ProfileSection;title:string;summary:string}[] = [
    {key:"identity",title:t("business.settings.profile_identity_title"),summary:[profile.taxId ? `${t(`business.dgii.tax_id_${profile.taxId.type}`)} ${profile.taxId.value}` : t("business.settings.profile_identity_empty"),profile.legalName].filter(Boolean).join(" · ")},
    {key:"contact",title:t("business.settings.profile_contact_title"),summary:[details.address,details.email || details.phone].filter(Boolean).join(" · ") || t("business.settings.profile_contact_empty")},
    {key:"presence",title:t("business.settings.profile_presence_title"),summary:[details.description,details.website].filter(Boolean).join(" · ") || t("business.settings.profile_presence_empty")},
  ];
  if(!live && invoicingShown(workspace.invoicing))sections.push({key:"invoicing",title:t("workspace_setup_preview.invoice_title"),summary:t(`workspace_setup_preview.invoice_${profile.invoice.status.replaceAll("-","_")}`)});
  const applySelection = ({section,trigger}:Selection)=>{
    if(trigger) opener.current = trigger;
    if(selected === "identity" && live && !legalName)retryRegistry();
    setFiscalDraft(null);setProvidedDraft(null);setDirty(false);setSelected(section);setPending(null);
    refresh();
    if(section === null) requestAnimationFrame(()=>{
      const checklistKey = opener.current?.dataset.profileChecklist;
      const target = checklistKey ? document.querySelector<HTMLElement>(`[data-profile-checklist="${checklistKey}"]`) : opener.current;
      target?.focus();
    });
  };
  const select = (next:Selection)=>{
    if(next.section === selected)return;
    if(dirty)setPending(next);else applySelection(next);
  };
  const close = ()=>select({section:null});
  const hasEditableForm = canEdit && (selected === "identity" || selected === "contact" || selected === "presence");
  const businessContext = selected !== "invoicing" ? <>{t("workspace_setup_preview.for_business")} <strong className="font-semibold text-[#152d26] dark:text-white">{title}</strong></> : undefined;
  const selectedTitle = selected === "appearance" ? t("identity.change_image") : sections.find(section=>section.key === selected)?.title ?? "";
  const basics = profile.checklist.filter(item=>item.section === "basic");
  const basicsComplete = basics.every(item=>item.complete);
  const factsReady = !live || Boolean(server.profile && fiscal && registryLookup?.status !== "checking");
  const [checklistVisit,setChecklistVisit] = useState<"unseen"|"incomplete"|"done">("unseen");
  if(factsReady && !basicsComplete && checklistVisit === "unseen")setChecklistVisit("incomplete");
  if(factsReady && basicsComplete && checklistVisit === "incomplete")setChecklistVisit("done");
  const done = basicsComplete && checklistVisit === "done";
  const showChecklist = (factsReady || checklistVisit !== "unseen") && !selected && (!basicsComplete || done);
  const checklistHeading = t(done ? "business.settings.profile_checklist_done_placeholder" : "business.settings.profile_finish");
  const checklistHelp: Partial<Record<ProfileChecklistKey,string>> = {
    taxId:t("business.settings.profile_checklist_tax_help_placeholder"),
    legalName:t("business.settings.profile_checklist_legal_help_placeholder"),
  };
  const checklistRows = (section:"basic"|"additional")=><ul className="mt-3">{profile.checklist.filter(item=>item.section===section).map(item=><li key={item.key} className="flex items-center gap-1">
    <button type="button" data-profile-checklist={item.key} onClick={event=>select({section:checklistSection[item.key],trigger:event.currentTarget})} className={`flex min-h-11 min-w-0 flex-1 items-center gap-3 rounded-item text-left focus-visible:outline-2 focus-visible:outline-offset-2 ${section === "basic" ? "text-[16px]" : "text-[15px] text-[#56635e] dark:text-white/70"}`}>
      <span aria-hidden="true" className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full ${item.complete ? "bg-[#2f5a49] text-white dark:bg-[#8fcbb0] dark:text-[#13211c]" : section === "additional" ? "text-[#56635e] dark:text-white/55" : "border border-black/25 dark:border-white/35"}`}>{item.complete ? <Check className="h-3 w-3"/> : section === "additional" ? <Plus className="h-4 w-4"/> : null}</span>
      <span className={item.complete ? "text-[#56635e] dark:text-white/60" : ""}>{labels[item.key]}{section === "basic" || item.complete ? <span className="sr-only"> · {t(item.complete ? "business.settings.profile_saved" : "business.settings.profile_pending")}</span> : null}</span>
    </button>
    {checklistHelp[item.key] ? <Tooltip content={checklistHelp[item.key]!} side="top"><button type="button" aria-label={t("business.settings.profile_checklist_help_placeholder",{field:labels[item.key]})} className="-mr-3 flex h-11 w-11 shrink-0 items-center justify-center rounded-item text-[#56635e] focus-visible:outline-2 focus-visible:outline-offset-2 dark:text-white/60"><Info aria-hidden="true" className="h-4 w-4"/></button></Tooltip> : null}
  </li>)}</ul>;
  const checklistDetails = <p className="mt-2 text-[14px] leading-relaxed text-[#56635e] dark:text-white/70">{t("business.settings.profile_finish_detail")}</p>;
  const optionalHeading = t("business.settings.profile_checklist_optional_placeholder");
  const dossier = <div key={`${businessId}:${selected}`} data-profile-dossier-content className="min-w-0">
    {selected === "appearance" ? <IdentityEditor saved={appearance} name={title} business onSave={async next=>{if(live)await server.saveAppearance(next);else{saveAppearance(storage(),`business:${businessId}`,next);window.dispatchEvent(new Event(IDENTITY_EVENT));}applySelection({section:null});}}/> : selected === "identity" ? <>
      <div data-profile-identity><BusinessContext.Provider value={formContext}><BusinessFiscalProfile footerTarget={footerTarget} initialDraft={fiscalDraft} onDraftChange={setFiscalDraft} onDirtyChange={setDirty} renderTaxIdControl={props=><AccessRolePicker {...props} showDetail={false} options={(["rnc","cedula"] as const).map(type=>({value:type,label:t(`business.dgii.tax_id_${type}`),description:t(`business.dgii.tax_id_hint_${type}`)}))} onChange={value=>props.onChange(value as "rnc"|"cedula")} />} /></BusinessContext.Provider></div>
      <dl className="mt-5 space-y-5 text-[16px]">
        {live && canEdit ? null : <div><dt className="mb-1 text-[14px] text-[#56635e] dark:text-white/70">{t("workspace_setup_preview.legal_name")}</dt><dd>{profile.legalName || t("business.settings.profile_unverified")}</dd></div>}
        {countryLabel ? <div><dt className="mb-1 text-[14px] text-[#56635e] dark:text-white/70">{t("workspace_setup_preview.operating_country")}</dt><dd>{countryLabel}</dd></div> : null}
      </dl>
    </> : selected === "contact" || selected === "presence" ? <BusinessProfileDetails footerTarget={footerTarget} initialDraft={providedDraft} onDraftChange={setProvidedDraft} group={selected} saved={details} canEdit={canEdit} onDirtyChange={setDirty} onSave={async next=>{if(live){const fields=selected==="presence"?["website","description"] as const:["address","province","municipality","email","phone"] as const;const saved=await server.save({details:Object.fromEntries(fields.map(field=>[field,next[field]]))});return saved.details;}const saved=saveBusinessProvidedDetails(storage(),businessId,next);refresh();return saved;}} /> : selected === "invoicing" && !live ? canEdit ? <WorkspaceSetupPreview profileInvoicing embedded onProfileChange={refresh} onClose={close} /> : <p className="text-[16px]">{sections.find(section=>section.key === "invoicing")?.summary}</p> : null}
  </div>;
  if(live && (server.refused || !server.profile || !fiscal))return <div className={SURFACE_CARD}>{server.failed||fiscalFailed?<><p role="alert">{t(server.refused?"business.lifecycle.errors.business_unavailable":"business.empty.overview_error")} {failureReference?<ReferenceCode reference={failureReference}/>:null}</p>{!server.refused?<button type="button" className={quietButtonClass} onClick={()=>{server.retry();setFiscalFailed(false);void fetchFiscal().catch(()=>{});}}>{t("common.retry")}</button>:null}</>:<div aria-busy="true" className="h-40 animate-pulse rounded-item bg-black/5"/>}</div>;
  return <>
    <span role="status" aria-atomic="true" className="sr-only">{checklistVisit === "done" ? t("business.settings.profile_checklist_done_placeholder") : ""}</span>
    <style>{`[data-profile-identity] form{max-width:none}[data-profile-identity] form>div.grid{grid-template-columns:minmax(0,1fr)}[data-profile-identity]>div{margin-top:0}.profile-section-row{display:flex;width:100%;min-width:0;align-items:center;gap:16px;padding:20px 12px;text-align:left;border-radius:8px}.profile-section-row:hover,.profile-section-row[aria-expanded=true]{background:rgba(0,0,0,.04)}.dark .profile-section-row:hover,.dark .profile-section-row[aria-expanded=true]{background:rgba(255,255,255,.06)}.profile-section-copy{min-width:0;flex:1}.profile-section-summary{display:block;overflow-wrap:anywhere;line-height:1.5;margin-top:5px}[data-profile-dossier-content] iframe{max-width:100%}@keyframes profile-done{from{opacity:0}to{opacity:1}}.profile-done{animation:profile-done 150ms ease-out}@media(prefers-reduced-motion:reduce){.profile-done{animation:none}}
    `}</style>
    {/* Perfil keeps the same 40rem main card as Acceso and Recepción; its checklist sits beside it only when the canvas has room. */}
    <div data-testid="business-profile-preview">
      <SettingsColumns
        main={<>
        <section className={SURFACE_CARD} aria-label={t("business.settings.profile_overview")}>
          <div className="mb-3 flex flex-col items-start gap-3"><BusinessMark businessId={businessId} name={title}/><div className="min-w-0"><h2 className="font-display break-words text-[21px] font-medium">{title}</h2>{countryLabel ? <p className="mt-1 text-[14px] text-[#56635e] dark:text-white/70">{countryLabel}</p> : null}{canEdit?<><button type="button" className={`${quietButtonClass} -ml-1`} disabled={imagePending&&appearanceState!=="failed"} aria-busy={imagePending&&appearanceState!=="failed"?true:undefined} onClick={event=>{if(imagePending)retryProfile();else select({section:"appearance",trigger:event.currentTarget});}}>{t(imagePending&&appearanceState==="failed"?"common.retry":"identity.change_image")}</button>{imagePending?<p role={appearanceState==="failed"?"alert":"status"} className="text-[14px] text-[#56635e] dark:text-white/70">{t(appearanceState==="failed"?"common.error_occurred":"common.loading")}</p>:null}</>:null}</div></div>
          <div className="-mx-3 divide-y divide-black/10 dark:divide-white/10">{sections.map(section=><button key={section.key} type="button" className="profile-section-row group focus-visible:outline-2 focus-visible:outline-offset-2" aria-expanded={selected === section.key} aria-controls={selected === section.key ? "profile-section-dossier" : undefined} onClick={event=>select({section:section.key,trigger:event.currentTarget})}>
            <span className="profile-section-copy"><span className="text-[16px] font-medium">{section.title}</span><span className="profile-section-summary text-[14px] text-[#56635e] dark:text-white/70">{section.summary}</span></span><RowActionLabel>{t("business.reception_preview.placeholder.open")}</RowActionLabel>
          </button>)}</div>
        </section>
        </>}
        aside={showChecklist ? <aside className="rounded-surface border border-[#DCE0DA] bg-[#FFFEFA] p-2 dark:border-white/10 dark:bg-[#1f2225]" aria-labelledby="profile-next-title">
        <div className="rounded-item bg-black/5 p-4 dark:bg-white/5"><div key={done ? "done" : "incomplete"} className={`flex items-center gap-2.5 ${done ? "profile-done" : ""}`}>{done ? <span aria-hidden="true" className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[#2f5a49] text-white dark:bg-[#8fcbb0] dark:text-[#13211c]"><Check className="h-3.5 w-3.5"/></span> : null}<h2 id="profile-next-title" className="font-display text-[21px] font-medium">{checklistHeading}</h2></div>{checklistDetails}{checklistRows("basic")}</div>
        <div className="px-4 pb-3 pt-5"><h3 className="text-[16px] font-medium">{optionalHeading}</h3>{checklistRows("additional")}</div>
      </aside> : undefined}
        compact={showChecklist && !done ? { label: checklistHeading, detail: t("business.settings.profile_progress", { done: basics.filter(item => item.complete).length, total: basics.length }), content: <>{checklistDetails}{checklistRows("basic")}<h3 className="mt-4 text-[16px] font-medium">{optionalHeading}</h3>{checklistRows("additional")}</> } : undefined}
      />
    </div>
    {selected ? <AdaptivePanel title={selectedTitle} summary={businessContext} headerSize="large" modal={false} width="lg" onClose={close} onBack={isBelowDesktop && selected !== "appearance" ? close : undefined} backLabel={t("business.settings.profile_overview")} closeLabel={t("common.close")} snaps={["full"]} initialSnap="full" returnFocusRef={opener}><div id="profile-section-dossier" style={{padding:isBelowDesktop ? undefined : 20}}>{dossier}{hasEditableForm ? <div ref={setFooterTarget} data-footer-slot="" className="mt-6 border-t border-[#DCE0DA] pt-4 empty:hidden dark:border-white/10" /> : null}</div></AdaptivePanel> : null}
    <ConfirmDialog isOpen={pending !== null} title={t("business.settings.profile_discard_title")} description={t("business.settings.profile_discard_detail")} confirmLabel={t("business.settings.profile_discard")} cancelLabel={t("business.settings.profile_keep_editing")} onCancel={()=>setPending(null)} onConfirm={()=>{if(pending)applySelection(pending);}} />
  </>;
}
