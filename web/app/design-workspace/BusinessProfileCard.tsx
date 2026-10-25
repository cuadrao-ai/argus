"use client";

import {useState} from "react";
import Image from "next/image";
import {Globe,Mail,MapPin,Phone} from "lucide-react";
import {useTranslation} from "react-i18next";
import {BusinessMark} from "@/components/business-app/BusinessSwitcher";
import type {readBusinessProfilePreview} from "./businessProfilePreviewState";

type SavedBusinessProfile = ReturnType<typeof readBusinessProfilePreview>;

function SavedBusinessMark({source}:{source:string|null|undefined}) {
  const [failed,setFailed] = useState(false);
  let url:URL|null = null;
  try { if(source)url = new URL(source); } catch { return <BusinessMark />; }
  if(failed || !url || !["https:","http:"].includes(url.protocol)) return <BusinessMark />;
  return <Image unoptimized src={url.href} alt="" aria-hidden="true" width={40} height={40} referrerPolicy="no-referrer" onError={()=>setFailed(true)} className="h-10 w-10 shrink-0 rounded-mark object-cover" />;
}

export default function BusinessProfileCard({profile,logoUrl}:{profile:SavedBusinessProfile;logoUrl?:string|null}) {
  const {t} = useTranslation();
  const details = profile.providedDetails;
  const country = profile.country ? t(`workspace_setup_preview.country_${profile.country.toLowerCase()}`,{defaultValue:profile.country}) : null;
  const location = [details.address,[details.municipality,details.province].filter(Boolean).join(", ")].filter(Boolean).join("\n");
  const contacts = [
    {key:"address",label:t("business.settings.profile_address"),value:location,Icon:MapPin},
    {key:"email",label:t("business.settings.profile_email"),value:details.email,Icon:Mail},
    {key:"phone",label:t("business.settings.profile_phone"),value:details.phone,Icon:Phone},
    {key:"website",label:t("business.settings.profile_website"),value:details.website,Icon:Globe},
  ].filter(item=>item.value);
  return <article data-testid="business-profile-card" aria-label={profile.name} className="min-w-0">
    <div className="flex items-center gap-3">
      <SavedBusinessMark key={logoUrl} source={logoUrl} />
      <div className="min-w-0"><h3 className="font-display text-[21px] font-medium" style={{overflowWrap:"anywhere"}}>{profile.name}</h3>{country ? <p className="mt-1 text-[14px] text-[#56635e] dark:text-white/70">{country}</p> : null}</div>
    </div>
    {details.description ? <p className="mt-5 text-[16px] leading-relaxed" style={{overflowWrap:"anywhere"}}>{details.description}</p> : null}
    <div className="mt-6 border-t border-[#DCE0DA] pt-5 dark:border-white/10">
      {contacts.length ? <dl className="space-y-5">{contacts.map(({key,label,value,Icon})=><div key={key} className="flex items-start gap-3">
        <Icon className="mt-1 h-5 w-5 shrink-0 text-[#56635e] dark:text-white/70" aria-hidden="true" />
        <div className="min-w-0"><dt className="text-[14px] text-[#56635e] dark:text-white/70">{label}</dt><dd className="mt-1 text-[16px] leading-relaxed" style={{overflowWrap:"anywhere",whiteSpace:"pre-line"}}>{value}</dd></div>
      </div>)}</dl> : <p className="text-[14px] leading-relaxed text-[#56635e] dark:text-white/70">{t("business.settings.profile_card_empty_contact")}</p>}
    </div>
  </article>;
}
