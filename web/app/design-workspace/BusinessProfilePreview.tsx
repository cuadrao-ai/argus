"use client";

import { useCallback, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { Check } from "lucide-react";
import { useTranslation } from "react-i18next";
import { BusinessContext, useBusiness } from "@/components/business-app/BusinessWorkspace";
import BusinessFiscalProfile from "@/components/business-app/BusinessFiscalProfile";
import ReceiptReadingControl from "@/components/business-app/ReceiptReadingControl";
import { SURFACE_CARD } from "@/components/business-app/foundation/surfaces";
import { BusinessMark } from "@/components/business-app/BusinessSwitcher";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import AccessRolePicker from "./AccessRolePicker";
import { secondaryButtonClass } from "@/components/business-app/business-ui";
import { invitationStorageKeys } from "./businessAccessPreviewState";
import { readBusinessProfilePreview, saveBusinessProfilePreview, saveBusinessProvidedDetails, type ProfileChecklistKey } from "./businessProfilePreviewState";
import BusinessProfileDetails from "./BusinessProfileDetails";
import WorkspaceSetupPreview from "./WorkspaceSetupPreview";

const changedEvent = "workspace-preview-profile-changed";
const emptyStorage = {getItem:()=>null,setItem:()=>{}};
// eslint-disable-next-line no-restricted-syntax -- The development-only profile reuses the business-scoped guide store.
const storage = () => typeof window === "undefined" ? emptyStorage : window.localStorage;

export default function BusinessProfilePreview() {
  const workspace = useBusiness();
  const {chosen,records,renamePreviewBusiness} = workspace;
  const {t} = useTranslation();
  const {isBelowDesktop} = useResponsiveLayout();
  const businessId = chosen?.space_id ?? "";
  const name = chosen?.name ?? "";
  const country = records.workspace?.country;
  const canEdit = chosen?.role === "owner";
  const [invoicing,setInvoicing] = useState(false);
  const form = useRef<HTMLDivElement>(null);
  const subscribe = useCallback((listener:()=>void) => {
    window.addEventListener("storage",listener);window.addEventListener(changedEvent,listener);
    return ()=>{window.removeEventListener("storage",listener);window.removeEventListener(changedEvent,listener);};
  },[]);
  const snapshot = useCallback(()=>storage().getItem(invitationStorageKeys(businessId).guide) ?? "",[businessId]);
  const raw = useSyncExternalStore(subscribe,snapshot,()=>"");
  const profile = useMemo(()=>{void raw;return readBusinessProfilePreview(storage(),businessId,name,country);},[raw,businessId,name,country]);
  const taxType = profile.taxId?.type;
  const taxValue = profile.taxId?.value;
  const localSource = useMemo(()=>({...workspace.source,
    fiscalProfile:async()=>({name:profile.name,tax_id:taxType && taxValue ? {type:taxType,value:taxValue} : null,can_edit:canEdit}),
    saveFiscalProfile:async(input:Parameters<typeof saveBusinessProfilePreview>[2])=>{
      if(!canEdit) throw new Error("permission_denied");
      saveBusinessProfilePreview(storage(),businessId,input);
      renamePreviewBusiness?.(input.name);
      window.dispatchEvent(new Event(changedEvent));
      return {name:input.name,tax_id:input.tax_id,can_edit:canEdit};
    },
  }),[workspace.source,profile.name,taxType,taxValue,canEdit,businessId,renamePreviewBusiness]);
  const formContext = useMemo(()=>({...workspace,source:localSource,reload:()=>{}}),[workspace,localSource]);
  const countryLabel = profile.country ? t(`workspace_setup_preview.country_${profile.country.toLowerCase()}`,{defaultValue:profile.country}) : null;
  const labels: Record<ProfileChecklistKey,string> = {
    name:t("workspace_setup_preview.business_name"),taxId:t("business.dgii.tax_id_type"),legalName:t("workspace_setup_preview.legal_name"),country:t("workspace_setup_preview.operating_country"),address:t("business.settings.profile_address"),email:t("business.settings.profile_email"),phone:t("business.settings.profile_phone"),website:t("business.settings.profile_website"),description:t("business.settings.profile_description"),
  };
  const focusField = (key:ProfileChecklistKey)=>{
    const selector = key === "name" ? '[name="business-name"]' : key === "taxId" ? '[name="tax-id-value"]' : key === "legalName" ? '[data-profile-legal]' : key === "country" ? '[data-profile-country]' : `[name="profile-${key}"]`;
    form.current?.querySelector<HTMLElement>(selector)?.focus();
  };
  const checklistRows = (section:"basic"|"additional")=><ul className="mt-3">{profile.checklist.filter(item=>item.section===section).map(item=><li key={item.key}><button type="button" disabled={!canEdit || (item.key === "country" && !profile.country)} onClick={()=>focusField(item.key)} className="flex min-h-11 w-full items-center gap-3 rounded-item text-left text-[16px] focus-visible:outline-2 focus-visible:outline-offset-2">
    <span aria-hidden="true" style={item.complete ? undefined : {borderColor:"currentColor",opacity:0.35}} className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full ${item.complete ? "bg-[#2f5a49] text-white dark:bg-[#8fcbb0] dark:text-[#13211c]" : "border border-black/25 dark:border-white/35"}`}>{item.complete ? <Check className="h-3 w-3"/> : null}</span>
    <span style={item.complete ? {textDecoration:"line-through"} : undefined} className={item.complete ? "text-[#56635e] dark:text-white/60" : ""}>{labels[item.key]}<span className="sr-only"> · {t(item.complete ? "business.settings.profile_saved" : "business.settings.profile_pending")}</span></span>
  </button></li>)}</ul>;
  return <>
    <div data-testid="business-profile-preview" style={{gridTemplateColumns:isBelowDesktop ? undefined : "minmax(0,1fr) 20rem"}} className="grid items-start gap-6">
      <div className="min-w-0 space-y-6">
        <section ref={form} className={SURFACE_CARD}>
          <div className="flex items-center gap-3">
            <BusinessMark />
            <h2 className="font-display break-words text-[21px] font-medium">{profile.name}</h2>
          </div>
          <div data-profile-identity><style>{"[data-profile-identity] form{max-width:none}"}</style><BusinessContext.Provider value={formContext}><BusinessFiscalProfile renderTaxIdControl={props=><div><AccessRolePicker {...props} showDetail={false} options={(["rnc","cedula"] as const).map(type=>({value:type,label:t(`business.dgii.tax_id_${type}`),description:t(`business.dgii.tax_id_hint_${type}`)}))} onChange={value=>props.onChange(value as "rnc"|"cedula")} /></div>} /></BusinessContext.Provider></div>
          {countryLabel ? <dl data-profile-country tabIndex={-1} className="mt-5 text-[16px]"><dt className="mb-1 text-[14px] text-[#56635e] dark:text-white/70">{t("workspace_setup_preview.operating_country")}</dt><dd>{countryLabel}</dd></dl> : null}
          <dl data-profile-legal tabIndex={-1} className="mt-5 text-[16px]"><dt className="mb-1 text-[14px] text-[#56635e] dark:text-white/70">{t("workspace_setup_preview.legal_name")}</dt><dd>{profile.legalName || t("business.settings.profile_unverified")}</dd></dl>
          <BusinessProfileDetails key={businessId} saved={profile.providedDetails} canEdit={canEdit} onSave={details=>{const next=saveBusinessProvidedDetails(storage(),businessId,details);window.dispatchEvent(new Event(changedEvent));return next;}} />
          <div className="mt-6 border-t border-black/10 pt-6 dark:border-white/10">
            <div className="flex flex-wrap items-baseline justify-between gap-2"><h3 className="text-[16px] font-medium">{t("workspace_setup_preview.invoice_title")}</h3><span className="text-[14px] text-[#56635e] dark:text-white/70">{t("workspace_setup_preview.optional")}</span></div>
            <p className="mt-2 text-[14px] text-[#56635e] dark:text-white/70">{t(`workspace_setup_preview.invoice_${profile.invoice.status.replaceAll("-","_")}`)}</p>
            {canEdit ? <button type="button" onClick={()=>setInvoicing(true)} className={`${secondaryButtonClass} mt-4`}>{t(profile.invoice.action === "configure" ? "business.settings.profile_invoice_configure" : `workspace_setup_preview.invoice_${profile.invoice.action}`)}</button> : null}
          </div>
        </section>
        <div className={SURFACE_CARD}><ReceiptReadingControl variant="row" /></div>
      </div>
      <aside className="rounded-surface border border-[#DCE0DA] bg-[#FFFEFA] p-2 dark:border-white/10 dark:bg-[#1f2225]" aria-labelledby="profile-next-title">
        <div className="rounded-item bg-black/5 p-4 dark:bg-white/5">
          <h2 id="profile-next-title" className="font-display text-[21px] font-medium">{t("business.settings.profile_finish")}</h2>
          <p className="mt-2 text-[14px] leading-relaxed text-[#56635e] dark:text-white/70">{t("business.settings.profile_finish_detail")}</p>
          {checklistRows("basic")}
        </div>
        <div className="px-4 pb-3 pt-5"><h3 className="text-[16px] font-medium">{t("business.settings.profile_additional")}</h3>{checklistRows("additional")}</div>
      </aside>
    </div>
    {invoicing ? <WorkspaceSetupPreview profileInvoicing onClose={()=>{setInvoicing(false);window.dispatchEvent(new Event(changedEvent));}} /> : null}
  </>;
}
