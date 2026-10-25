"use client";

import { useCallback, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { Check, ChevronRight } from "lucide-react";
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
import { readBusinessProfilePreview, saveBusinessProfilePreview } from "./businessProfilePreviewState";
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
  const localSource = useMemo(()=>({...workspace.source,
    fiscalProfile:async()=>({name:profile.name,tax_id:profile.taxId,can_edit:canEdit}),
    saveFiscalProfile:async(input:Parameters<typeof saveBusinessProfilePreview>[2])=>{
      if(!canEdit) throw new Error("permission_denied");
      saveBusinessProfilePreview(storage(),businessId,input);
      renamePreviewBusiness?.(input.name);
      window.dispatchEvent(new Event(changedEvent));
      return {name:input.name,tax_id:input.tax_id,can_edit:canEdit};
    },
  }),[workspace.source,profile.name,profile.taxId,canEdit,businessId,renamePreviewBusiness]);
  const formContext = useMemo(()=>({...workspace,source:localSource,reload:()=>{}}),[workspace,localSource]);
  const countryLabel = profile.country ? t(`workspace_setup_preview.country_${profile.country.toLowerCase()}`,{defaultValue:profile.country}) : null;
  const reviewName = ()=>form.current?.querySelector<HTMLInputElement>('input[name="business-name"]')?.focus();
  return <>
    <div data-testid="business-profile-preview" style={{gridTemplateColumns:isBelowDesktop ? undefined : "minmax(0,1.5fr) minmax(17rem,1fr)"}} className="grid items-start gap-6">
      <div className="min-w-0 space-y-6" style={{maxWidth:"40rem"}}>
        <section ref={form} className={SURFACE_CARD}>
          <div className="flex items-center gap-3">
            <BusinessMark />
            <h2 className="font-display break-words text-[21px] font-medium">{profile.name}</h2>
          </div>
          <BusinessContext.Provider value={formContext}><BusinessFiscalProfile renderTaxIdControl={props=><div><AccessRolePicker {...props} showDetail={false} options={(["rnc","cedula"] as const).map(type=>({value:type,label:t(`business.dgii.tax_id_${type}`),description:t(`business.dgii.tax_id_hint_${type}`)}))} onChange={value=>props.onChange(value as "rnc"|"cedula")} /></div>} /></BusinessContext.Provider>
          {countryLabel ? <dl className="mt-5 text-[16px]"><dt className="mb-1 text-[14px] text-[#56635e] dark:text-white/70">{t("workspace_setup_preview.operating_country")}</dt><dd>{countryLabel}</dd></dl> : null}
          {profile.legalName ? <dl className="mt-5 text-[16px]"><dt className="mb-1 text-[14px] text-[#56635e] dark:text-white/70">{t("workspace_setup_preview.legal_name")}</dt><dd>{profile.legalName}</dd></dl> : null}
        </section>
        <div className={SURFACE_CARD}><ReceiptReadingControl variant="row" /></div>
      </div>
      <aside className={SURFACE_CARD} aria-labelledby="profile-next-title">
        <h2 id="profile-next-title" className="font-display text-[21px] font-medium">{t("business.settings.profile_finish")}</h2>
        <p className="mt-2 text-[14px] leading-relaxed text-[#56635e] dark:text-white/70">{t("business.settings.profile_finish_detail")}</p>
        <ul className="mt-4 space-y-1 text-[16px]">
          {profile.name ? <li><button type="button" onClick={reviewName} disabled={!canEdit} className="flex min-h-11 w-full items-center gap-3 rounded-item text-left focus-visible:outline-2 focus-visible:outline-offset-2"><Check aria-hidden="true" className="h-4 w-4 shrink-0"/><span className="flex-1">{t("workspace_setup_preview.business_name")}<span className="sr-only"> · {t("business.settings.profile_saved")}</span></span>{canEdit ? <ChevronRight aria-hidden="true" className="h-4 w-4"/> : null}</button></li> : null}
          {countryLabel ? <li className="flex min-h-11 items-center gap-3"><Check aria-hidden="true" className="h-4 w-4 shrink-0"/><span>{t("workspace_setup_preview.operating_country")}<span className="block text-[14px] text-[#56635e] dark:text-white/70">{countryLabel}</span><span className="sr-only"> · {t("business.settings.profile_saved")}</span></span></li> : null}
        </ul>
        <div className="mt-4 border-t border-black/10 pt-5 dark:border-white/10">
          <div className="flex flex-wrap items-baseline justify-between gap-2"><h3 className="text-[16px] font-medium">{t("workspace_setup_preview.invoice_title")}</h3><span className="text-[14px] text-[#56635e] dark:text-white/70">{t("workspace_setup_preview.optional")}</span></div>
          <p className="mt-2 text-[14px] text-[#56635e] dark:text-white/70">{t(`workspace_setup_preview.invoice_${profile.invoice.status.replaceAll("-","_")}`)}</p>
          {canEdit ? <button type="button" onClick={()=>setInvoicing(true)} className={`${secondaryButtonClass} mt-4 w-full`}>{t(profile.invoice.action === "configure" ? "business.settings.profile_invoice_configure" : `workspace_setup_preview.invoice_${profile.invoice.action}`)}</button> : null}
        </div>
      </aside>
    </div>
    {invoicing ? <WorkspaceSetupPreview profileInvoicing onClose={()=>{setInvoicing(false);window.dispatchEvent(new Event(changedEvent));}} /> : null}
  </>;
}
