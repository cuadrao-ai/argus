"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Check, Search } from "lucide-react";
import { useTranslation } from "react-i18next";
import AdaptivePanel from "@/components/ui/AdaptivePanel";
import type { ApiUser, ProfilePatch } from "@/lib/argus-api";
import { inlineFailureTextClass } from "@/lib/failure-treatment";
import {
  COUNTRY_CODES,
  CURRENCY_CODES,
  browserRegion,
  countryName,
  currencyName,
} from "@/lib/home-country";
import { normalizeEnabledLanguage } from "@/lib/language-features";
import { saveProfile } from "@/lib/profile-writes";

type HomeCountryModalProps = {
  /** The account as the menu last read it; null until that read lands. */
  profile: ApiUser | null;
  onClose: () => void;
  onBack?: () => void;
  backLabel?: string;
  onProfileSaved: (user: ApiUser) => void;
};

type Setting = "country" | "currency";

type Option = {
  /** Null is the row that clears the setting. */
  code: string | null;
  label: string;
  detail: string | null;
};

/**
 * The country the user lives in and the currency they count in. A pick saves
 * at once. The currency shown is the one the account resolves to, so a new
 * country shows the currency it implies without this panel deriving it.
 */
export default function HomeCountryModal({
  profile,
  onClose,
  onBack,
  backLabel,
  onProfileSaved,
}: HomeCountryModalProps) {
  const searchInputRef = useRef<HTMLInputElement>(null);
  const { t, i18n } = useTranslation();
  const language = normalizeEnabledLanguage(i18n.language);
  const [setting, setSetting] = useState<Setting>("country");
  const [searchQuery, setSearchQuery] = useState("");
  const [pending, setPending] = useState<ProfilePatch | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  // Closing unmounts the panel, so a save that outlives it answers to no one here.
  const editSessionRef = useRef(0);
  const endEditSession = useCallback(() => {
    editSessionRef.current += 1;
  }, []);
  useEffect(() => endEditSession, [endEditSession]);

  // A pick shows while it saves and goes back if the account refuses it.
  const country =
    pending && "country" in pending
      ? (pending.country ?? null)
      : (profile?.country ?? null);
  const currencyOverride =
    pending && "currency_override" in pending
      ? (pending.currency_override ?? null)
      : (profile?.currency_override ?? null);
  const selected = setting === "country" ? country : currencyOverride;

  const suggestedCountry = useMemo(
    () =>
      profile?.country || typeof navigator === "undefined"
        ? null
        : browserRegion(navigator.languages ?? [navigator.language]),
    [profile?.country],
  );

  const options = useMemo<Option[]>(() => {
    const byLabel = (a: Option, b: Option) => a.label.localeCompare(b.label, language);
    const listed =
      setting === "country"
        ? [
            { code: null, label: t("settings.app.no_country", "No country"), detail: null },
            ...COUNTRY_CODES.map((code) => ({
              code,
              label: countryName(code, language),
              detail:
                code === suggestedCountry
                  ? t("settings.app.suggested_country", "Suggested")
                  : null,
            })).sort(
              (a, b) =>
                Number(b.code === suggestedCountry) -
                  Number(a.code === suggestedCountry) || byLabel(a, b),
            ),
          ]
        : [
            {
              code: null,
              label: t("settings.app.currency_from_country", "Match my country"),
              detail: null,
            },
            ...CURRENCY_CODES.map((code) => ({
              code,
              label: currencyName(code, language),
              detail: code,
            })).sort(byLabel),
          ];
    const query = searchQuery.trim().toLowerCase();
    if (!query) return listed;
    return listed.filter(
      (option) =>
        option.code !== null &&
        (option.label.toLowerCase().includes(query) ||
          option.code.toLowerCase().includes(query)),
    );
  }, [language, searchQuery, setting, suggestedCountry, t]);

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, []);

  const chooseSetting = (next: Setting) => {
    if (pending) return;
    setSetting(next);
    setSearchQuery("");
    setSaveError(null);
  };

  const handleSelect = async (code: string | null) => {
    if (pending) return;
    const patch: ProfilePatch =
      setting === "country" ? { country: code } : { currency_override: code };
    const session = editSessionRef.current;
    setPending(patch);
    setSaveError(null);
    try {
      await saveProfile(patch, onProfileSaved);
      if (session !== editSessionRef.current) return;
      setSearchQuery("");
    } catch (error) {
      console.error("Failed to update home country", error);
      if (session !== editSessionRef.current) return;
      setSaveError(
        setting === "country"
          ? t("settings.profile.country_save_error", "Could not update your country yet.")
          : t("settings.profile.currency_save_error", "Could not update your currency yet."),
      );
    } finally {
      if (session === editSessionRef.current) setPending(null);
    }
  };

  const settingValue = (entry: Setting) =>
    entry === "country"
      ? country
        ? countryName(country, language)
        : t("settings.app.no_country", "No country")
      : (profile?.currency ?? t("settings.app.no_currency", "Not set"));

  return (
    <AdaptivePanel
      title={t("settings.app.home_country", "Country and currency")}
      closeLabel={t("settings.app.close_home_country", "Close country and currency")}
      onClose={onClose}
      onBack={onBack}
      backLabel={backLabel}
      width="sm"
      initialFocusRef={searchInputRef}
    >
      <div className="px-3 pt-3">
        <div className="flex items-stretch gap-1 rounded-2xl bg-black/5 p-1 dark:bg-black/35">
          {(["country", "currency"] as const).map((entry) => (
            <button
              key={entry}
              type="button"
              aria-pressed={setting === entry}
              onClick={() => chooseSetting(entry)}
              className={`flex min-w-0 flex-1 flex-col items-start rounded-xl px-3 py-2 text-left transition-colors ${
                setting === entry
                  ? "bg-white text-black dark:bg-[#32363d] dark:text-white"
                  : "text-black/55 hover:text-black dark:text-white/55 dark:hover:text-white"
              }`}
            >
              <span className="text-[12px] opacity-70">
                {entry === "country"
                  ? t("settings.app.country", "Country")
                  : t("settings.app.currency", "Currency")}
              </span>
              <span className="max-w-full truncate text-[14px] font-medium">
                {settingValue(entry)}
              </span>
            </button>
          ))}
        </div>
        <p className="px-1 pt-2 text-[12px] text-black/45 dark:text-white/45">
          {t(
            "settings.app.home_country_note",
            "When Cuadrao looks things up, it uses your country as your location.",
          )}
        </p>
      </div>
      <div className="mt-2 flex items-center border-y border-black/5 px-4 py-3 dark:border-white/5">
        <Search className="mr-3 h-4 w-4 text-black/40 dark:text-white/40" />
        <input
          ref={searchInputRef}
          type="text"
          placeholder={
            setting === "country"
              ? t("settings.app.search_country", "Search countries")
              : t("settings.app.search_currency", "Search currencies")
          }
          value={searchQuery}
          onChange={(event) => setSearchQuery(event.target.value)}
          className="w-full border-none bg-transparent text-[16px] text-black outline-none placeholder:text-black/35 dark:text-white dark:placeholder:text-white/35"
        />
      </div>
      {saveError ? (
        <p role="alert" className={`px-4 pt-3 text-[12px] ${inlineFailureTextClass}`}>
          {saveError}
        </p>
      ) : null}
      <div className="max-h-[340px] overflow-y-auto py-1" aria-busy={pending ? true : undefined}>
        {options.length === 0 ? (
          <div className="px-4 py-8 text-center text-[14px] text-black/45 dark:text-white/45">
            {setting === "country"
              ? t("settings.app.no_countries", "No countries found")
              : t("settings.app.no_currencies", "No currencies found")}
          </div>
        ) : (
          options.map((option) => (
            <button
              key={option.code ?? "none"}
              type="button"
              onClick={() => void handleSelect(option.code)}
              aria-disabled={pending ? true : undefined}
              className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left transition-colors hover:bg-black/5 aria-disabled:cursor-wait aria-disabled:opacity-60 dark:hover:bg-white/5"
            >
              <span className="text-[15px] font-medium text-black dark:text-white">
                {option.label}
              </span>
              {option.code === selected ? (
                <Check className="h-4 w-4 shrink-0 text-black dark:text-white" />
              ) : option.detail ? (
                <span className="shrink-0 text-[14px] text-black/45 dark:text-white/45">
                  {option.detail}
                </span>
              ) : null}
            </button>
          ))
        )}
      </div>
    </AdaptivePanel>
  );
}
