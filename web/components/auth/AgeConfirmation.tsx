"use client";

import { useTranslation } from "react-i18next";

const ROW =
  "flex min-h-11 w-full items-center gap-3 px-1 text-sm text-black/70 dark:text-white/70";

export default function AgeConfirmation({
  confirmedAt,
  onConfirmedAt,
}: {
  confirmedAt: string | null;
  onConfirmedAt: (value: string | null) => void;
}) {
  const { t } = useTranslation();
  return (
    <div
      data-testid="age-confirmation-slot"
      className="min-h-11"
      style={{ minHeight: 44 }}
    >
      <label className={`${ROW} cursor-pointer`} style={{ minHeight: 44 }}>
        <input
          id="age-confirmation-checkbox"
          type="checkbox"
          required
          checked={Boolean(confirmedAt)}
          className="h-5 w-5 shrink-0 accent-black dark:accent-white"
          onChange={(event) => {
            onConfirmedAt(event.target.checked ? new Date().toISOString() : null);
          }}
        />
        <span>
          {t("auth.age_confirmation.checkbox", "I confirm I'm 18 or older.")}
        </span>
      </label>
    </div>
  );
}
