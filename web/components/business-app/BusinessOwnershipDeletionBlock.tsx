import { useTranslation } from "react-i18next";
import spanish from "@/public/locales/es-419/common.json";

export const businessOwnershipCopyEs = {
  warning: spanish.business.lifecycle.deletion.warning,
  transfer: spanish.business.lifecycle.transfer.title,
  close: spanish.business.lifecycle.close.action,
  reopen: spanish.business.lifecycle.reopen.action,
};

export function useBusinessOwnershipCopy() {
  const { t } = useTranslation();
  return {
    warning: t("business.lifecycle.deletion.warning", businessOwnershipCopyEs.warning),
    transfer: t("business.lifecycle.transfer.title", businessOwnershipCopyEs.transfer),
    close: t("business.lifecycle.close.action", businessOwnershipCopyEs.close),
    reopen: t("business.lifecycle.reopen.action", businessOwnershipCopyEs.reopen),
  };
}

type Copy = { [Key in keyof typeof businessOwnershipCopyEs]: string };
export type SolelyOwnedBusiness = { id: string; name: string; transferHref: string; closeHref: string };

export default function BusinessOwnershipDeletionBlock({ businesses, copy }: { businesses: SolelyOwnedBusiness[]; copy: Copy }) {
  return <ul className="space-y-3">
    {businesses.map(business => <li key={business.id}>
      <p className="text-[14px] leading-relaxed">{copy.warning.replace("{{businessName}}", () => business.name)}</p>
      <div className="flex flex-wrap gap-x-4">
        <a className="inline-flex min-h-11 items-center text-[14px] underline" href={business.transferHref}>{copy.transfer}</a>
        <a className="inline-flex min-h-11 items-center text-[14px] underline" href={business.closeHref}>{copy.close}</a>
      </div>
    </li>)}
  </ul>;
}
