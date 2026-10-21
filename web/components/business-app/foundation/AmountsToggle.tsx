"use client";

import { Eye, EyeClosed } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Tooltip } from "@/components/ui/Tooltip";
import { setAmountsHidden, useAmountsHidden } from "@/lib/amounts-hidden";

/**
 * The top bar's eye: one tap blurs every amount, for sharing a screen or
 * working in public. A toggle button keeps one name and lets aria-pressed
 * carry the state, so the tooltip shows that same name. The icon shows the
 * state: an open eye while amounts show, a closed eye while they are hidden.
 * It looks and reacts like the password eye on the sign-in form.
 */
export function AmountsToggle() {
  const { t } = useTranslation();
  const hidden = useAmountsHidden();
  const label = t("business.amounts.hide", "Hide amounts");
  const Icon = hidden ? EyeClosed : Eye;
  return (
    <Tooltip content={label} side="bottom">
      <button
        type="button"
        data-testid="amounts-toggle"
        aria-pressed={hidden}
        aria-label={label}
        onClick={() => setAmountsHidden(!hidden)}
        className="flex h-11 w-11 items-center justify-center rounded-full text-[#56635e] transition-colors hover:bg-[#e3ebe1] hover:text-[#172b26] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f5a49] dark:text-white/70 dark:hover:bg-white/10 dark:hover:text-white dark:focus-visible:outline-[#8fcbb0]"
      >
        <Icon className="h-5 w-5" aria-hidden="true" />
      </button>
    </Tooltip>
  );
}
