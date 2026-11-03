"use client";

import {
  useCallback,
  useEffect,
  useState,
  type RefObject,
} from "react";
import { ChevronDown, Loader2, RefreshCw } from "lucide-react";
import { useTranslation } from "react-i18next";
import SettingsSurface from "@/components/settings/SettingsSurface";
import { getUsageAllowances } from "@/lib/argus-api";
import {
  allowanceMeterTone,
  classifyAllowance,
  formatAllowancePeriodEnd,
  isUnboundedAllowance,
  showsHourlyWindow,
  showsWorkspaceWindow,
  type AllowanceMeterTone,
  type OperationClassAllowance,
  type UsageAllowanceResponse,
} from "@/lib/usage-allowance";

type UsageModalProps = {
  locale: "en-US" | "es-419";
  onClose: () => void;
  onBack?: () => void;
  returnFocusRef?: RefObject<HTMLElement | null>;
  backLabel?: string;
};

type AllowanceSectionProps = {
  allowance: OperationClassAllowance;
  label: string;
  locale: "en-US" | "es-419";
};

const METER_TONE_CLASS: Record<AllowanceMeterTone, string> = {
  teal: "bg-[var(--rui-color-teal)]",
  warning: "bg-[var(--rui-color-warning)]",
  danger: "bg-[var(--rui-color-danger)]",
};

function AllowanceSection({ allowance, label, locale }: AllowanceSectionProps) {
  const { t } = useTranslation();
  if (isUnboundedAllowance(allowance)) {
    // Nothing to meter: no gauge, no reset, only the label and the fact.
    return (
      <section aria-label={label}>
        <div className="flex items-baseline justify-between gap-3">
          <h3 className="text-[14px] font-medium text-black dark:text-white">
            {label}
          </h3>
          <p className="text-[13px] font-medium text-black/70 dark:text-white/75">
            {t("settings.data.usage_panel.no_limit")}
          </p>
        </div>
      </section>
    );
  }
  const state = classifyAllowance(allowance);
  const day = allowance.day;
  const hour = allowance.hour;
  const meterTone = allowanceMeterTone(allowance);
  const dayExhausted = state === "exhausted";
  const hourLimited = state === "hourly_limited";
  const workspace = allowance.guest_session;
  const workspaceLimited = workspace !== null && workspace.remaining === 0;
  const progress =
    day.limit === 0
      ? 100
      : Math.min(100, Math.round((day.used / day.limit) * 100));
  const resetDisplay = formatAllowancePeriodEnd(day.period_end, locale);

  return (
    <section aria-label={label}>
      <div className="flex items-baseline justify-between gap-3">
        <h3 className="text-[14px] font-medium text-black dark:text-white">
          {label}
        </h3>
        <p
          className={`text-[13px] font-medium ${
            dayExhausted
              ? "text-[#b94c55] dark:text-[#e7a2a8]"
              : "text-black/70 dark:text-white/75"
          }`}
        >
          {t("settings.data.usage_panel.left_today", { count: day.remaining })}
        </p>
      </div>

      <div
        className="mt-2.5 h-1 overflow-hidden rounded-full bg-black/[0.07] dark:bg-white/[0.08]"
        role="progressbar"
        aria-label={t("settings.data.usage_panel.used_of_limit", {
          used: day.used,
          limit: day.limit,
        })}
        aria-valuemin={0}
        aria-valuemax={day.limit}
        aria-valuenow={Math.min(day.used, day.limit)}
      >
        <div
          className={`h-full rounded-full transition-[width] ${METER_TONE_CLASS[meterTone]}`}
          style={{ width: `${progress}%` }}
        />
      </div>

      <p className="mt-2 text-[12px] text-black/45 dark:text-white/45">
        {t("settings.data.usage_panel.resets", { time: "" })}
        <time dateTime={day.period_end}>{resetDisplay}</time>
      </p>

      {hour !== null && showsHourlyWindow(allowance) ? (
        <p
          className={`mt-1 text-[12px] ${
            hourLimited
              ? "text-[#b94c55] dark:text-[#e7a2a8]"
              : "text-black/45 dark:text-white/45"
          }`}
        >
          {t("settings.data.usage_panel.hourly_available", {
            count: hour.remaining,
            time: "",
          })}
          <time dateTime={hour.period_end}>
            {formatAllowancePeriodEnd(hour.period_end, locale)}
          </time>
        </p>
      ) : null}

      {workspace !== null && showsWorkspaceWindow(allowance) ? (
        <p
          className={`mt-1 text-[12px] ${
            workspaceLimited
              ? "text-[#b94c55] dark:text-[#e7a2a8]"
              : "text-black/45 dark:text-white/45"
          }`}
        >
          {t("settings.data.usage_panel.workspace_available", {
            count: workspace.remaining,
            time: "",
          })}
          <time dateTime={workspace.period_end}>
            {formatAllowancePeriodEnd(workspace.period_end, locale)}
          </time>
        </p>
      ) : null}
    </section>
  );
}

export default function UsageModal({
  locale,
  onClose,
  onBack,
  backLabel,
  returnFocusRef,
}: UsageModalProps) {
  const { t } = useTranslation();
  const [usage, setUsage] = useState<UsageAllowanceResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [hasError, setHasError] = useState(false);
  const [requestVersion, setRequestVersion] = useState(0);
  const [rulesOpen, setRulesOpen] = useState(false);

  const retry = useCallback(() => {
    setRequestVersion((current) => current + 1);
  }, []);

  useEffect(() => {
    let isCurrent = true;
    setIsLoading(true);
    setHasError(false);
    getUsageAllowances()
      .then((response) => {
        if (isCurrent) setUsage(response);
      })
      .catch(() => {
        if (isCurrent) setHasError(true);
      })
      .finally(() => {
        if (isCurrent) setIsLoading(false);
      });
    return () => {
      isCurrent = false;
    };
  }, [requestVersion]);

  return (
    <SettingsSurface
      title={t("settings.data.usage_panel.title")}
      closeLabel={t("settings.data.usage_panel.close")}
      onClose={onClose}
      onBack={onBack}
      backLabel={backLabel}
      width="md"
      returnFocusRef={returnFocusRef}
    >
        <div className="overflow-y-auto px-5 pb-5" aria-live="polite">
          {isLoading ? (
            <div
              className="flex min-h-56 flex-col items-center justify-center gap-3 text-[13px] text-black/40 dark:text-white/40"
              role="status"
            >
              <Loader2 className="h-5 w-5 animate-spin" />
              {t("settings.data.usage_panel.loading")}
            </div>
          ) : hasError || !usage ? (
            <div className="flex min-h-56 flex-col items-center justify-center gap-4 text-center">
              <p className="text-[13px] text-black/50 dark:text-white/50">
                {t("settings.data.usage_panel.load_error")}
              </p>
              <button
                type="button"
                onClick={retry}
                className="flex min-h-11 items-center gap-2 rounded-xl bg-black/[0.06] px-3.5 py-2 text-[12px] font-medium text-black/70 hover:bg-black/[0.09] dark:bg-white/[0.08] dark:text-white/70 dark:hover:bg-white/[0.12]"
              >
                <RefreshCw className="h-3.5 w-3.5" />
                {t("settings.data.usage_panel.retry")}
              </button>
            </div>
          ) : (
            <>
              <div className="pt-2">
                <AllowanceSection
                  allowance={usage.allowances.compute}
                  label={t("settings.data.usage_panel.conversation")}
                  locale={locale}
                />
                <div className="my-4 border-t border-black/[0.05] dark:border-white/[0.06]" />
                <AllowanceSection
                  allowance={usage.allowances.grounding}
                  label={t("settings.data.usage_panel.searches")}
                  locale={locale}
                />
                <div className="my-4 border-t border-black/[0.05] dark:border-white/[0.06]" />
                <AllowanceSection
                  allowance={usage.allowances.execution}
                  label={t("settings.data.usage_panel.simulations")}
                  locale={locale}
                />
              </div>

              <div className="mt-5">
                <button
                  type="button"
                  onClick={() => setRulesOpen((open) => !open)}
                  aria-expanded={rulesOpen}
                  aria-controls="argus-usage-what-counts"
                  className="flex min-h-11 items-center gap-1.5 rounded-lg text-[12px] font-medium text-black/55 hover:text-black dark:text-white/55 dark:hover:text-white"
                >
                  {t("settings.data.usage_panel.what_counts")}
                  <ChevronDown
                    className={`h-3.5 w-3.5 transition-transform ${
                      rulesOpen ? "rotate-180" : ""
                    }`}
                  />
                </button>
                {rulesOpen ? (
                  <div
                    id="argus-usage-what-counts"
                    className="space-y-2 pb-1 text-[12px] leading-relaxed text-black/45 dark:text-white/45"
                  >
                    <p>{t("settings.data.usage_panel.conversation_rule")}</p>
                    <p>{t("settings.data.usage_panel.search_rule")}</p>
                    <p>{t("settings.data.usage_panel.simulation_rule")}</p>
                  </div>
                ) : null}
              </div>
            </>
          )}
        </div>
    </SettingsSurface>
  );
}
