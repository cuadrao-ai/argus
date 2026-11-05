"use client";

import { Tooltip } from "@/components/ui/Tooltip";
import { withViewportPortal } from "@/components/ui/withViewportPortal";

import AdaptivePanel from "@/components/ui/AdaptivePanel";
import {useResponsiveLayout} from "@/components/layout/useResponsiveLayout";
import IdentityEditor from "@/components/identity/IdentityEditor";
import {SavedIdentityMark,useIdentityAppearance} from "@/components/identity/IdentityMark";
import {saveAppearance,IDENTITY_EVENT,identityPreviewEnabled} from "@/lib/identity-appearance";
import { useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { ChevronUp, Edit2, X } from "lucide-react";

import { useModalSurface } from "@/components/layout/useModalSurface";
import ProfileNameFields from "@/components/sidebar/ProfileNameFields";
import type { ApiUser } from "@/lib/argus-api";
import {
  AVATAR_THEMES,
  avatarThemeClassName,
  avatarThemeStyle,
  type AvatarTheme,
} from "@/lib/avatar-theme";

/* The Profile dialog. ProfileMenu owns every value it renders; the layer
 * registration is this file's own, scoped to the panel rather than the backdrop
 * so focus does not open on an invisible dismiss control. */

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
}: ProfileDetailsDialogProps) {
  const { t } = useTranslation();
  const overlayId = useId();
  const {isBelowDesktop} = useResponsiveLayout();
  const [editingImage,setEditingImage] = useState(false);
  const identityScope = profile?.id?`person:${profile.id}`:"";
  const savedAppearance = useIdentityAppearance(identityScope);
  const profileModalRef = useRef<HTMLDivElement>(null);

  useModalSurface({
    isOpen: !(editingImage&&isBelowDesktop),
    overlayId,
    containerRef: profileModalRef,
    onDismiss: editingImage?()=>setEditingImage(false):closeProfileModal,
    onEscape: editingImage?()=>setEditingImage(false):onEscape,
    returnFocusRef,
  });

  // eslint-disable-next-line no-restricted-syntax -- Local preview photo only; no profile API mutation.
  const imageEditor = profile ? <IdentityEditor onBack={()=>setEditingImage(false)} saved={savedAppearance??{kind:"avatar",token:profile.avatar_theme??"ocean",mark:"initials"}} name={profile.display_name??profile.email??""} onSave={appearance=>{saveAppearance(window.localStorage,identityScope,appearance);window.dispatchEvent(new Event(IDENTITY_EVENT));setEditingImage(false);}}/> : null;
  if(editingImage && profile){
    if(isBelowDesktop)return <AdaptivePanel title={t("identity.photo")} closeLabel={t("common.close")} onClose={()=>setEditingImage(false)} backLabel={t("common.back")} snaps={["full"]} initialSnap="full"><div className="p-4">{imageEditor}</div></AdaptivePanel>;
    return <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/25 p-4 dark:bg-black/60"><div ref={profileModalRef} role="dialog" aria-modal="true" aria-label={t("identity.photo")} className="max-h-[90dvh] w-full max-w-sm overflow-y-auto rounded-surface bg-white p-5 text-[#172b26] dark:bg-[#1f2225] dark:text-white"><div className="mb-4 flex items-center justify-between gap-3"><h2 className="font-display text-[24px] font-medium">{t("identity.photo")}</h2><button type="button" className="flex min-h-11 min-w-11 items-center justify-center rounded-item" aria-label={t("common.close")} onClick={()=>setEditingImage(false)}><X className="h-5 w-5"/></button></div>{imageEditor}</div></div>;
  }


  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/40 p-4 dark:bg-black/60">
      <button
        tabIndex={-1}
        className="absolute inset-0 cursor-default"
        onClick={closeProfileModal}
        aria-label={t("settings.profile.close", "Close profile")}
      />
      <div
        ref={profileModalRef}
        className="relative max-h-[calc(100dvh-2rem)] w-full max-w-[440px] overflow-y-auto rounded-surface border border-[#DCE0DA] bg-white p-6 text-[#172b26] dark:border-white/10 dark:bg-[#1b1d20] dark:text-white"
        role="dialog"
        aria-modal="true"
        aria-labelledby="argus-profile-modal-title"
      >
        <div className="mb-[21px] flex items-center justify-between gap-3">
          <h2 id="argus-profile-modal-title" className="font-display text-[21px] font-medium">
            {t("settings.profile.title", "Profile")}
          </h2>
          <button
            type="button"
            onClick={closeProfileModal}
            aria-label={t("settings.profile.close", "Close profile")}
            className="-mr-2 flex h-11 w-11 items-center justify-center rounded-full text-black/60 hover:bg-black/5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--cuadrao-green)] dark:text-white/60 dark:hover:bg-white/10"
          >
            <X className="h-5 w-5" aria-hidden="true" />
          </button>
        </div>

        <div className="flex flex-col gap-3 border-b border-[#DCE0DA] pb-[21px] dark:border-white/10">
          {/* Who this is: the avatar, the name and the email. The names are edited below. */}
          <div className="flex items-center gap-[13px]">
            {accountKind === "registered" ? (
              <button
                ref={avatarTriggerRef}
                type="button"
                onClick={identityPreviewEnabled() ? () => setEditingImage(true) : toggleAvatarPicker}
                className="group relative flex h-14 w-14 shrink-0 items-center justify-center rounded-full transition-transform hover:scale-[1.03] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--cuadrao-green)]"
                aria-label={t("settings.profile.avatar_theme.change", "Edit avatar")}
                aria-expanded={isAvatarPickerOpen}
                aria-controls="argus-avatar-theme-drawer"
                data-avatar-theme-trigger
              >
                <span className={`flex h-full w-full items-center justify-center rounded-full text-[18px] font-bold ${avatarClassName}`} style={avatarStyle}>
                  <SavedIdentityMark scope={identityScope} name={profile?.display_name ?? ""} size={56} fallback={profileInitial(profile)} />
                </span>
                <span className="pointer-events-none absolute -bottom-0.5 -right-0.5 flex h-6 w-6 items-center justify-center rounded-full bg-white text-black ring-1 ring-black/10 dark:bg-[#2b2e33] dark:text-white dark:ring-white/15" aria-hidden="true">
                  <Edit2 className="h-3 w-3" />
                </span>
              </button>
            ) : (
              <div className={`flex h-14 w-14 shrink-0 items-center justify-center rounded-full text-[18px] font-bold ${avatarClassName}`} style={avatarStyle}>
                <SavedIdentityMark scope={identityScope} name={profile?.display_name ?? ""} size={56} fallback={profileInitial(profile)} />
              </div>
            )}
            <div className="min-w-0">
              <p className="truncate text-[16px] font-medium">{profile?.display_name || t("settings.profile.default_user", "User")}</p>
              <p className="truncate text-[14px] text-[#56635e] dark:text-white/70">{profile?.email ?? ""}</p>
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
                                className={`flex h-9 w-9 items-center justify-center rounded-full border border-[var(--segment-thumb-border)] text-[12px] font-bold ${avatarThemeClassName(theme.token)} ${
                                  selected
                                    ? "ring-2 ring-black/70 dark:ring-white/80"
                                    : ""
                                }`}
                                style={avatarThemeStyle(theme.token)}
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
        </div>

        {accountKind === "registered" ? (
          <div className="pt-[21px]">
            <ProfileNameFields
              profile={profile}
              editingName={editingName}
              nameValue={nameValue}
              setNameValue={setNameValue}
              startEditName={handleStartEditName}
              saveName={handleSaveName}
              stopEditingName={stopEditingName}
              isSavingName={isSavingName}
              nameError={nameError}
              editingPreferredName={editingPreferredName}
              preferredNameValue={preferredNameValue}
              setPreferredNameValue={setPreferredNameValue}
              startEditPreferredName={handleStartEditPreferredName}
              savePreferredName={handleSavePreferredName}
              stopEditingPreferredName={stopEditingPreferredName}
              isSavingPreferredName={isSavingPreferredName}
              preferredNameError={preferredNameError}
            />
          </div>
        ) : null}
      </div>
    </div>
  );
}

export default withViewportPortal(ProfileDetailsDialogSurface);
