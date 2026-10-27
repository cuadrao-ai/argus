"use client";

import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { Check, ChevronRight } from "lucide-react";
import { useTranslation } from "react-i18next";
import { BusinessContext, useBusiness } from "@/components/business-app/BusinessWorkspace";
import BusinessFiscalProfile, {type FiscalProfileDraft} from "@/components/business-app/BusinessFiscalProfile";
import { SURFACE_CARD } from "@/components/business-app/foundation/surfaces";
import IdentityEditor from "@/components/identity/IdentityEditor";
import {useIdentityAppearance} from "@/components/identity/IdentityMark";
import {saveAppearance,IDENTITY_EVENT,DEFAULT_APPEARANCE} from "@/lib/identity-appearance";
import { BusinessMark } from "@/components/business-app/BusinessSwitcher";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import AdaptivePanel from "@/components/ui/AdaptivePanel";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import AccessRolePicker from "./AccessRolePicker";
import { invitationStorageKeys } from "./businessAccessPreviewState";
import { profileChecklist, readBusinessProfilePreview, saveBusinessProfilePreview, saveBusinessProvidedDetails, type ProfileChecklistKey, type BusinessProvidedDetails } from "./businessProfilePreviewState";
import {quietButtonClass} from "@/components/business-app/business-ui";
import BusinessProfileCard from "./BusinessProfileCard";
import BusinessProfileDetails from "./BusinessProfileDetails";
import WorkspaceSetupPreview from "./WorkspaceSetupPreview";
import { useBusinessProfile } from "@/components/business-app/useBusinessProfile";
import { businessAppearanceState,businessSettingsRequest,subscribeBusinessAppearance } from "@/lib/business-profile-api";
import type { FiscalProfile } from "@/lib/business-dgii";
import {referenceCode} from "@/lib/failure-screen";
import {ReferenceCode} from "@/components/status/ReferenceCode";

const changedEvent = "workspace-preview-profile-changed";
const emptyStorage = {getItem:()=>null,setItem:()=>{}};
// eslint-disable-next-line no-restricted-syntax -- The development-only profile reuses the business-scoped guide store.
const storage = () => typeof window === "undefined" ? emptyStorage : window.localStorage;
type ProfileSection = "appearance" | "card" | "identity" | "contact" | "presence" | "invoicing";
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
  const fetchFiscal=useCallback(async(options:RequestInit={})=>{
    fiscalRequest.current?.abort();
    const controller=new AbortController();fiscalRequest.current=controller;
    try{
      const value=await businessSettingsRequest<FiscalProfile>("/business/fiscal-profile",{...options,signal:controller.signal});
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
  const canEdit = live ? Boolean(chosen?.permissions?.includes("manage")) && !server.refused : chosen?.role === "owner";
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
  const snapshot = useCallback(()=>live?"":storage().getItem(invitationStorageKeys(businessId).guide) ?? "",[businessId,live]);
  const raw = useSyncExternalStore(subscribe,snapshot,()=>"");
  const previewProfile = useMemo(()=>{void raw;return readBusinessProfilePreview(live?emptyStorage:storage(),businessId,name,country);},[raw,businessId,name,country,live]);
  const profile = live && server.profile ? {...previewProfile,name:server.profile.name,country:server.profile.country,taxId:fiscal?.tax_id??null,legalName:null,providedDetails:server.profile.details,checklist:profileChecklist({name:server.profile.name,country:server.profile.country,taxId:fiscal?.tax_id??null,legalName:null},server.profile.details)} : previewProfile;
  const taxType = profile.taxId?.type;
  const taxValue = profile.taxId?.value;
  const localSource = useMemo(()=>({...workspace.source,
    fiscalProfile:async()=>live ? fetchFiscal() : ({name:profile.name,tax_id:taxType && taxValue ? {type:taxType,value:taxValue} : null,can_edit:canEdit}),
    saveFiscalProfile:async(input:Parameters<typeof saveBusinessProfilePreview>[2],key:string)=>{
      if(!canEdit) throw new Error("permission_denied");
      if(live){const next=await fetchFiscal({method:"PATCH",headers:{"Idempotency-Key":key},body:JSON.stringify(input)});reloadWorkspace();retryProfile();return next;}
      saveBusinessProfilePreview(storage(),businessId,input);
      renamePreviewBusiness?.(input.name);
      refresh();
      return {name:input.name,tax_id:input.tax_id,can_edit:canEdit};
    },
  }),[workspace.source,reloadWorkspace,retryProfile,profile.name,taxType,taxValue,canEdit,businessId,renamePreviewBusiness,refresh,live,fetchFiscal]);
  const formContext = useMemo(()=>({...workspace,source:localSource,reload:()=>{}}),[workspace,localSource]);
  const countryLabel = profile.country ? t(`workspace_setup_preview.country_${profile.country.toLowerCase()}`,{defaultValue:profile.country}) : null;
  const labels: Record<ProfileChecklistKey,string> = {
    name:t("workspace_setup_preview.business_name"),taxId:t("business.dgii.tax_id_type"),legalName:t("workspace_setup_preview.legal_name"),country:t("workspace_setup_preview.operating_country"),address:t("business.settings.profile_address"),email:t("business.settings.profile_email"),phone:t("business.settings.profile_phone"),website:t("business.settings.profile_website"),description:t("business.settings.profile_description"),
  };
  const details = profile.providedDetails;
  const sections: {key:ProfileSection;title:string;summary:string}[] = [
    {key:"identity",title:t("business.settings.profile_identity_title"),summary:[profile.taxId ? `${t(`business.dgii.tax_id_${profile.taxId.type}`)} ${profile.taxId.value}` : t("business.settings.profile_identity_empty"),profile.legalName].filter(Boolean).join(" · ")},
    {key:"contact",title:t("business.settings.profile_contact_title"),summary:[details.address,details.email || details.phone].filter(Boolean).join(" · ") || t("business.settings.profile_contact_empty")},
    {key:"presence",title:t("business.settings.profile_presence_title"),summary:[details.description,details.website].filter(Boolean).join(" · ") || t("business.settings.profile_presence_empty")},
  ];
  if(!live)sections.push({key:"invoicing",title:t("workspace_setup_preview.invoice_title"),summary:t(`workspace_setup_preview.invoice_${profile.invoice.status.replaceAll("-","_")}`)});
  const applySelection = ({section,trigger}:Selection)=>{
    if(trigger) opener.current = trigger;
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
  const businessContext = selected !== "card" && selected !== "invoicing" ? <>{t("workspace_setup_preview.for_business")} <strong className="font-semibold text-[#152d26] dark:text-white">{profile.name}</strong></> : undefined;
  const selectedTitle = selected === "appearance" ? t("identity.change_image") : selected === "card" ? t("business.settings.profile_overview") : sections.find(section=>section.key === selected)?.title ?? "";
  const checklistRows = (section:"basic"|"additional")=><ul className="mt-3">{profile.checklist.filter(item=>item.section===section).map(item=><li key={item.key}><button type="button" data-profile-checklist={item.key} onClick={event=>select({section:checklistSection[item.key],trigger:event.currentTarget})} className="flex min-h-11 w-full items-center gap-3 rounded-item text-left text-[16px] focus-visible:outline-2 focus-visible:outline-offset-2">
    <span aria-hidden="true" style={item.complete ? undefined : {borderColor:"currentColor",opacity:0.35}} className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full ${item.complete ? "bg-[#2f5a49] text-white dark:bg-[#8fcbb0] dark:text-[#13211c]" : "border border-black/25 dark:border-white/35"}`}>{item.complete ? <Check className="h-3 w-3"/> : null}</span>
    <span style={item.complete ? {textDecoration:"line-through"} : undefined} className={item.complete ? "text-[#56635e] dark:text-white/60" : ""}>{labels[item.key]}<span className="sr-only"> · {t(item.complete ? "business.settings.profile_saved" : "business.settings.profile_pending")}</span></span>
  </button></li>)}</ul>;
  const dossier = <div key={`${businessId}:${selected}`} data-profile-dossier-content className="min-w-0">
    {selected === "appearance" ? <IdentityEditor onBack={isBelowDesktop?close:undefined} saved={appearance} name={name} business onSave={async next=>{if(live)await server.saveAppearance(next);else{saveAppearance(storage(),`business:${businessId}`,next);window.dispatchEvent(new Event(IDENTITY_EVENT));}applySelection({section:null});}}/> : selected === "card" ? <BusinessProfileCard profile={profile} businessId={businessId} logoUrl={chosen?.logo_url} /> : selected === "identity" ? <>
      <div data-profile-identity><BusinessContext.Provider value={formContext}><BusinessFiscalProfile footerTarget={footerTarget} initialDraft={fiscalDraft} onDraftChange={setFiscalDraft} onDirtyChange={setDirty} renderTaxIdControl={props=><AccessRolePicker {...props} showDetail={false} options={(["rnc","cedula"] as const).map(type=>({value:type,label:t(`business.dgii.tax_id_${type}`),description:t(`business.dgii.tax_id_hint_${type}`)}))} onChange={value=>props.onChange(value as "rnc"|"cedula")} />} /></BusinessContext.Provider></div>
      <dl className="mt-5 space-y-5 text-[16px]">
        <div><dt className="mb-1 text-[14px] text-[#56635e] dark:text-white/70">{t("workspace_setup_preview.legal_name")}</dt><dd>{profile.legalName || t("business.settings.profile_unverified")}</dd></div>
        {countryLabel ? <div><dt className="mb-1 text-[14px] text-[#56635e] dark:text-white/70">{t("workspace_setup_preview.operating_country")}</dt><dd>{countryLabel}</dd></div> : null}
      </dl>
    </> : selected === "contact" || selected === "presence" ? <BusinessProfileDetails footerTarget={footerTarget} initialDraft={providedDraft} onDraftChange={setProvidedDraft} group={selected} saved={details} canEdit={canEdit} onDirtyChange={setDirty} onSave={async next=>{if(live){const fields=selected==="presence"?["website","description"] as const:["address","province","municipality","email","phone"] as const;const saved=await server.save({details:Object.fromEntries(fields.map(field=>[field,next[field]]))});return saved.details;}const saved=saveBusinessProvidedDetails(storage(),businessId,next);refresh();return saved;}} /> : selected === "invoicing" && !live ? canEdit ? <WorkspaceSetupPreview profileInvoicing embedded onProfileChange={refresh} onClose={close} /> : <p className="text-[16px]">{sections.find(section=>section.key === "invoicing")?.summary}</p> : null}
  </div>;
  if(live && (server.refused || !server.profile || !fiscal))return <div className={SURFACE_CARD}>{server.failed||fiscalFailed?<><p role="alert">{t(server.refused?"business.lifecycle.errors.business_unavailable":"business.empty.overview_error")} {failureReference?<ReferenceCode reference={failureReference}/>:null}</p>{!server.refused?<button type="button" className={quietButtonClass} onClick={()=>{server.retry();setFiscalFailed(false);void fetchFiscal().catch(()=>{});}}>{t("common.retry")}</button>:null}</>:<div aria-busy="true" className="h-40 animate-pulse rounded-item bg-black/5"/>}</div>;
  return <>
    <style>{`[data-profile-identity] form{max-width:none}[data-profile-identity] form>div.grid{grid-template-columns:minmax(0,1fr)}[data-profile-identity]>div{margin-top:0}.profile-section-row{display:flex;width:100%;min-width:0;align-items:center;gap:16px;padding:20px 12px;text-align:left;border-radius:8px}.profile-section-row:hover,.profile-section-row[aria-expanded=true]{background:rgba(0,0,0,.04)}.dark .profile-section-row:hover,.dark .profile-section-row[aria-expanded=true]{background:rgba(255,255,255,.06)}.profile-section-copy{min-width:0;flex:1}.profile-section-summary{display:block;overflow-wrap:anywhere;line-height:1.5;margin-top:5px}[data-profile-dossier-content] iframe{max-width:100%}
    `}</style>
    <div data-testid="business-profile-preview" style={{gridTemplateColumns:isBelowDesktop ? undefined : selected ? "minmax(0,1fr)" : "minmax(0,1fr) 20rem"}} className="grid items-start gap-6">
      <div className="min-w-0 space-y-6">
        <section className={SURFACE_CARD} aria-label={t("business.settings.profile_overview")}>
          <div className="mb-5 flex items-center gap-3"><BusinessMark businessId={businessId} name={name}/><div className="min-w-0 flex-1"><h2 className="font-display break-words text-[21px] font-medium">{profile.name}</h2>{countryLabel ? <p className="mt-1 text-[14px] text-[#56635e] dark:text-white/70">{countryLabel}</p> : null}{canEdit?<><button type="button" className={quietButtonClass} disabled={imagePending&&appearanceState!=="failed"} aria-busy={imagePending&&appearanceState!=="failed"?true:undefined} onClick={event=>{if(imagePending)retryProfile();else select({section:"appearance",trigger:event.currentTarget});}}>{t(imagePending&&appearanceState==="failed"?"common.retry":"identity.change_image")}</button>{imagePending?<p role={appearanceState==="failed"?"alert":"status"} className="text-[14px] text-[#56635e] dark:text-white/70">{t(appearanceState==="failed"?"common.error_occurred":"common.loading")}</p>:null}</>:null}</div><button type="button" className={`${quietButtonClass} shrink-0`} aria-expanded={selected === "card"} aria-controls={selected === "card" ? "profile-section-dossier" : undefined} onClick={event=>select({section:"card",trigger:event.currentTarget})}>{t("business.settings.profile_view")}</button></div>
          <div className="divide-y divide-black/10 dark:divide-white/10">{sections.map(section=><button key={section.key} type="button" className="profile-section-row focus-visible:outline-2 focus-visible:outline-offset-2" aria-expanded={selected === section.key} aria-controls={selected === section.key ? "profile-section-dossier" : undefined} onClick={event=>select({section:section.key,trigger:event.currentTarget})}>
            <span className="profile-section-copy"><span className="text-[16px] font-medium">{section.title}</span><span className="profile-section-summary text-[14px] text-[#56635e] dark:text-white/70">{section.summary}</span></span><ChevronRight aria-hidden="true" className="h-4 w-4 shrink-0 text-[#56635e] dark:text-white/70" />
          </button>)}</div>
        </section>
      </div>
      {!selected ? <aside className="rounded-surface border border-[#DCE0DA] bg-[#FFFEFA] p-2 dark:border-white/10 dark:bg-[#1f2225]" aria-labelledby="profile-next-title">
        <div className="rounded-item bg-black/5 p-4 dark:bg-white/5"><h2 id="profile-next-title" className="font-display text-[21px] font-medium">{t("business.settings.profile_finish")}</h2><p className="mt-2 text-[14px] leading-relaxed text-[#56635e] dark:text-white/70">{t("business.settings.profile_finish_detail")}</p>{checklistRows("basic")}</div>
        <div className="px-4 pb-3 pt-5"><h3 className="text-[16px] font-medium">{t("business.settings.profile_additional")}</h3>{checklistRows("additional")}</div>
      </aside> : null}
    </div>
    {selected ? <AdaptivePanel title={selectedTitle} summary={businessContext} headerSize="large" modal={false} width="lg" onClose={close} onBack={isBelowDesktop && selected !== "appearance" ? close : undefined} backLabel={t("business.settings.profile_overview")} closeLabel={t("common.close")} snaps={["full"]} initialSnap="full" returnFocusRef={opener}><div id="profile-section-dossier" style={{padding:isBelowDesktop ? undefined : 20}}>{dossier}{hasEditableForm ? <div ref={setFooterTarget} data-footer-slot="" className="mt-6 border-t border-[#DCE0DA] pt-4 empty:hidden dark:border-white/10" /> : null}</div></AdaptivePanel> : null}
    <ConfirmDialog isOpen={pending !== null} title={t("business.settings.profile_discard_title")} description={t("business.settings.profile_discard_detail")} confirmLabel={t("business.settings.profile_discard")} cancelLabel={t("business.settings.profile_keep_editing")} onCancel={()=>setPending(null)} onConfirm={()=>{if(pending)applySelection(pending);}} />
  </>;
}
