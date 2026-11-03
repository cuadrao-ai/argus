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
