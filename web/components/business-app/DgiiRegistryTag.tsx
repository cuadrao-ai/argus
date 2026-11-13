"use client";

import { Check } from "lucide-react";
import { useTranslation } from "react-i18next";

const TAGS = {
  verified: "bg-[#E3EFE8] text-[#2f5a49] dark:bg-[#8fcbb0]/15 dark:text-[#8fcbb0]",
  neutral: "bg-[#EDECE6] text-[#56635e] dark:bg-white/10 dark:text-white/80",
  inactive: "bg-[#F6EBD4] text-[#7a5512] dark:bg-[#f6e7c1]/15 dark:text-[#f6e7c1]",
} as const;

export default function DgiiRegistryTag({ status }: { status: "verified" | "inactive" | "pending" | "unverified" }) {
  const { t } = useTranslation();
  return status === "verified"
    ? <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[12px] font-medium ${TAGS.verified}`}><Check className="h-3 w-3" aria-hidden="true" />{t("business.dgii.legal_name.tag_verified")}</span>
    : status === "inactive"
      ? <span className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[12px] font-medium ${TAGS.inactive}`}><span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-current" />{t("business.dgii.legal_name.tag_inactive")}</span>
      : <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[12px] font-medium ${TAGS.neutral}`}>{t(status === "pending" ? "business.dgii.legal_name.tag_pending" : "business.dgii.legal_name.tag_unverified")}</span>;
}
