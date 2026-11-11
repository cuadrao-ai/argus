"use client";

import { useEffect } from "react";
import { cuadraoLegalLinks } from "@/lib/cuadrao-legal-links";
import { browserLanguageSources, resolveLanguage } from "@/lib/language-features";

/** Only the browser knows the language the app last showed, so the hop to the published page happens there. */
export function LegalRedirect({ document }: { document: "terms" | "privacy" }) {
  useEffect(() => {
    window.location.replace(cuadraoLegalLinks(resolveLanguage(browserLanguageSources()))[document]);
  }, [document]);
  return null;
}
