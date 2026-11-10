"use client";

import { type FormEvent, type ReactNode, useContext, useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { AlertCircle, Check } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  getFiscalProfile,
  setFiscalProfile,
  type FiscalProfile,
  type RegistryAnswer,
  type TaxIdType,
} from "@/lib/business-dgii";
import { randomId } from "@/lib/random-id";
import { referenceCode } from "@/lib/failure-screen";
import { ReferenceCode } from "@/components/status/ReferenceCode";
import { ErrorSummary, FormField, SelectField, useFieldChecks, type FieldRules } from "@/components/ui/FormField";
import { BusinessContext } from "./BusinessWorkspace";
import { primaryButtonClass, quietButtonClass, secondaryButtonClass } from "./business-ui";
import { Settle } from "./business-skeletons";

const LENGTH = { rnc: 9, cedula: 11 } as const;

function digitsOf(raw: string): string {
  return raw.replace(/[ -]/g, "");
}

type Field = "name" | "number";
export type FiscalProfileDraft = {name:string;kind:TaxIdType;value:string};
/** A refusal the server explains; retrying the same values cannot help. */
type Problem = { text: string; retry: boolean; reference?: string };
/** The registry check of one typed number, keyed by type and digits. */
type Lookup = { key: string } & ({ status: "checking" } | { status: "failed"; reference: string } | { status: "done"; answer: RegistryAnswer });
/** What the Razón social block shows for the typed number. */
/** `stored` is true when the name shown is the one confirmed for this number; only an unstored match asks to confirm. */
type LegalNameState =
  | { status: "checking" }
  | { status: "failed"; reference: string; name: string | null }
  | { status: "verified"; name: string }
  | { status: "pending"; name: string }
  | { status: "inactive"; name: string; registryStatus: string; stored: boolean }
  | { status: "unverified"; name: string | null };

/** The tag is always the registry's current word for the typed number. A name confirmed for that
 * number is shown in place of the registry's, and is Verificado only while the registry says verificado. */
function legalNameState(profile: FiscalProfile, kind: TaxIdType, digits: string, lookup: Lookup | null): LegalNameState {
  const stored = profile.legal_name && profile.tax_id?.type === kind && profile.tax_id.value === digits ? profile.legal_name.value : null;
  if (!lookup || lookup.key !== `${kind}:${digits}` || lookup.status === "checking") return { status: "checking" };
  if (lookup.status === "failed") return { status: "failed", reference: lookup.reference, name: stored };
  const { verification, record } = lookup.answer;
  if (!record || verification === "sin_verificar") return { status: "unverified", name: stored };
  if (verification === "no_activo") return { status: "inactive", name: stored ?? record.name, registryStatus: record.status, stored: stored !== null };
  return stored ? { status: "verified", name: stored } : { status: "pending", name: record.name };
}

const TAGS = {
  verified: "bg-[#E3EFE8] text-[#2f5a49] dark:bg-[#8fcbb0]/15 dark:text-[#8fcbb0]",
  neutral: "bg-[#EDECE6] text-[#56635e] dark:bg-white/10 dark:text-white/80",
  inactive: "bg-[#F6EBD4] text-[#7a5512] dark:bg-[#f6e7c1]/15 dark:text-[#f6e7c1]",
} as const;

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
  const [lookup, setLookup] = useState<Lookup | null>(null);
  const [lookupAttempt, setLookupAttempt] = useState(0);
  // One key per number being confirmed, so a retry after a failed second step replays instead of writing twice.
  const confirmKey = useRef<{ key: string; id: string } | null>(null);
  // The workspace's source owns the read, so the sample business answers with its own name and RNC.
  const read = workspace?.source.fiscalProfile ?? getFiscalProfile;
  const write = workspace?.source.saveFiscalProfile ?? setFiscalProfile;
  // Only a source with the registry (the live one) shows the Razón social block; the local preview and the sample have none.
  const lookupSource = workspace?.source.lookupRegistry;
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
  const registryShown = Boolean(profile?.can_edit && lookupSource && writeLegalName && numberValid);
  useEffect(() => {
    if (!registryShown || !lookupSource) return;
    const controller = new AbortController();
    setLookup({ key: lookupKey, status: "checking" });
    lookupSource({ type: kind, value: digits }, controller.signal)
      .then((answer) => { if (!controller.signal.aborted) setLookup({ key: lookupKey, status: "done", answer }); })
      .catch((error: unknown) => { if (!controller.signal.aborted) setLookup({ key: lookupKey, status: "failed", reference: referenceCode(error) }); });
    return () => controller.abort();
  }, [registryShown, lookupSource, lookupKey, kind, digits, lookupAttempt]);
  const legal = profile && registryShown ? legalNameState(profile, kind, digits, lookup) : null;
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
    name.trim() === profile.name &&
    (value.trim() ? digitsOf(value) : "") === (profile.tax_id?.value ?? "") &&
    (value.trim() ? kind : profile.tax_id?.type ?? kind) === (profile.tax_id?.type ?? kind);
  useEffect(() => { if(profile)onDraftChange?.({name,kind,value}); }, [profile,name,kind,value,onDraftChange]);
  useEffect(() => { onDirtyChange?.(profile !== null && !unchanged); }, [profile, unchanged, onDirtyChange]);
  const businessName = name.trim() || profile?.name || "";
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
          {profile.name || "-"} · {profile.tax_id ? `${taxIdTitle} ${profile.tax_id.value}` : t("business.dgii.tax_id_none", "606 / 607 · Not applicable")}
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
          {legal ? <LegalNameBlock state={legal} onRetry={() => setLookupAttempt((count) => count + 1)} /> : null}
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

function LegalNameBlock({ state, onRetry }: { state: LegalNameState; onRetry: () => void }) {
  const { t } = useTranslation();
  const labelId = useId();
  const label = <span id={labelId} className="text-[15px] font-medium">{t("business.dgii.legal_name.label")}</span>;
  if (state.status === "checking") {
    return <div data-testid="legal-name" data-legal-name-status="checking" aria-busy="true" aria-labelledby={labelId} className="space-y-1">{label}<div aria-hidden="true" className="h-5 w-2/3 animate-pulse rounded-item bg-black/5 dark:bg-white/10" /></div>;
  }
  if (state.status === "failed") {
    return <div data-testid="legal-name" data-legal-name-status="failed" className="min-w-0 space-y-1">{label}
      {state.name ? <p data-testid="legal-name-value" className="text-[16px] [overflow-wrap:anywhere]">{state.name}</p> : null}
      <div role="alert" className="flex items-start gap-2 text-[14px] leading-relaxed text-[#9e2f39] dark:text-[#ec9aa0]">
        <AlertCircle className="mt-[3px] h-4 w-4 shrink-0" aria-hidden="true" />
        <div className="min-w-0"><p>{t("common.error_occurred")} <ReferenceCode reference={state.reference} /></p><button type="button" onClick={onRetry} className={`${quietButtonClass} -ml-1`}>{t("common.retry")}</button></div>
      </div>
    </div>;
  }
  const tag = state.status === "verified"
    ? <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[12px] font-medium ${TAGS.verified}`}><Check className="h-3 w-3" aria-hidden="true" />{t("business.dgii.legal_name.tag_verified")}</span>
    : state.status === "inactive"
      ? <span className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[12px] font-medium ${TAGS.inactive}`}><span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-current" />{t("business.dgii.legal_name.tag_inactive")}</span>
      : <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[12px] font-medium ${TAGS.neutral}`}>{t(state.status === "pending" ? "business.dgii.legal_name.tag_pending" : "business.dgii.legal_name.tag_unverified")}</span>;
  // Sin verificar names no source: the registry copy is loaded by hand and can be stale.
  const source = state.status === "unverified" ? null : state.status === "inactive" ? t("business.dgii.legal_name.source_status", { status: state.registryStatus }) : t("business.dgii.legal_name.source");
  return <div data-testid="legal-name" data-legal-name-status={state.status} aria-live="polite" className="min-w-0 space-y-1">
    <div className="flex flex-wrap items-center gap-2">{label}{tag}</div>
    {state.name ? <p data-testid="legal-name-value" className="text-[16px] [overflow-wrap:anywhere]">{state.name}</p> : <p className="text-[16px] text-[#56635e] dark:text-white/70">-</p>}
    {source ? <p className="text-[14px] text-[#56635e] dark:text-white/70">{source}</p> : null}
  </div>;
}
