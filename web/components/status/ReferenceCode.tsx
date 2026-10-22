"use client";

import { useTranslation } from "react-i18next";
import { CopyButton } from "@/components/business-app/foundation/CopyButton";
import { shortReference } from "@/lib/failure-screen";

export type ReferenceLabels = { shown: string; name: string; copied: string; failed: string };

/**
 * The one way a failure's reference shows: its short form in small muted
 * text, the full id in the title and the accessible name, and a press copies
 * the full id so support finds the exact request in the server logs.
 */
export function ReferenceCodeView({ reference, labels }: { reference: string; labels: ReferenceLabels }) {
  return (
    <CopyButton
      value={reference}
      title={reference}
      label={labels.name}
      copiedLabel={labels.copied}
      failedLabel={labels.failed}
      testId="error-reference"
      className="inline-flex items-center gap-1 rounded text-[12px] tabular-nums opacity-80 hover:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-current [&_svg]:h-3 [&_svg]:w-3"
    >
      <span data-reference-short aria-hidden="true">{labels.shown}</span>
      <span className="sr-only">{labels.name}</span>
    </CopyButton>
  );
}

export function ReferenceCode({ reference }: { reference: string }) {
  const { t } = useTranslation();
  return (
    <ReferenceCodeView
      reference={reference}
      labels={{
        shown: t("common.reference", { reference: shortReference(reference), defaultValue: "Ref. {{reference}}" }),
        name: t("common.reference_copy", { reference, defaultValue: "Copy reference {{reference}}" }),
        copied: t("common.reference_copied", "Reference copied."),
        failed: t("common.reference_copy_failed", { reference, defaultValue: "Could not copy it. Your reference is {{reference}}" }),
      }}
    />
  );
}
