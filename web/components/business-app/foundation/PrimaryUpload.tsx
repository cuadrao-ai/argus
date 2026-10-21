"use client";

import { primaryButtonClass } from "../business-ui";

export function PrimaryUpload({ label, onClick, fullWidth = false }: { label: string; onClick: () => void; fullWidth?: boolean }) {
  return (
    <button
      type="button"
      data-testid="business-primary-upload"
      data-primary="true"
      onClick={onClick}
      className={fullWidth ? `${primaryButtonClass} w-full` : primaryButtonClass}
    >
      {label}
    </button>
  );
}
