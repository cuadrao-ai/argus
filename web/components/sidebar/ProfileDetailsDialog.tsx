"use client";

import { Tooltip } from "@/components/ui/Tooltip";
import { withViewportPortal } from "@/components/ui/withViewportPortal";

import { useId, useRef } from "react";
import { useTranslation } from "react-i18next";
import { Check, ChevronUp, Edit2, X } from "lucide-react";

import { useModalSurface } from "@/components/layout/useModalSurface";
import type { ApiUser } from "@/lib/argus-api";
import {
  AVATAR_THEMES,
  avatarThemeStyle,
  type AvatarTheme,
} from "@/lib/avatar-theme";
import {
  ENABLED_LANGUAGES,
  languageDisplayAbbreviation,
  normalizeEnabledLanguage,
} from "@/lib/language-features";

/* The Profile dialog. ProfileMenu owns every value it renders; the layer
 * registration is this file's own, scoped to the panel rather than the backdrop
 * so focus does not open on an invisible dismiss control. */

function profileHandle(profile: ApiUser | null) {
  const explicitUsername = profile?.username?.trim().replace(/^@+/, "");
  if (explicitUsername) return `@${explicitUsername}`;

  const emailLocalPart = profile?.email?.split("@")[0]?.trim();
  return emailLocalPart ? `@${emailLocalPart}` : null;
}

function profileInitial(profile: ApiUser | null) {
  const source =
    profile?.display_name?.trim() ||
    profile?.username?.trim() ||
    profile?.email?.trim() ||
    "A";
  return source.charAt(0).toUpperCase();
}

type ProfileDetailsDialogProps = {
  profile: ApiUser | null;
  accountKind: "guest" | "registered" | null;
  closeProfileModal: () => void;
  /** Escape while a nested picker is open closes the picker, not the dialog. */
  onEscape: () => void;
  returnFocusRef: React.RefObject<HTMLElement | null>;

  avatarClassName: string;
  avatarStyle: React.CSSProperties | undefined;
  avatarTriggerRef: React.RefObject<HTMLButtonElement | null>;
  avatarThemeDrawerRef: React.RefObject<HTMLDivElement | null>;
  isAvatarPickerOpen: boolean;
  toggleAvatarPicker: () => void;
  closeAvatarPicker: () => void;
  isSavingAvatarTheme: boolean;
  avatarThemeError: string | null;
  handleAvatarThemeSelect: (avatarTheme: AvatarTheme) => void | Promise<void>;
  handleAvatarThemeKeyDown: (
    event: React.KeyboardEvent<HTMLButtonElement>,
    currentIndex: number,
  ) => void;

  editingName: boolean;
  nameValue: string;
  setNameValue: (value: string) => void;
  /** Leaves edit mode and clears the field's error together. */
  stopEditingName: () => void;
  handleStartEditName: () => void;
  handleSaveName: () => void | Promise<void>;
  isSavingName: boolean;
  nameError: string | null;

  editingPreferredName: boolean;
  preferredNameValue: string;
  setPreferredNameValue: (value: string) => void;
  /** Leaves edit mode and clears the field's error together. */
  stopEditingPreferredName: () => void;
  handleStartEditPreferredName: () => void;
  handleSavePreferredName: () => void | Promise<void>;
  isSavingPreferredName: boolean;
  preferredNameError: string | null;

  languagePickerRef: React.RefObject<HTMLDivElement | null>;
  isLanguagePickerOpen: boolean;
  setIsLanguagePickerOpen: React.Dispatch<React.SetStateAction<boolean>>;
  currentLanguage: string;
  currentLanguageAbbreviation: string;
  handleLanguageSelect: (code: string) => void | Promise<void>;
  isSavingLanguage: boolean;
  languageError: string | null;

};

function ProfileDetailsDialogSurface({
  profile,
  accountKind,
  closeProfileModal,
  onEscape,
  returnFocusRef,
  avatarClassName,
  avatarStyle,
  avatarTriggerRef,
  avatarThemeDrawerRef,
  isAvatarPickerOpen,
  toggleAvatarPicker,
  closeAvatarPicker,
  isSavingAvatarTheme,
  avatarThemeError,
  handleAvatarThemeSelect,
  handleAvatarThemeKeyDown,
  editingName,
  nameValue,
  setNameValue,
  stopEditingName,
  handleStartEditName,
  handleSaveName,
  isSavingName,
  nameError,
  editingPreferredName,
  preferredNameValue,
  setPreferredNameValue,
  stopEditingPreferredName,
  handleStartEditPreferredName,
  handleSavePreferredName,
  isSavingPreferredName,
  preferredNameError,
  languagePickerRef,
  isLanguagePickerOpen,
  setIsLanguagePickerOpen,
  currentLanguage,
  currentLanguageAbbreviation,
  handleLanguageSelect,
  isSavingLanguage,
  languageError,
}: ProfileDetailsDialogProps) {
  const { t } = useTranslation();
  const overlayId = useId();
  const profileModalRef = useRef<HTMLDivElement>(null);

  useModalSurface({
    isOpen: true,
    overlayId,
    containerRef: profileModalRef,
    onDismiss: closeProfileModal,
    onEscape,
    returnFocusRef,
  });

  return (
    <>
      <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/25 p-4 backdrop-blur-sm dark:bg-black/60">
        <button
      tabIndex={-1}
          className="absolute inset-0"
          onClick={closeProfileModal}
          aria-label={t("settings.profile.close", "Close profile")}
        />
        <div
          ref={profileModalRef}
          className="relative w-full max-w-sm overflow-visible rounded-[18px] border border-black/5 bg-white p-5 dark:border-white/10 dark:bg-[#1b1d20]"
          role="dialog"
          aria-modal="true"
          aria-labelledby="argus-profile-modal-title"
        >
          {/* Header */}
          <div className="mb-4 flex items-center justify-between">
            <h2
              id="argus-profile-modal-title"
              className="font-display text-[16px] font-medium text-black dark:text-white"
            >
              {t("settings.profile.title", "Profile")}
            </h2>
            <button
              onClick={closeProfileModal}
              className="rounded-full p-1.5 hover:bg-black/5 dark:hover:bg-white/10"
              aria-label={t("settings.profile.close", "Close profile")}
            >
              <X className="h-4 w-4 text-black/50 dark:text-white/50" />
            </button>
          </div>

          <div className="flex flex-col gap-3">
            {/* Avatar + Name */}
            <div className="flex items-center gap-3">
              {accountKind === "registered" ? (
                <button
                  ref={avatarTriggerRef}
                  type="button"
                  onClick={toggleAvatarPicker}
                  className="group relative flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-full outline-none transition-transform hover:scale-[1.03] focus-visible:ring-2 focus-visible:ring-black/30 dark:focus-visible:ring-white/50"
                  aria-label={t(
                    "settings.profile.avatar_theme.change",
                    "Edit avatar",
                  )}
                  aria-expanded={isAvatarPickerOpen}
                  aria-controls="argus-avatar-theme-drawer"
                  data-avatar-theme-trigger
                >
                  <span
                    className={`flex h-full w-full items-center justify-center rounded-full text-[16px] font-bold ${avatarClassName}`}
                    style={avatarStyle}
                  >
                    {profileInitial(profile)}
                  </span>
                  <span
                    className="pointer-events-none absolute -bottom-0.5 -right-0.5 flex h-5 w-5 items-center justify-center rounded-full bg-white text-black ring-1 ring-black/10 dark:bg-[#2b2e33] dark:text-white dark:ring-white/15"
                    aria-hidden="true"
                  >
                    <Edit2 className="h-2.5 w-2.5" />
                  </span>
                </button>
              ) : (
                <div
                  className={`flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-full text-[16px] font-bold ${avatarClassName}`}
                  style={avatarStyle}
                >
                  {profileInitial(profile)}
                </div>
              )}
              <div className="flex min-w-0 flex-1 flex-col">
                {/* Display Name - editable */}
                {editingName ? (
                  <div className="flex items-center gap-1.5">
                    <input
                      autoFocus
                      type="text"
                      value={nameValue}
                      onChange={(e) => setNameValue(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") void handleSaveName();
                        if (e.key === "Escape") stopEditingName();
                      }}
                      disabled={isSavingName}
                      className="min-w-0 flex-1 rounded-md border border-black/15 bg-transparent px-2 py-1 text-[14px] font-medium outline-none focus:border-black/30 dark:border-white/15 dark:focus:border-white/30"
                      placeholder={t(
                        "settings.profile.display_name",
                        "Display name",
                      )}
                    />
                    <Tooltip content={t("common.save", "Save")} side="top">
                      <button
                        onClick={() => void handleSaveName()}
                        disabled={isSavingName}
                        className="rounded-md p-1 hover:bg-black/5 dark:hover:bg-white/10"
                        aria-label={t("common.save", "Save")}
                      >
                        <Check
                          className={`h-3.5 w-3.5 text-[#5ba897] ${
                            isSavingName ? "opacity-40" : ""
                          }`}
                        />
                      </button>
                    </Tooltip>
                    <Tooltip content={t("common.cancel", "Cancel")} side="top">
                      <button
                        onClick={stopEditingName}
                        disabled={isSavingName}
                        className="rounded-md p-1 hover:bg-black/5 dark:hover:bg-white/10"
                        aria-label={t("common.cancel", "Cancel")}
                      >
                        <X className="h-3.5 w-3.5 text-black/40 dark:text-white/40" />
                      </button>
                    </Tooltip>
                  </div>
                ) : (
                  <Tooltip content={t(
                      "settings.profile.edit_display_name",
                      "Edit display name",
                    )} side="top">
                    <button
                      type="button"
                      onClick={handleStartEditName}
                      className="flex min-h-11 min-w-0 items-center gap-1.5 rounded-md text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-black/20 dark:focus-visible:ring-white/25"
                      aria-label={t(
                        "settings.profile.edit_display_name",
                        "Edit display name",
                      )}
                    >
                      <span className="font-display truncate text-[15px] font-medium text-black dark:text-white">
                        {profile?.display_name ??
                          t("settings.profile.default_user", "User")}
                      </span>
                      <Edit2
                        className="h-3 w-3 shrink-0 text-black/40 dark:text-white/40"
                        aria-hidden="true"
                      />
                    </button>
                  </Tooltip>
                )}
                {nameError && (
                  <span className="mt-1 text-[12px] text-[#d66d75]">
                    {nameError}
                  </span>
                )}
                {/* Username */}
                {profileHandle(profile) && (
                  <span className="text-[13px] text-black/40 dark:text-white/40">
                    {profileHandle(profile)}
                  </span>
                )}
                <span className="text-[13px] text-black/40 dark:text-white/40">
                  {profile?.email ?? ""}
                </span>
              </div>
            </div>

            {accountKind === "registered" && (
              <div
                id="argus-avatar-theme-drawer"
                ref={avatarThemeDrawerRef}
                className={`grid transition-[grid-template-rows,margin,opacity] duration-200 ease-out motion-reduce:transition-none ${
                  isAvatarPickerOpen
                    ? "mt-0 grid-rows-[1fr] opacity-100"
                    : "mt-0 grid-rows-[0fr] opacity-0"
                }`}
                aria-hidden={!isAvatarPickerOpen}
                inert={!isAvatarPickerOpen}
              >
                <div className="min-h-0 overflow-hidden">
                  <div className="pt-1">
                    <button
                      type="button"
                      onClick={closeAvatarPicker}
                      className="flex h-11 w-full items-center gap-2 text-left outline-none focus-visible:ring-2 focus-visible:ring-black/20 dark:focus-visible:ring-white/30"
                      aria-label={t(
                        "settings.profile.avatar_theme.close",
                        "Hide avatar colors",
                      )}
                    >
                      <span className="whitespace-nowrap text-[13px] text-black/50 dark:text-white/50">
                        {t(
                          "settings.profile.avatar_theme.label",
                          "Avatar color",
                        )}
                      </span>
                      <span
                        className="h-px flex-1 bg-black/10 dark:bg-white/10"
                        aria-hidden="true"
                      />
                      <span className="text-[11px] text-black/35 dark:text-white/35">
                        {t(
                          "settings.profile.avatar_theme.hide",
                          "Hide",
                        )}
                      </span>
                      <ChevronUp
                        className="h-3.5 w-3.5 text-black/35 dark:text-white/35"
                        aria-hidden="true"
                      />
                    </button>
                    <div
                      className="grid grid-cols-8 place-items-center gap-y-2 sm:grid-cols-7"
                      role="radiogroup"
                      aria-busy={isSavingAvatarTheme || undefined}
                      aria-label={t(
                        "settings.profile.avatar_theme.label",
                        "Avatar color",
                      )}
                    >
                      {AVATAR_THEMES.map((theme, index) => {
                        const selected =
                          (profile?.avatar_theme ?? "ocean") === theme.token;
                        const themeLabel = t(
                          `settings.profile.avatar_theme.themes.${theme.token}`,
                          theme.token,
                        );
                        return (
                          <Tooltip key={theme.token} content={themeLabel} side="top">
                            <button
                              type="button"
                              role="radio"
                              aria-checked={selected}
                              aria-label={themeLabel}
                              aria-disabled={isSavingAvatarTheme || undefined}
                              onClick={() => void handleAvatarThemeSelect(theme.token)}
                              onKeyDown={(event) =>
                                handleAvatarThemeKeyDown(event, index)
                              }
                              tabIndex={selected ? 0 : -1}
                              className={`col-span-2 flex h-11 w-11 items-center justify-center rounded-full outline-none transition-transform hover:scale-105 focus-visible:ring-2 focus-visible:ring-black/30 dark:focus-visible:ring-white/50 sm:col-span-1 ${
                                isSavingAvatarTheme
                                  ? "cursor-wait opacity-60"
                                  : ""
                              } ${
                                index === 4 ? "col-start-2 sm:col-auto" : ""
                              }`}
                            >
                              <span
                                className={`flex h-9 w-9 items-center justify-center rounded-full border text-[12px] font-bold ${theme.className} ${
                                  theme.token === "ocean"
                                    ? "border-black/20 dark:border-white/20"
                                    : "border-transparent"
                                } ${
                                  selected
                                    ? "ring-2 ring-black/70 dark:ring-white/80"
                                    : ""
                                }`}
                                style={avatarThemeStyle(theme.token, "picker")}
                                aria-hidden="true"
                              >
                                {profileInitial(profile)}
                              </span>
                            </button>
                          </Tooltip>
                        );
                      })}
                    </div>
                    {avatarThemeError && (
                      <span className="mt-3 block text-[12px] text-[#d66d75]">
                        {avatarThemeError}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            )}

          {/* Its own field rather than display_name, which is an identity field.
              Optional. Neither name input caps what can be typed: the bound
              belongs to the trimmed name, and the save refuses an over-long one. */}
          {accountKind === "registered" && (
            <div className="mt-2 flex flex-col gap-1.5 border-t border-black/5 pt-3 dark:border-white/5">
              <label
                htmlFor="argus-profile-preferred-name"
                className="text-[13px] text-black/50 dark:text-white/50"
              >
                {t(
                  "settings.profile.preferred_name",
                  "What should Argus call you?",
                )}
              </label>
              {editingPreferredName ? (
                <div className="flex items-center gap-1.5">
                  <input
                    autoFocus
                    id="argus-profile-preferred-name"
                    type="text"
                    value={preferredNameValue}
                    onChange={(event) => setPreferredNameValue(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") void handleSavePreferredName();
                      if (event.key === "Escape") stopEditingPreferredName();
                    }}
                    disabled={isSavingPreferredName}
                    className="min-w-0 flex-1 rounded-md border border-black/15 bg-transparent px-2 py-1 text-[14px] outline-none focus:border-black/30 dark:border-white/15 dark:focus:border-white/30"
                    placeholder={t(
                      "settings.profile.preferred_name_placeholder",
                      "Leave blank for no name",
                    )}
                  />
                  <Tooltip content={t("common.save", "Save")} side="top">
                    <button
                      onClick={() => void handleSavePreferredName()}
                      disabled={isSavingPreferredName}
                      className="rounded-md p-1 hover:bg-black/5 dark:hover:bg-white/10"
                      aria-label={t("common.save", "Save")}
                    >
                      <Check
                        className={`h-3.5 w-3.5 text-[#5ba897] ${
                          isSavingPreferredName ? "opacity-40" : ""
                        }`}
                      />
                    </button>
                  </Tooltip>
                  <Tooltip content={t("common.cancel", "Cancel")} side="top">
                    <button
                      onClick={stopEditingPreferredName}
                      disabled={isSavingPreferredName}
                      className="rounded-md p-1 hover:bg-black/5 dark:hover:bg-white/10"
                      aria-label={t("common.cancel", "Cancel")}
                    >
                      <X className="h-3.5 w-3.5 text-black/40 dark:text-white/40" />
                    </button>
                  </Tooltip>
                </div>
              ) : (
                <button
                  id="argus-profile-preferred-name"
                  type="button"
                  onClick={handleStartEditPreferredName}
                  className="group flex min-h-11 items-center gap-1.5 rounded-md text-left outline-none focus-visible:ring-2 focus-visible:ring-black/20 dark:focus-visible:ring-white/25"
                >
                  <span
                    className={`text-[14px] ${
                      profile?.preferred_name
                        ? "text-black dark:text-white"
                        : "text-black/35 dark:text-white/35"
                    }`}
                  >
                    {profile?.preferred_name ||
                      t("settings.profile.preferred_name_unset", "Not set")}
                  </span>
                  <Edit2
                    className="h-3 w-3 text-black/40 opacity-0 transition-opacity group-hover:opacity-100 group-focus:opacity-100 dark:text-white/40"
                    aria-hidden="true"
                  />
                </button>
              )}
              {preferredNameError && (
                <span className="text-[12px] text-[#d66d75]">
                  {preferredNameError}
                </span>
              )}
            </div>
          )}

          {/* Info */}
          <div className="mt-2 flex flex-col gap-2 text-[13px]">
            <div
              ref={languagePickerRef}
              className="relative flex items-center justify-between py-1"
            >
              <span className="text-black/50 dark:text-white/50">
                {t("settings.app.language", "Language")}
              </span>
              <button
                id="argus-profile-language-trigger"
                type="button"
                onClick={() => setIsLanguagePickerOpen((open) => !open)}
                className="-mr-1 rounded-md px-1.5 py-0.5 text-black outline-none transition-colors hover:bg-black/[0.04] focus-visible:ring-2 focus-visible:ring-black/20 dark:text-white dark:hover:bg-white/[0.06] dark:focus-visible:ring-white/20"
                aria-haspopup="listbox"
                aria-expanded={isLanguagePickerOpen}
                aria-controls="argus-profile-language-picker"
                aria-label={t("settings.app.language", "App language")}
              >
                {currentLanguageAbbreviation}
              </button>
              {isLanguagePickerOpen && (
                <div
                  id="argus-profile-language-picker"
                  role="listbox"
                  aria-labelledby="argus-profile-language-trigger"
                  className="absolute right-0 top-full z-30 mt-1 min-w-[136px] rounded-[10px] border border-black/10 bg-white py-1 shadow-[0_12px_28px_rgba(0,0,0,0.12)] dark:border-white/10 dark:bg-[#23262a]"
                >
                  {ENABLED_LANGUAGES.map((entry) => {
                    const entryLanguage = normalizeEnabledLanguage(entry.code);
                    const selected = entryLanguage === currentLanguage;
                    return (
                      <button
                        key={entry.code}
                        type="button"
                        role="option"
                        aria-selected={selected}
                        onClick={() => void handleLanguageSelect(entry.code)}
                        disabled={isSavingLanguage}
                        className="flex w-full items-center justify-between gap-3 px-3 py-2 text-left text-[13px] text-black transition-colors hover:bg-black/5 disabled:cursor-wait disabled:opacity-60 dark:text-white dark:hover:bg-white/5"
                      >
                        <span>{entry.name}</span>
                        {selected ? (
                          <Check className="h-3.5 w-3.5 text-black dark:text-white" />
                        ) : (
                          <span className="text-black/35 dark:text-white/35">
                            {languageDisplayAbbreviation(entryLanguage)}
                          </span>
                        )}
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
            {languageError && (
              <span className="text-[12px] text-[#d66d75]">
                {languageError}
              </span>
            )}
          </div>

        </div>
      </div>
    </div>
    </>
  );
}

export default withViewportPortal(ProfileDetailsDialogSurface);
