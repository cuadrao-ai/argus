"use client";

import { Eye, EyeOff } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Tooltip } from "@/components/ui/Tooltip";
import { setAmountsHidden, useAmountsHidden } from "@/lib/amounts-hidden";

/** The top bar's eye: one tap blurs every amount, for sharing a screen or working in public. */
export function AmountsToggle() {
  const { t } = useTranslation();
  const hidden = useAmountsHidden();
  const label = hidden ? t("business.amounts.show", "Show amounts") : t("business.amounts.hide", "Hide amounts");
  return (
    <Tooltip content={label} side="bottom">
      <button
        type="button"
        data-testid="amounts-toggle"
        aria-pressed={hidden}
        aria-label={t("business.amounts.hide", "Hide amounts")}
        onClick={() => setAmountsHidden(!hidden)}
        className="flex h-11 w-11 items-center justify-center rounded-full border border-[#DCE0DA] bg-[#FFFEFA] text-[#56635e] transition-colors hover:text-[#172b26] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f5a49] aria-pressed:bg-[#e3ebe1] aria-pressed:text-[#2f5a49] dark:border-white/10 dark:bg-[#1f2225] dark:text-white/70"
      >
        {hidden ? <EyeOff className="h-[18px] w-[18px]" aria-hidden="true" /> : <Eye className="h-[18px] w-[18px]" aria-hidden="true" />}
      </button>
    </Tooltip>
  );
}
