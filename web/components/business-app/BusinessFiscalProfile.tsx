"use client";

import { type FormEvent, type ReactNode, useContext, useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { AlertCircle } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  getFiscalProfile,
  setFiscalProfile,
  type FiscalProfile,
  type TaxIdType,
} from "@/lib/business-dgii";
import { randomId } from "@/lib/random-id";
import { referenceCode } from "@/lib/failure-screen";
import { ReferenceCode } from "@/components/status/ReferenceCode";
import { ErrorSummary, FormField, SelectField, useFieldChecks, type FieldRules } from "@/components/ui/FormField";
import { BusinessContext } from "./BusinessWorkspace";
import { formatBusinessName } from "./business-format";
import { primaryButtonClass, quietButtonClass, secondaryButtonClass } from "./business-ui";
import { Settle } from "./business-skeletons";
import DgiiRegistryStatus, { registryStatusOf, useRegistryLookup, type RegistryLookup, type RegistryStatusState } from "./DgiiRegistryStatus";

const LENGTH = { rnc: 9, cedula: 11 } as const;

function digitsOf(raw: string): string {
  return raw.replace(/[ -]/g, "");
}

type Field = "name" | "number";
export type FiscalProfileDraft = {name:string;kind:TaxIdType;value:string};
/** A refusal the server explains; retrying the same values cannot help. */
type Problem = { text: string; retry: boolean; reference?: string };
/** What the Razón social block shows for the typed number. */
/** `stored` is true when the name shown is the one confirmed for this number; only an unstored match asks to confirm. */
type LegalNameState = Exclude<RegistryStatusState, { status: "inactive" }> | { status: "inactive"; name: string; registryStatus: string; stored: boolean };

/** The tag is always the registry's current word for the typed number. A name confirmed for that
 * number is shown in place of the registry's, and is Verificado only while the registry says verificado. */
function legalNameState(profile: FiscalProfile, kind: TaxIdType, digits: string, lookup: RegistryLookup): LegalNameState {
  const stored = profile.legal_name && profile.tax_id?.type === kind && profile.tax_id.value === digits ? profile.legal_name.value : null;
  const registry = registryStatusOf(lookup);
  if (registry.status === "checking") return registry;
  if (registry.status === "failed" || registry.status === "unverified") return { ...registry, name: stored };
  if (registry.status === "inactive") return { ...registry, name: stored ?? registry.name, stored: stored !== null };
  return stored ? { status: "verified", name: stored } : { status: "pending", name: registry.name };
}

export default function BusinessFiscalProfile({ draftId, renderTaxIdControl, onDirtyChange, initialDraft, onDraftChange, footerTarget }: { draftId?: string; footerTarget?: HTMLElement | null; initialDraft?: FiscalProfileDraft | null; onDraftChange?: (draft:FiscalProfileDraft) => void; onDirtyChange?: (dirty: boolean) => void; renderTaxIdControl?: (props: {value: TaxIdType; label: string; disabled: boolean; onChange: (value: TaxIdType) => void}) => ReactNode }) {
  const { t, i18n } = useTranslation();
  const workspace = useContext(BusinessContext);
  const base = useId();
  const restoredDraft = useRef(initialDraft);
  const [profile, setProfile] = useState<FiscalProfile | null>(null);
  const [name, setName] = useState("");
  const [kind, setKind] = useState<TaxIdType>("rnc");
  const [value, setValue] = useState("");
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<Problem | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  // One key per number being confirmed, so a retry after a failed second step replays instead of writing twice.
  const confirmKey = useRef<{ key: string; id: string } | null>(null);
  // The workspace's source owns the read, so the sample business answers with its own name and RNC.
  const read = workspace?.source.fiscalProfile ?? getFiscalProfile;
  const write = workspace?.source.saveFiscalProfile ?? setFiscalProfile;
  const writeLegalName = workspace?.source.saveLegalName;
  useEffect(() => {
    let live = true;
    setLoadFailed(false);
    void read(draftId)
      .then((next) => {
        if (!live) return;
        setProfile(next);
        setName(restoredDraft.current?.name ?? next.name ?? "");
        setKind(restoredDraft.current?.kind ?? next.tax_id?.type ?? "rnc");
        setValue(restoredDraft.current?.value ?? next.tax_id?.value ?? "");
        restoredDraft.current = null;
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
  const digits = digitsOf(value);
  const numberValid = Boolean(value.trim()) && rules.number({ name, number: value }) === null;
  const lookupKey = `${kind}:${digits}`;
  // Only a source with the registry (the live one) answers; the local preview and the sample show no Razón social block.
  const { lookup, retry: retryLookup } = useRegistryLookup(profile?.can_edit && writeLegalName && numberValid ? { type: kind, value: digits } : null);
  const legal = profile && lookup ? legalNameState(profile, kind, digits, lookup) : null;
  const confirming = legal?.status === "pending" || (legal?.status === "inactive" && !legal.stored);

  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!profile || busy || !checks.submit()) return;
    setBusy(true);
    setSaved(false);
    setProblem(null);
    // Saving is the confirmation: the number first, then the registry's name for it.
    const confirmed = confirming && legal ? { name: legal.name, taxId: { type: kind, value: digits } } : null;
    if (confirmed && confirmKey.current?.id !== lookupKey) confirmKey.current = { key: randomId(), id: lookupKey };
    try {
      let next = profile;
      if (!unchanged) {
        next = await write(
          {
            name: name.trim(),
            previous_name: profile.name,
            tax_id: value.trim() ? { type: kind, value: value.trim() } : null,
            previous_tax_id: profile.tax_id,
          },
          randomId(),
        );
        setProfile(next);
        setName(next.name ?? "");
        setKind(next.tax_id?.type ?? kind);
        setValue(next.tax_id?.value ?? "");
        if (next.name !== profile.name) workspace?.reload();
      }
      if (confirmed && writeLegalName && confirmKey.current) {
        next = await writeLegalName(
          { legal_name: confirmed.name, previous_legal_name: next.legal_name?.value ?? null, tax_id: confirmed.taxId, confirmed: true },
          confirmKey.current.key,
        );
        setProfile(next);
        confirmKey.current = null;
      }
      checks.reset();
      setSaved(true);
    } catch (error) {
      const code = (error as { code?: string }).code;
      const known = Boolean(code) && i18n.exists(`business.dgii.error.${code}`);
      setProblem({
        text: known ? t(`business.dgii.error.${code}`) : t("business.dgii.profile_failed"),
        retry: !known,
        reference: known ? undefined : referenceCode(error),
      });
    } finally {
      setBusy(false);
    }
  };
  const unchanged =
    profile !== null &&
    name.trim() === (profile.name ?? "") &&
    (value.trim() ? digitsOf(value) : "") === (profile.tax_id?.value ?? "") &&
    (value.trim() ? kind : profile.tax_id?.type ?? kind) === (profile.tax_id?.type ?? kind);
  useEffect(() => { if(profile)onDraftChange?.({name,kind,value}); }, [profile,name,kind,value,onDraftChange]);
  useEffect(() => { onDirtyChange?.(profile !== null && !unchanged); }, [profile, unchanged, onDirtyChange]);
  const savedName = formatBusinessName(profile?.name, t("business.overview.title", "My business"));
  const businessName = name.trim() || savedName;
  const ids: Record<Field, string> = { name: `${base}-name`, number: `${base}-number` };
  const labels: Record<Field, string> = {
    name: t("business.dgii.business_name", "Business name"),
    number: t("business.dgii.tax_id_value", "Number"),
  };
  const changeKind = (next:TaxIdType)=>{setKind(next);setSaved(false);};
  const numberHint = t(kind === "rnc" ? "business.dgii.tax_id_hint_rnc" : "business.dgii.tax_id_hint_cedula");
  const taxIdTitle = profile?.tax_id?.type === "cedula" ? t("business.dgii.tax_id_cedula", "Cédula") : t("business.dgii.tax_id_rnc", "RNC");
  const saveButton = <button type="submit" form={`${base}-form`} className={footerTarget === undefined ? secondaryButtonClass : `${primaryButtonClass} h-12 w-full rounded-item`} disabled={busy || (unchanged && !confirming)}>{t(footerTarget === undefined ? "business.dgii.save_profile" : "business.settings.profile_save_changes")}</button>;
  const status = <p role="status" className={`${saved ? "" : "sr-only"} text-[14px] text-[#56635e] dark:text-white/70`}>{saved ? t("business.settings.profile_details_saved") : ""}</p>;
  const confirmLine = confirming ? <p data-testid="legal-name-confirm" className="text-[14px] leading-relaxed text-[#56635e] dark:text-white/70">{t(`business.dgii.legal_name.confirm_on_save_${kind}`, { business: businessName })}</p> : null;
  const actions = footerTarget === undefined ? <div className="flex flex-col gap-2 pt-2">{confirmLine}<div className="flex min-h-11 flex-wrap items-center gap-3">{saveButton}{status}</div></div> : <div className="flex flex-col gap-2">{status}{confirmLine}{saveButton}</div>;
  return (
    <div className="mt-[21px]" data-testid="business-fiscal-profile">
      {profile === null && !loadFailed ? <Settle pending layout="form" /> : null}
      {/* The editable fields already show the name and number; the summary line is for those who can only read. */}
      {profile && !profile.can_edit ? (
        <p className="text-[14px] text-[#56635e] dark:text-white/70">
          {savedName} · {profile.tax_id ? `${taxIdTitle} ${profile.tax_id.value}` : t("business.dgii.tax_id_none", "606 / 607 · Not applicable")}
        </p>
      ) : null}
      {profile?.can_edit ? (
        <form id={`${base}-form`} noValidate onSubmit={(event) => void save(event)} className="max-w-[34rem] space-y-[13px]">
          <ErrorSummary
            key={checks.attempt}
            title={t("common.form_summary", "Check these fields to continue:")}
            items={checks.summary.map((field) => ({ id: ids[field], label: labels[field] }))}
          />
          <FormField
            id={ids.name}
            name="business-name"
            label={<>{labels.name}<span aria-hidden="true"> *</span></>}
            required
            aria-required="true"
            placeholder={t("workspace_setup_preview.business_name_example")}
            reserveMessages={[t("business.dgii.business_name_required")]}
            error={checks.errorOf("name")}
            autoComplete="organization"
            maxLength={80}
            value={name}
            disabled={busy}
            onBlur={() => checks.blur("name")}
            onChange={(event) => {setName(event.target.value);setSaved(false);}}
          />
          <div className="grid gap-x-[13px] gap-y-[13px] tablet:grid-cols-[minmax(0,11rem)_minmax(0,1fr)]">
            {renderTaxIdControl ? renderTaxIdControl({value:kind,label:t("business.dgii.tax_id_type", "Tax id"),disabled:busy,onChange:changeKind}) : <SelectField
              id={`${base}-kind`}
              name="tax-id-type"
              label={t("business.dgii.tax_id_type", "Tax id")}
              value={kind}
              disabled={busy}
              onChange={(event) => changeKind(event.target.value as TaxIdType)}
            >
              <option value="rnc">{t("business.dgii.tax_id_rnc", "RNC")}</option>
              <option value="cedula">{t("business.dgii.tax_id_cedula", "Cédula")}</option>
            </SelectField>}
            <FormField
              id={ids.number}
              name="tax-id-value"
              label={<>{labels.number}<span className="ml-1 text-[14px] font-normal text-[#56635e] dark:text-white/70">({t("workspace_setup_preview.optional")})</span></>}
              placeholder={t(`business.dgii.tax_id_example_${kind}`)}
              hint={numberHint}
              reserveMessages={[numberHint,t("business.dgii.error.tax_id_not_digits"),t(`business.dgii.tax_id_length_${kind}`),t("business.dgii.error.tax_id_all_zero")]}
              error={checks.errorOf("number")}
              inputMode="numeric"
              autoComplete="off"
              spellCheck={false}
              maxLength={13}
              value={value}
              disabled={busy}
              onBlur={() => checks.blur("number")}
              onChange={(event) => {setValue(event.target.value);setSaved(false);}}
            />
          </div>
          {legal ? <DgiiRegistryStatus state={legal} onRetry={retryLookup} testId="legal-name" label={t("business.dgii.legal_name.label")} /> : null}
          {footerTarget === undefined ? actions : footerTarget ? createPortal(actions,footerTarget) : null}
          {problem ? (
            <div role="alert" className="flex items-start gap-2 text-[14px] leading-relaxed text-[#9e2f39] dark:text-[#ec9aa0]">
              <AlertCircle className="mt-[3px] h-4 w-4 shrink-0" aria-hidden="true" />
              <div className="min-w-0">
                <p>{problem.text}{problem.reference ? <> <ReferenceCode reference={problem.reference} /></> : null}</p>
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
