"use client";
import { useEffect, useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { X } from "lucide-react";
import { withViewportPortal } from "@/components/ui/withViewportPortal";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import { useModalSurface } from "@/components/layout/useModalSurface";
import AdaptivePanel from "@/components/ui/AdaptivePanel";
import { FormField, useFieldChecks } from "@/components/ui/FormField";
import {
  primaryButtonClass,
  quietButtonClass,
} from "@/components/business-app/business-ui";
import IdentityEditor from "@/components/identity/IdentityEditor";
import { IdentityMark } from "@/components/identity/IdentityMark";
import {
  DEFAULT_APPEARANCE,
  parseAppearance,
  type IdentityAppearance,
} from "@/lib/identity-appearance";
import AccessRolePicker from "./AccessRolePicker";
import {
  createLocalBusiness,
  type LocalBusiness,
} from "./localBusinessPreview";
const DRAFT_KEY = "cuadrao-new-business-draft-v1";
function readDraft() {
  try {
    // eslint-disable-next-line no-restricted-syntax -- Bounded development-only identity storage; no production data.
    const saved = JSON.parse(window.localStorage.getItem(DRAFT_KEY) || "{}");
    return {
      name: typeof saved.name === "string" ? saved.name.slice(0, 80) : "",
      country: ["DO", "US", "CA"].includes(saved.country) ? saved.country : "",
      appearance: parseAppearance(saved.appearance),
    };
  } catch {
    return { name: "", country: "", appearance: DEFAULT_APPEARANCE };
  }
}
function CreateBusinessPreviewSurface({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (business: LocalBusiness) => void;
}) {
  const { t } = useTranslation(),
    { isBelowDesktop } = useResponsiveLayout(),
    id = useId();
  const [draft, setDraft] = useState(readDraft),
    [step, setStep] = useState<"details" | "image">("details"),
    [failed, setFailed] = useState(false),
    [busy, setBusy] = useState(false);
  const panel = useRef<HTMLDivElement>(null),
    submitting = useRef(false);
  const preserve = () => {
    try {
      // eslint-disable-next-line no-restricted-syntax -- Bounded development-only identity storage; no production data.
      window.localStorage.setItem(DRAFT_KEY, JSON.stringify(draft));
      return true;
    } catch {
      setFailed(true);
      return false;
    }
  };
  useEffect(() => {
    try {
      // eslint-disable-next-line no-restricted-syntax -- Bounded development-only identity storage; no production data.
      window.localStorage.setItem(DRAFT_KEY, JSON.stringify(draft));
    } catch {
      setFailed(true);
    }
  }, [draft]);
  const close = () => {
    if (busy) return;
    if (step === "image") setStep("details");
    else if (preserve()) onClose();
  };
  useModalSurface({
    isOpen: !isBelowDesktop,
    overlayId: id,
    containerRef: panel,
    onDismiss: close,
    onEscape: close,
  });
  const checks = useFieldChecks(
    {
      name: (values) =>
        values.name.trim() && values.name.trim().length <= 80
          ? null
          : t("identity.business_name_error"),
      country: (values) =>
        ["DO", "US", "CA"].includes(values.country)
          ? null
          : t("identity.country_error"),
    },
    { name: draft.name, country: draft.country },
  );
  const submit = () => {
    if (submitting.current) return;
    if (!checks.submit()) {
      requestAnimationFrame(() =>
        panel.current
          ?.querySelector<HTMLElement>('[aria-invalid="true"]')
          ?.focus(),
      );
      return;
    }
    submitting.current = true;
    setBusy(true);
    try {
      const business = createLocalBusiness(
        // eslint-disable-next-line no-restricted-syntax -- Bounded development-only identity storage; no production data.
        window.localStorage,
        draft.name,
        draft.country,
        draft.appearance,
      );
      // eslint-disable-next-line no-restricted-syntax -- Bounded development-only identity storage; no production data.
      window.localStorage.removeItem(DRAFT_KEY);
      onCreated(business);
    } catch {
      setFailed(true);
      setBusy(false);
      submitting.current = false;
    }
  };
  const content = (
    <div ref={isBelowDesktop ? panel : undefined}>
      {step === "image" ? (
        <>
          <IdentityEditor
            onBack={() => setStep("details")}
            saved={draft.appearance}
            name={draft.name}
            business
            onSave={(appearance: IdentityAppearance) => {
              setDraft({ ...draft, appearance });
              setStep("details");
            }}
          />
        </>
      ) : (
        <form
          noValidate
          onSubmit={(event) => {
            event.preventDefault();
            submit();
          }}
          className="space-y-4"
        >
          <div className="flex items-center gap-3">
            <IdentityMark
              appearance={draft.appearance}
              name={draft.name}
              business
              size={56}
            />
            <button
              type="button"
              className={quietButtonClass}
              onClick={() => setStep("image")}
            >
              {t(
                draft.appearance.kind === "default"
                  ? "identity.add_image"
                  : "identity.change_image",
              )}
            </button>
          </div>
          <FormField
            id={`${id}-name`}
            label={t("workspace_setup_preview.business_name")}
            required
            placeholder={t("identity.business_name_example")}
            autoComplete="organization"
            maxLength={80}
            value={draft.name}
            onChange={(event) =>
              setDraft({ ...draft, name: event.target.value })
            }
            onBlur={() => checks.blur("name")}
            error={checks.errorOf("name")}
          />
          <div>
            <AccessRolePicker
              id={`${id}-country`}
              value={draft.country}
              label={t("workspace_setup_preview.operating_country")}
              options={[
                {
                  value: "",
                  label: t("identity.country_choose"),
                  description: "",
                },
                ...(["DO", "US", "CA"] as const).map((value) => ({
                  value,
                  label: t(
                    `workspace_setup_preview.country_${value.toLowerCase()}`,
                  ),
                  description: "",
                })),
              ]}
              onChange={(country) => setDraft({ ...draft, country })}
              onBlur={() => checks.blur("country")}
              invalid={Boolean(checks.errorOf("country"))}
              describedBy={
                checks.errorOf("country") ? `${id}-country-error` : undefined
              }
              showDetail={false}
            />
            {checks.errorOf("country") ? (
              <p
                id={`${id}-country-error`}
                role="alert"
                className="mt-1 text-[14px] text-[#b52335] dark:text-[#ff929c]"
              >
                {checks.errorOf("country")}
              </p>
            ) : null}
          </div>
          {failed ? (
            <p
              role="alert"
              className="text-[14px] text-[#b52335] dark:text-[#ff929c]"
            >
              {t("identity.create_error")}
            </p>
          ) : null}
          <div className="border-t border-black/10 pt-4 dark:border-white/10">
            <button
              disabled={busy}
              type="submit"
              className={`${primaryButtonClass} w-full`}
            >
              {t("identity.create_business")}
            </button>
          </div>
        </form>
      )}
    </div>
  );
  const title = t(
    step === "image" ? "identity.change_image" : "business.switcher.add",
  );
  if (isBelowDesktop)
    return (
      <AdaptivePanel
        title={title}
        summary={step === "details" ? t("identity.create_detail") : undefined}
        closeLabel={t("common.close")}
        onClose={close}
        backLabel={t("common.back")}
        snaps={["full"]}
        initialSnap="full"
      >
        <div className="p-4">{content}</div>
      </AdaptivePanel>
    );
  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/25 p-4 dark:bg-black/60"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) close();
      }}
    >
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby={`${id}-title`}
        className="max-h-[90dvh] w-full max-w-lg overflow-y-auto rounded-surface bg-white p-5 text-[#172b26] dark:bg-[#1f2225] dark:text-white"
      >
        <div className="mb-4 flex items-start gap-3">
          <div className="min-w-0 flex-1">
            <h2
              id={`${id}-title`}
              className="font-display text-[24px] font-medium"
            >
              {title}
            </h2>
            {step === "details" ? (
              <p className="mt-1 text-[14px] text-[#56635e] dark:text-white/70">
                {t("identity.create_detail")}
              </p>
            ) : null}
          </div>
          <button
            type="button"
            aria-label={t("common.close")}
            className="flex min-h-11 min-w-11 items-center justify-center rounded-item hover:bg-black/5 dark:hover:bg-white/10"
            onClick={close}
          >
            <X className="h-5 w-5" />
          </button>
        </div>
        {content}
      </div>
    </div>
  );
}
export default withViewportPortal(CreateBusinessPreviewSurface);
