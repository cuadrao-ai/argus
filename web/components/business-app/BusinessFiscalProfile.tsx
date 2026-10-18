"use client";

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { getFiscalProfile, setFiscalProfile, type FiscalProfile } from "@/lib/business-dgii";
import { randomId } from "@/lib/random-id";
import { secondaryButtonClass } from "./business-ui";

export default function BusinessFiscalProfile({ draftId }: { draftId?: string }) {
  const { t } = useTranslation();
  const [profile, setProfile] = useState<FiscalProfile | null>(null);
  const [rnc, setRnc] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState(false);
  useEffect(() => {
    let live = true;
    void getFiscalProfile(draftId).then((value) => { if (live) { setProfile(value); setRnc(value.rnc ?? ""); } }).catch(() => { if (live) setProblem(true); });
    return () => { live = false; };
  }, [draftId]);
  const save = async () => {
    if (!profile || busy) return;
    setBusy(true); setProblem(false);
    try { setProfile(await setFiscalProfile(rnc || null, profile.rnc, randomId())); }
    catch { setProblem(true); }
    finally { setBusy(false); }
  };
  return <div className="mt-3 space-y-2" data-testid="business-fiscal-profile">
    {profile ? <p className="text-[13px] text-black/65 dark:text-white/65">{profile.rnc ? `RNC ${profile.rnc}` : "606 / 607 · No aplica"}</p> : null}
    {profile?.can_edit ? <div className="flex flex-wrap items-end gap-2"><label className="text-[13px] text-black/65 dark:text-white/65">{t("business.dgii.business_rnc", "RNC del negocio")}<input aria-label={t("business.dgii.business_rnc", "RNC del negocio")} inputMode="numeric" maxLength={11} value={rnc} disabled={busy} onChange={(event) => setRnc(event.target.value)} className="mt-1 block min-h-11 rounded-lg border border-black/15 bg-transparent px-3 dark:border-white/20" /></label><button type="button" className={secondaryButtonClass} disabled={busy || rnc === (profile.rnc ?? "") || Boolean(rnc) && !/^(?!0+$)(?:\d{9}|\d{11})$/.test(rnc)} onClick={() => void save()}>{t("business.dgii.save_rnc", "Guardar RNC")}</button></div> : null}
    {problem ? <p role="alert" className="text-[13px] text-[#a8434c]">{t("business.dgii.profile_failed", "No se pudo leer o guardar el RNC. Revisa el negocio abierto antes de intentar de nuevo.")}</p> : null}
  </div>;
}
