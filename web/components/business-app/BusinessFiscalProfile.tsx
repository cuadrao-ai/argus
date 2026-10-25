"use client";

import { type FormEvent, type ReactNode, useContext, useEffect, useId, useState } from "react";
import { AlertCircle } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  getFiscalProfile,
  setFiscalProfile,
  type FiscalProfile,
  type TaxIdType,
} from "@/lib/business-dgii";
import { randomId } from "@/lib/random-id";
import { ErrorSummary, FormField, SelectField, useFieldChecks, type FieldRules } from "@/components/ui/FormField";
import { BusinessContext } from "./BusinessWorkspace";
import { quietButtonClass, secondaryButtonClass } from "./business-ui";
import { Settle } from "./business-skeletons";

const LENGTH = { rnc: 9, cedula: 11 } as const;

function digitsOf(raw: string): string {
  return raw.replace(/[ -]/g, "");
}

type Field = "name" | "number";
/** A refusal the server explains; retrying the same values cannot help. */
type Problem = { text: string; retry: boolean };

export default function BusinessFiscalProfile({ draftId, renderTaxIdControl }: { draftId?: string; renderTaxIdControl?: (props: {value: TaxIdType; label: string; disabled: boolean; onChange: (value: TaxIdType) => void}) => ReactNode }) {
  const { t, i18n } = useTranslation();
  const workspace = useContext(BusinessContext);
  const base = useId();
  const [profile, setProfile] = useState<FiscalProfile | null>(null);
  const [name, setName] = useState("");
  const [kind, setKind] = useState<TaxIdType>("rnc");
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<Problem | null>(null);
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

  // The same rules the server applies to a tax id: digits once spaces and hyphens go, the exact length, not all zeros.
  const rules: FieldRules<Field> = {
    name: (values) =>
      values.name.trim() ? null : t("business.dgii.business_name_required", "Enter the business name."),
    number: (values) => {
      if (!values.number.trim()) return null;
      const digits = digitsOf(values.number);
      if (!/^\d+$/.test(digits)) return t("business.dgii.error.tax_id_not_digits", "Use digits and hyphens only.");
      if (digits.length !== LENGTH[kind]) {
        return kind === "rnc"
          ? t("business.dgii.tax_id_length_rnc", "An RNC has 9 digits.")
          : t("business.dgii.tax_id_length_cedula", "A cédula has 11 digits.");
      }
      return /^0+$/.test(digits) ? t("business.dgii.error.tax_id_all_zero", "It can't be all zeros.") : null;
    },
  };
  const checks = useFieldChecks(rules, { name, number: value });

  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!profile || busy || !checks.submit()) return;
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
      checks.reset();
      if (next.name !== profile.name) workspace?.reload();
    } catch (error) {
      const code = (error as { code?: string }).code;
      const known = Boolean(code) && i18n.exists(`business.dgii.error.${code}`);
      setProblem({
        text: known ? t(`business.dgii.error.${code}`) : t("business.dgii.profile_failed"),
        retry: !known,
      });
    } finally {
      setBusy(false);
    }
  };
  const unchanged =
    profile !== null &&
    name.trim() === profile.name &&
    (value.trim() ? digitsOf(value) : "") === (profile.tax_id?.value ?? "") &&
    (value.trim() ? kind : profile.tax_id?.type ?? kind) === (profile.tax_id?.type ?? kind);
  const ids: Record<Field, string> = { name: `${base}-name`, number: `${base}-number` };
  const labels: Record<Field, string> = {
    name: t("business.dgii.business_name", "Business name"),
    number: t("business.dgii.tax_id_value", "Number"),
  };
  const taxIdTitle = profile?.tax_id?.type === "cedula" ? t("business.dgii.tax_id_cedula", "Cédula") : t("business.dgii.tax_id_rnc", "RNC");
  return (
    <div className="mt-[21px]" data-testid="business-fiscal-profile">
      {profile === null && !loadFailed ? <Settle pending layout="form" /> : null}
      {/* The editable fields already show the name and number; the summary line is for those who can only read. */}
      {profile && !profile.can_edit ? (
        <p className="text-[14px] text-[#56635e] dark:text-white/70">
          {profile.name || "-"} · {profile.tax_id ? `${taxIdTitle} ${profile.tax_id.value}` : t("business.dgii.tax_id_none", "606 / 607 · Not applicable")}
        </p>
      ) : null}
      {profile?.can_edit ? (
        <form noValidate onSubmit={(event) => void save(event)} className="max-w-[34rem] space-y-[13px]">
          <ErrorSummary
            key={checks.attempt}
            title={t("common.form_summary", "Check these fields to continue:")}
            items={checks.summary.map((field) => ({ id: ids[field], label: labels[field] }))}
          />
          <FormField
            id={ids.name}
            name="business-name"
            label={labels.name}
            error={checks.errorOf("name")}
            autoComplete="organization"
            maxLength={80}
            value={name}
            disabled={busy}
            onBlur={() => checks.blur("name")}
            onChange={(event) => setName(event.target.value)}
          />
          <div className="grid gap-x-[13px] gap-y-[13px] tablet:grid-cols-[minmax(0,11rem)_minmax(0,1fr)]">
            {renderTaxIdControl ? renderTaxIdControl({value:kind,label:t("business.dgii.tax_id_type", "Tax id"),disabled:busy,onChange:setKind}) : <SelectField
              id={`${base}-kind`}
              name="tax-id-type"
              label={t("business.dgii.tax_id_type", "Tax id")}
              value={kind}
              disabled={busy}
              onChange={(event) => setKind(event.target.value as TaxIdType)}
            >
              <option value="rnc">{t("business.dgii.tax_id_rnc", "RNC")}</option>
              <option value="cedula">{t("business.dgii.tax_id_cedula", "Cédula")}</option>
            </SelectField>}
            <FormField
              id={ids.number}
              name="tax-id-value"
              label={labels.number}
              hint={
                kind === "rnc"
                  ? t("business.dgii.tax_id_hint_rnc", "9 digits. Hyphens are fine.")
                  : t("business.dgii.tax_id_hint_cedula", "11 digits. Hyphens are fine.")
              }
              error={checks.errorOf("number")}
              inputMode="numeric"
              autoComplete="off"
              spellCheck={false}
              maxLength={13}
              value={value}
              disabled={busy}
              onBlur={() => checks.blur("number")}
              onChange={(event) => setValue(event.target.value)}
            />
          </div>
          <div className="pt-2">
            <button type="submit" className={secondaryButtonClass} disabled={busy || unchanged}>
              {t("business.dgii.save_profile", "Save")}
            </button>
          </div>
          {problem ? (
            <div role="alert" className="flex items-start gap-2 text-[14px] leading-relaxed text-[#9e2f39] dark:text-[#ec9aa0]">
              <AlertCircle className="mt-[3px] h-4 w-4 shrink-0" aria-hidden="true" />
              <div className="min-w-0">
                <p>{problem.text}</p>
                {problem.retry ? (
                  <button type="submit" disabled={busy} className={`${quietButtonClass} -ml-1`}>
                    {t("common.retry", "Retry")}
                  </button>
                ) : null}
              </div>
            </div>
          ) : null}
        </form>
      ) : null}
      {loadFailed ? (
        <div role="alert" className="flex items-start gap-2 text-[14px] leading-relaxed text-[#9e2f39] dark:text-[#ec9aa0]">
          <AlertCircle className="mt-[3px] h-4 w-4 shrink-0" aria-hidden="true" />
          <div className="min-w-0">
            <p>{t("business.dgii.profile_load_failed", "We couldn't load the name and RNC.")}</p>
            <button type="button" onClick={() => setAttempt((count) => count + 1)} className={`${quietButtonClass} -ml-1`}>
              {t("common.retry", "Retry")}
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
