"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Check, Search } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useConversationSurface } from "@/components/chat/ChatWorkspace";
import SettingsSurface, { useInSettingsWindow } from "@/components/settings/SettingsSurface";
import type { ApiUser } from "@/lib/argus-api";
import { inlineFailureTextClass } from "@/lib/failure-treatment";
import {
  BUSINESS_PREVIEW_LANGUAGE_KEY,
  ENABLED_LANGUAGES,
  normalizeEnabledLanguage,
} from "@/lib/language-features";
import { writeStored } from "@/lib/browser-storage";
import { saveProfileLanguage } from "@/lib/profile-writes";

type LanguageModalProps = {
  onClose: () => void;
  onBack?: () => void;
  backLabel?: string;
  /**
   * Where a saved profile goes. Without it there is no account to save to, so
   * the choice stays in this browser.
   */
  onProfileSaved?: (user: ApiUser) => void;
};

/** Centered blur modal with search + language list. */
export default function LanguageModal({
  onClose,
  onBack,
  backLabel,
  onProfileSaved,
}: LanguageModalProps) {
  const searchInputRef = useRef<HTMLInputElement>(null);
  const { t, i18n } = useTranslation();
  const isBusiness = useConversationSurface() === "business";
  const [searchQuery, setSearchQuery] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const lang = i18n.language || "en";
  // Inside Ajustes a pick shows its check and stays; a sheet closes on the pick.
  const inWindow = useInSettingsWindow();
  const finish = inWindow ? () => undefined : onClose;
  // A search earns its place only once the list is longer than a glance.
  const searchable = ENABLED_LANGUAGES.length > 6;

  // Closing unmounts the panel, so a save that outlives it answers to no one here.
  const editSessionRef = useRef(0);
  const endEditSession = useCallback(() => {
    editSessionRef.current += 1;
  }, []);
  useEffect(() => endEditSession, [endEditSession]);

  const filteredLanguages = useMemo(
    () =>
      ENABLED_LANGUAGES.filter(
        (entry) =>
          entry.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
          entry.translation.toLowerCase().includes(searchQuery.toLowerCase()),
      ),
    [searchQuery],
  );

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, []);

  const handleSelect = async (code: string) => {
    if (!onProfileSaved || (isBusiness && process.env.NODE_ENV === "development" && process.env.NEXT_PUBLIC_MOCK_AUTH === "true")) {
      const language = normalizeEnabledLanguage(code);
      if (isBusiness && process.env.NODE_ENV === "development" && process.env.NEXT_PUBLIC_MOCK_AUTH === "true") writeStored(BUSINESS_PREVIEW_LANGUAGE_KEY, language);
      await i18n.changeLanguage(language);
      finish();
      return;
    }
    if (isSaving) return;

    const session = editSessionRef.current;
    setIsSaving(true);
    setSaveError(null);
    const saved = await saveProfileLanguage(i18n, code, {
      onSaved: onProfileSaved,
    });
    if (session !== editSessionRef.current) return;
    setIsSaving(false);
    if (saved) {
      finish();
      return;
    }
    setSaveError(
      t("settings.profile.language_save_error", "Could not update language yet."),
    );
  };

  return (
    <SettingsSurface
      title={t("guest.shell.language", "Language")}
      closeLabel={t("settings.app.close_language_modal", "Close language modal")}
      onClose={onClose}
      onBack={onBack}
      backLabel={backLabel}
      width="sm"
      initialFocusRef={searchable ? searchInputRef : undefined}
    >
        {searchable ? <div className="flex items-center px-4 py-3 border-b border-black/5 dark:border-white/5">
          <Search className="w-4 h-4 text-black/40 dark:text-white/40 mr-3" />
          <input
            ref={searchInputRef}
            type="text"
            autoFocus
            placeholder={t("settings.search_language")}
            value={searchQuery}
            onChange={(event) => setSearchQuery(event.target.value)}
            className="w-full bg-transparent border-none outline-none text-[16px] text-black dark:text-white placeholder:text-black/35 dark:placeholder:text-white/35"
          />
        </div> : null}
        {saveError ? (
          <p
            role="alert"
            className={`px-4 pt-3 text-[12px] ${inlineFailureTextClass}`}
          >
            {saveError}
          </p>
        ) : null}
        <div
          role="radiogroup"
          aria-label={t("guest.shell.language", "Language")}
          className="max-h-[340px] overflow-y-auto p-3"
          aria-busy={isSaving || undefined}
        >
          {filteredLanguages.length === 0 ? (
            <div className="px-4 py-8 text-center text-[14px] text-black/45 dark:text-white/45">
              {t("settings.no_languages")}
            </div>
          ) : (
            filteredLanguages.map((entry) => (
              <button
                key={entry.code}
                type="button"
                role="radio"
                aria-checked={entry.code === normalizeEnabledLanguage(lang)}
                data-testid={`language-option-${entry.code}`}
                onClick={() => void handleSelect(entry.code)}
                aria-disabled={isSaving || undefined}
                className="flex min-h-11 w-full items-center justify-between rounded-item px-2 py-2.5 transition-colors hover:bg-black/5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-[var(--cuadrao-green)] aria-disabled:cursor-wait aria-disabled:opacity-60 dark:hover:bg-white/5"
              >
                <span className="text-[16px] text-black dark:text-white">
                  {entry.name}
                </span>
                {entry.code === normalizeEnabledLanguage(lang) ? (
                  <Check className="h-5 w-5 text-[var(--cuadrao-green)]" aria-hidden="true" />
                ) : !isBusiness || entry.translation !== entry.name ? (
                  <span className="text-[14px] text-black/45 dark:text-white/45">
                    {entry.translation}
                  </span>
                ) : null}
              </button>
            ))
          )}
        </div>
    </SettingsSurface>
  );
}
