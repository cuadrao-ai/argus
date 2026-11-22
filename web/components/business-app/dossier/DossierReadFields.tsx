"use client";

import { useLayoutEffect, useRef, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { DossierCard } from "./DossierParts";
import frame from "./dossier.module.css";
import styles from "../receipt-reading.module.css";

const PLACEHOLDERS = [
  [[34, 104], [58, 170], [30, 120], [42, 92]],
  [[92, 210], [96, 150]],
  [[60, 80], [36, 64], [40, 88]],
];

export default function DossierReadFields({ reading, children }: { reading: boolean; children?: ReactNode }) {
  const { t } = useTranslation();
  const titles = [t("business.dossier.card.comprobante"), t("business.dossier.card.report", { form: "606" }), t("business.terms.montos_title")];
  return <>
    <div role={reading ? "status" : undefined} aria-label={reading ? t("business.reading.document") : undefined} data-reading={reading} className={frame.stack}>
      {PLACEHOLDERS.map((rows, group) => <DossierCard key={group} title={titles[group]}>
        <ul className={frame.rows} aria-hidden="true">
          {rows.map(([label, value]) => <li key={label} className={`${frame.row} ${styles.placeholderRow}`}>
            <span className={`rounded-full ${styles.bar}`} style={{ width: label }} />
            <span className={`rounded-full ${styles.bar} ${styles.placeholderValue}`} style={{ width: value }} />
          </li>)}
        </ul>
      </DossierCard>)}
    </div>
    {children}
  </>;
}

export function useReadLanding(landedDraftId: string | null) {
  const fields = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    if (!landedDraftId || !fields.current || !Element.prototype.animate) return;
    const preference = window.matchMedia("(prefers-reduced-motion: reduce)");
    if (preference.matches) return;
    const rows = Array.from(fields.current.querySelectorAll<HTMLElement>("li[data-fact]"));
    const animations = rows.map((row, index) => {
      const warning = row.matches("[data-attention=true]") || row.querySelector("[data-tone=warn], [data-tone=bad]");
      const wash = warning ? "var(--d-warn-bg)" : "var(--d-flash)";
      return row.animate([
        { offset: 0, opacity: 0, transform: "translateY(6px)", backgroundColor: wash },
        { offset: 0.24, opacity: 1, transform: "none" },
        { offset: 0.6, backgroundColor: wash },
        { offset: 1, backgroundColor: "transparent" },
      ], { duration: 1500, delay: index * 80, fill: "backwards", easing: "ease-out" });
    });
    const stop = () => animations.forEach(animation => animation.cancel());
    preference.addEventListener("change", stop);
    return () => { preference.removeEventListener("change", stop); stop(); };
  }, [landedDraftId]);
  return fields;
}
