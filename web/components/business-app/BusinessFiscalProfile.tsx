"use client";

import { useContext, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  getFiscalProfile,
  setFiscalProfile,
  type FiscalProfile,
  type TaxIdType,
} from "@/lib/business-dgii";
import { randomId } from "@/lib/random-id";
import { BusinessContext } from "./BusinessWorkspace";
import { quietButtonClass, secondaryButtonClass } from "./business-ui";
import { Settle } from "./business-skeletons";

const LENGTH = { rnc: 9, cedula: 11 } as const;

function digitsOf(raw: string): string {
  return raw.replace(/[ -]/g, "");
}

function acceptable(kind: TaxIdType, raw: string): boolean {
  if (!raw.trim()) return true;
  const digits = digitsOf(raw);
  return new RegExp(`^(?!0+$)\\d{${LENGTH[kind]}}$`).test(digits);
}

function labelFor(profile: FiscalProfile): string {
  if (!profile.tax_id) return "606 / 607 · No aplica";
  const title = profile.tax_id.type === "cedula" ? "Cédula" : "RNC";
  return `${title} ${profile.tax_id.value}`;
}

export default function BusinessFiscalProfile({ draftId }: { draftId?: string }) {
  const { t } = useTranslation();
  const workspace = useContext(BusinessContext);
  const [profile, setProfile] = useState<FiscalProfile | null>(null);
  const [name, setName] = useState("");
  const [kind, setKind] = useState<TaxIdType>("rnc");
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  // The workspace's source owns the read, so the sample business answers with its own name and RNC.
  const read = workspace?.source.fiscalProfile ?? getFiscalProfile;
  const write = workspace?.source.saveFiscalProfile ?? setFiscalProfile;
  useEffect(() => {
    let live = true;
    setLoadFailed(false);
    void read(draftId)
      .then((next) => {
        if (!live) return;
        setProfile(next);
        setName(next.name);
        setKind(next.tax_id?.type ?? "rnc");
        setValue(next.tax_id?.value ?? "");
      })
      .catch(() => {
        if (live) setLoadFailed(true);
      });
    return () => {
      live = false;
    };
  }, [draftId, read, attempt]);
  const save = async () => {
    if (!profile || busy || !acceptable(kind, value)) return;
    setBusy(true);
    setProblem(null);
    try {
      const next = await write(
        {
          name: name.trim(),
          previous_name: profile.name,
          tax_id: value.trim() ? { type: kind, value: value.trim() } : null,
          previous_tax_id: profile.tax_id,
        },
        randomId(),
      );
      setProfile(next);
      setName(next.name);
      setKind(next.tax_id?.type ?? kind);
      setValue(next.tax_id?.value ?? "");
      if (next.name !== profile.name) workspace?.reload();
    } catch (error) {
      const code = (error as { code?: string }).code;
      setProblem(
        t(`business.dgii.error.${code}`, {
          defaultValue: t("business.dgii.profile_failed"),
        }),
      );
    } finally {
      setBusy(false);
    }
  };
  const unchanged =
    profile !== null &&
    name.trim() === profile.name &&
    (value.trim() ? digitsOf(value) : "") === (profile.tax_id?.value ?? "") &&
    (value.trim() ? kind : profile.tax_id?.type ?? kind) === (profile.tax_id?.type ?? kind);
  return (
    <div className="mt-3 space-y-2" data-testid="business-fiscal-profile">
      {profile === null && !loadFailed ? <Settle pending layout="form" /> : null}
      {/* The editable fields already show the name and number; the summary line is for those who can only read. */}
      {profile && !profile.can_edit ? (
        <p className="text-[13px] text-black/65 dark:text-white/65">
          {profile.name} · {labelFor(profile)}
        </p>
      ) : null}
      {profile?.can_edit ? (
        <div className="flex flex-wrap items-end gap-2">
          <label className="text-[13px] text-black/65 dark:text-white/65">
            {t("business.dgii.business_name", "Business name")}
            <input
              name="business-name"
              aria-label={t("business.dgii.business_name", "Business name")}
              value={name}
              disabled={busy}
              maxLength={80}
              onChange={(event) => setName(event.target.value)}
              className="mt-1 block min-h-11 rounded-lg border border-black/15 bg-transparent px-3 dark:border-white/20"
            />
          </label>
          <label className="text-[13px] text-black/65 dark:text-white/65">
            {t("business.dgii.tax_id_type", "Tax id")}
            <select
              name="tax-id-type"
              aria-label={t("business.dgii.tax_id_type", "Tax id")}
              value={kind}
              disabled={busy}
              onChange={(event) => setKind(event.target.value as TaxIdType)}
              className="mt-1 block min-h-11 rounded-lg border border-black/15 bg-transparent px-3 dark:border-white/20"
            >
              <option value="rnc">{t("business.dgii.tax_id_rnc", "RNC")}</option>
              <option value="cedula">{t("business.dgii.tax_id_cedula", "Cédula")}</option>
            </select>
          </label>
          <label className="text-[13px] text-black/65 dark:text-white/65">
            {t("business.dgii.tax_id_value", "Number")}
            <input
              name="tax-id-value"
              aria-label={t("business.dgii.tax_id_value", "Number")}
              inputMode="numeric"
              maxLength={13}
              value={value}
              disabled={busy}
              onChange={(event) => setValue(event.target.value)}
              className="mt-1 block min-h-11 rounded-lg border border-black/15 bg-transparent px-3 dark:border-white/20"
            />
          </label>
          <button
            type="button"
            className={secondaryButtonClass}
            disabled={busy || unchanged || !name.trim() || !acceptable(kind, value)}
            onClick={() => void save()}
          >
            {t("business.dgii.save_profile", "Save")}
          </button>
        </div>
      ) : null}
      {loadFailed ? (
        <p role="alert" className="flex flex-wrap items-center gap-2 text-[14px] text-[#9e2f39] dark:text-[#ec9aa0]">
          {t("business.dgii.profile_load_failed", "We couldn't load the name and RNC.")}
          <button type="button" onClick={() => setAttempt((value) => value + 1)} className={quietButtonClass}>
            {t("common.retry", "Retry")}
          </button>
        </p>
      ) : null}
      {problem ? (
        <p role="alert" className="text-[13px] text-[#9e2f39] dark:text-[#ec9aa0]">
          {problem}
        </p>
      ) : null}
    </div>
  );
}
