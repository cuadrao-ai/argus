"use client";

import { useTranslation } from "react-i18next";
import { SampleDataNotice } from "./business-ui";

/** The heading of an empty Business conversation. */
export default function BusinessHome({ variant }: { variant: "new_chat" }) {
  const { t } = useTranslation();
  return (
    <div data-business-home={variant} className="w-full max-w-2xl text-center">
      <SampleDataNotice />
      <h1 className="font-display text-[28px] font-medium tracking-tight text-black dark:text-white">
        {t("business.home.title", "What can we do for your business?")}
      </h1>
      <p className="mt-2 text-[15px] text-black/55 dark:text-white/55">
        {t("business.home.body", "Add a receipt, record an expense, or ask about what you've saved.")}
      </p>
    </div>
  );
}
