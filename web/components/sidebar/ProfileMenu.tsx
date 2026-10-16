"use client";

import {
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
} from "react";
import { createPortal } from "react-dom";
import { useModalSurface } from "../layout/useModalSurface";
import { useOverlayLayer } from "../layout/overlayStack";
import ProfileDeleteRequestDialog, {
  type DeleteRequestState,
} from "./ProfileDeleteRequestDialog";
import ProfileDetailsDialog from "./ProfileDetailsDialog";
import { businessNameCopy } from "@/components/business-app/business-name-copy";
import { useBusinessNaming } from "@/components/business-app/BusinessNamingProvider";
import ProfileSettingsPanels, {
  type SettingsPanel,
} from "./ProfileSettingsPanels";
import {
  SHEET_SUBMENU_CLASS,
  profileMenuClass,
  profileSubmenuAnchorClass,
  profileSubmenuClass,
  type ProfileMenuPlacement,
} from "./profileMenuPlacement";
import {
  Activity,
  Archive,
  Brain,
  ChevronRight,
  Database,
  HelpCircle,
  Keyboard,
  Link2,
  LogOut,
  MessageSquareText,
  Palette,
  Globe,
  MapPin,
  PanelLeft,
  Shield,
  Trash2,
  User,
  FileText,
  Bug,
  Lightbulb,
  MessageCircle,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { useConversationSurface } from "@/components/chat/ChatWorkspace";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import AdaptivePanel from "@/components/ui/AdaptivePanel";
import {
  deletionEndsSession,
  requestAccountDeletion,
  type LogoutOptions,
} from "@/lib/account-deletion-api";
import { type ApiUser } from "@/lib/argus-api";
import {
  readProfile,
  saveProfile,
  saveProfileLanguage,
} from "@/lib/profile-writes";
import {
  DISPLAY_NAME_MAX_LENGTH,
  PREFERRED_NAME_MAX_LENGTH,
  normalizeProfileName,
  profileNameExceeds,
} from "@/lib/profile-names";
import {
  AVATAR_THEMES,
  avatarThemeClassName,
  avatarThemeStyle,
  type AvatarTheme,
} from "@/lib/avatar-theme";
import {
  languageDisplayAbbreviation,
  localeForLanguage,
  normalizeEnabledLanguage,
} from "@/lib/language-features";
import { memoryAvailable as fetchMemoryAvailable } from "@/lib/memory-privacy";
import { businessPilotEnabled, evidenceReceiptSharingEnabled } from "@/lib/private-alpha-flags";
import { supportEmail } from "@/lib/support-email";
import { navigateFromOverlay } from "@/lib/overlay-history";
import { QuickJumpBadge } from "@/components/keyboard/QuickJumpBadge";
import { useQuickJump } from "@/components/keyboard/useQuickJump";

// ─── Types ────────────────────────────────────────────────────────────────────

type ProfileMenuProps = {
  isOpen: boolean;
  onClose: () => void;
  onLogout: (options?: LogoutOptions) => void;
  onFeedback?: (type: "bug" | "feature" | "general") => void;
  onDeleteAllConversations?: () => void;
  onHistoryMutated?: () => void;
  /** Every successful patch reports upward, not just the fields a surface reads. */
  onProfileUpdated?: (user: ApiUser) => void;
  onOpenSidebarPreference?: () => void;
  onOpenKeyboardShortcuts?: () => void;
  /** Anchor position */
  anchorRef: React.RefObject<HTMLElement | null>;
  /** Whether the sidebar is collapsed (affects menu position) */
  sidebarCollapsed?: boolean;
  /**
   * Where the menu is opening from. The rail can afford a detached popover that
   * flies its submenus out to the right; a drawer cannot.
   */
  placement?: ProfileMenuPlacement;
};

// Derived from the panel registry, so a new settings panel needs no edit here.
type ActiveModal = null | SettingsPanel | "profile";

type SubMenu = null | "data" | "settings" | "help" | "feedback";


type ProfileQuickJumpItem = {
  id: string;
  onSelect: () => void;
};

// ─── Component ────────────────────────────────────────────────────────────────

export default function ProfileMenu({
  isOpen,
  onClose,
  onLogout,
  onFeedback,
  onDeleteAllConversations,
  onHistoryMutated,
  onProfileUpdated,
  onOpenSidebarPreference,
  onOpenKeyboardShortcuts,
  anchorRef,
  sidebarCollapsed = false,
  placement = "rail",
}: ProfileMenuProps) {
  const { t, i18n } = useTranslation();
  const isBusiness = useConversationSurface() === "business";
  const { isBelowDesktop } = useResponsiveLayout();
  /*
   * Below the panel line this menu is a sheet, whatever the sidebar is doing.
   * Tying it to the sidebar's own 720 line left the tablet band showing a
   * shrunken mouse menu whose submenus only opened on a hover that a tablet
   * cannot produce.
   */
  const asSheet = isBelowDesktop;
  const isDrawerPlacement = placement === "drawer";
  const handlePageLinkClick = useCallback(
    (event: React.MouseEvent<HTMLAnchorElement>, href: string) => {
      if (
        event.button !== 0 ||
        event.metaKey ||
        event.ctrlKey ||
        event.shiftKey ||
        event.altKey
      ) {
        return;
      }
      event.preventDefault();
      navigateFromOverlay(href, onClose);
    },
    [onClose],
  );
  const menuOverlayId = useId();
  const menuRef = useRef<HTMLDivElement>(null);
  const languagePickerRef = useRef<HTMLDivElement>(null);
  const avatarTriggerRef = useRef<HTMLButtonElement>(null);
  const avatarThemeDrawerRef = useRef<HTMLDivElement>(null);
  const [activeSubmenu, setActiveSubmenu] = useState<SubMenu>(null);
  const [activeModal, setActiveModal] = useState<ActiveModal>(null);
  const [profile, setProfile] = useState<ApiUser | null>(null);
  const [accountKind, setAccountKind] = useState<"guest" | "registered" | null>(
    null,
  );
  const [memoryControlsAvailable, setMemoryControlsAvailable] = useState(false);
  // Every receipt endpoint requires the registered-only can_save_decision
  // capability, so showing this to a guest offers a modal whose only action is a
  // retry that can never succeed.
  const receiptsAvailable =
    evidenceReceiptSharingEnabled && accountKind === "registered";
  // A country is a registered-account setting; a guest has nowhere to keep one.
  const homeCountryAvailable = !isBusiness && accountKind === "registered";
  const naming = useBusinessNaming();
  const businessNameAvailable = naming?.canEdit === true;
  const whatsappLinkAvailable = businessPilotEnabled && accountKind === "registered";
  const [editingName, setEditingName] = useState(false);
  const [nameValue, setNameValue] = useState("");
  const [isSavingName, setIsSavingName] = useState(false);
  const [nameError, setNameError] = useState<string | null>(null);
  const [editingPreferredName, setEditingPreferredName] = useState(false);
  const [preferredNameValue, setPreferredNameValue] = useState("");
  const [isSavingPreferredName, setIsSavingPreferredName] = useState(false);
  const [preferredNameError, setPreferredNameError] = useState<string | null>(
    null,
  );
  const [isLanguagePickerOpen, setIsLanguagePickerOpen] = useState(false);
  const [isSavingLanguage, setIsSavingLanguage] = useState(false);
  const [languageError, setLanguageError] = useState<string | null>(null);
  const [isSavingAvatarTheme, setIsSavingAvatarTheme] = useState(false);
  const [avatarThemeError, setAvatarThemeError] = useState<string | null>(null);
  const [isAvatarPickerOpen, setIsAvatarPickerOpen] = useState(false);
  const [isDeleteRequestOpen, setIsDeleteRequestOpen] = useState(false);
  const isMenuVisible = isOpen && activeModal === null && !isDeleteRequestOpen;
  const [deleteRequestState, setDeleteRequestState] =
    useState<DeleteRequestState>("idle");
  const [usesCommandKey, setUsesCommandKey] = useState(false);
  const submenuTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const hoverOpenedRef = useRef(false);

  const closeAvatarPicker = useCallback(() => {
    if (!isAvatarPickerOpen) return;

    setIsAvatarPickerOpen(false);
    avatarTriggerRef.current?.focus();
  }, [isAvatarPickerOpen]);

  const toggleAvatarPicker = useCallback(() => {
    if (accountKind !== "registered") return;

    if (isAvatarPickerOpen) {
      closeAvatarPicker();
      return;
    }

    setAvatarThemeError(null);
    setIsAvatarPickerOpen(true);
  }, [accountKind, closeAvatarPicker, isAvatarPickerOpen]);

  // The error renders in read mode too, so leaving an edit clears it.
  const stopEditingName = useCallback(() => {
    setEditingName(false);
    setNameError(null);
  }, []);

  const stopEditingPreferredName = useCallback(() => {
    setEditingPreferredName(false);
    setPreferredNameError(null);
  }, []);

  // Closing does not cancel a request already on the wire, and this menu stays
  // mounted, so post-await edit state is written only for the edit that began it.
  const editSessionRef = useRef(0);
  const isCurrentEditSession = useCallback(
    (session: number) => session === editSessionRef.current,
    [],
  );

  const closeProfileModal = useCallback(() => {
    setIsAvatarPickerOpen(false);
    // Per-edit state belongs to the dialog, which unmounts here.
    editSessionRef.current += 1;
    stopEditingName();
    stopEditingPreferredName();
    setNameValue("");
    setPreferredNameValue("");
    setIsSavingName(false);
    setIsSavingPreferredName(false);
    setActiveModal(null);
  }, [stopEditingName, stopEditingPreferredName]);

  // The one way a saved profile leaves this menu.
  const applyPatchedProfile = useCallback(
    (user: ApiUser) => {
      setProfile(user);
      onProfileUpdated?.(user);
    },
    [onProfileUpdated],
  );

  useEffect(() => {
    if (!isAvatarPickerOpen) return;

    const selectedTheme = avatarThemeDrawerRef.current?.querySelector<HTMLButtonElement>(
      '[role="radio"][aria-checked="true"]',
    );
    selectedTheme?.focus();
  }, [isAvatarPickerOpen]);

  // Fetch profile on open
  useEffect(() => {
    if (isOpen) {
      setNameError(null);
      setPreferredNameError(null);
      setLanguageError(null);
      // Queued too, so it cannot snapshot a row before a pending write and
      // answer after it.
      readProfile()
        .then(({ user, account_kind }) => {
          applyPatchedProfile(user);
          setAccountKind(account_kind);
        })
        .catch(() => null);
    }
  }, [applyPatchedProfile, isOpen]);

  // Reset submenu state when menu closes
  useEffect(() => {
    if (!isOpen) {
      // Don't clear submenu here — preserve for re-open persistence
    }
  }, [isOpen]);

  useEffect(() => {
    setUsesCommandKey(
      /Mac|iPhone|iPad|iPod/.test(navigator.userAgent),
    );
  }, []);

  // Memory stays invisible unless the backend exposes it to this account.
  useEffect(() => {
    if (!isOpen || accountKind !== "registered") return;
    let isCurrent = true;
    void fetchMemoryAvailable().then((available) => {
      if (isCurrent) setMemoryControlsAvailable(available);
    });
    return () => {
      isCurrent = false;
    };
  }, [isOpen, accountKind]);


  /*
   * One registration per visible surface.
   *
   * As a sheet the shell already owns the layer, the history entry and the
   * focus trap, so registering here as well gave the same panel two owners:
   * closing it scheduled two `history.back()` calls, and traversal being
   * asynchronous, that leaves a phantom entry the next press spends.
   */
  useModalSurface({
    isOpen: isMenuVisible && isDrawerPlacement && !asSheet,
    overlayId: menuOverlayId,
    containerRef: menuRef,
    onDismiss: onClose,
    // A submenu is the shallower thing on screen, so it answers first instead
    // of one press closing both levels.
    onEscape: () => {
      if (activeSubmenu) {
        setActiveSubmenu(null);
        return;
      }
      onClose();
    },
    // A menu is not modal, so it does not hold Tab itself. The registry hands
    // containment down to the nearest trapping layer instead, which inside the
    // drawer is the drawer, so Tab still cannot reach the page behind it.
    trapFocus: false,
  });

  // On the rail this is a detached popover rather than a layer, so it keeps the
  // plain dismissal rules a popover has.
  useOverlayLayer({
    isOpen: isMenuVisible && !isDrawerPlacement && !asSheet,
    overlayId: menuOverlayId,
    containerRef: menuRef,
    onEscape: onClose,
    onOutsidePointerDown: (event) => {
      if (anchorRef.current?.contains(event.target as Node)) return;
      onClose();
    },
  });

  /*
   * Escape inside the Profile dialog, which registers its own layer.
   *
   * The pickers inside it are nested state rather than layers of their own, so
   * the registry cannot see them. Defaulting Escape to onDismiss threw the
   * whole dialog away while a picker was open.
   */
  const handleProfileModalEscape = useCallback(() => {
    if (isLanguagePickerOpen) {
      setIsLanguagePickerOpen(false);
      return;
    }
    if (isAvatarPickerOpen) {
      closeAvatarPicker();
      return;
    }
    if (isDeleteRequestOpen) {
      // Deleted or locked: signed out on the result; leaving only cleans up.
      if (deletionEndsSession(deleteRequestState)) {
        onLogout({ sessionEnded: true });
      } else if (deleteRequestState !== "submitting") {
        setIsDeleteRequestOpen(false);
      }
      return;
    }
    closeProfileModal();
  }, [
    closeAvatarPicker,
    closeProfileModal,
    deleteRequestState,
    isAvatarPickerOpen,
    isDeleteRequestOpen,
    isLanguagePickerOpen,
    onLogout,
  ]);


  useEffect(() => {
    if (!isLanguagePickerOpen) return;
    const handler = (e: MouseEvent) => {
      if (languagePickerRef.current?.contains(e.target as Node)) return;
      setIsLanguagePickerOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [isLanguagePickerOpen]);

  // Submenu hover with delay and guard
  const [canOpenSubmenu, setCanOpenSubmenu] = useState(false);

  useEffect(() => {
    if (isOpen) {
      // Guard: wait 100ms before allowing submenus to open to prevent 'exploded' effect on open
      const t = setTimeout(() => setCanOpenSubmenu(true), 100);
      return () => clearTimeout(t);
    } else {
      setCanOpenSubmenu(false);
      setActiveSubmenu(null);
    }
  }, [isOpen]);

  // A tap emits mouseenter as well as click, so hover-to-open and tap-to-toggle
  // cancelled each other out and no submenu ever appeared in the drawer. Touch
  // has no hover to express intent with, so the tap is the only opener there.
  const handleSubmenuEnter = useCallback((menu: SubMenu) => {
    if (asSheet) return;
    if (!canOpenSubmenu) return;
    if (submenuTimeoutRef.current) clearTimeout(submenuTimeoutRef.current);
    hoverOpenedRef.current = true;
    setActiveSubmenu(menu);
  }, [asSheet, canOpenSubmenu]);

  /*
   * Click opens a submenu at every width; hover only ever accelerates it.
   *
   * A press on a hover-capable machine fires enter and then click, so a plain
   * toggle closed what the hover had just opened and the submenu never
   * appeared. Anything a mouse can reach only by hovering is unreachable on a
   * tablet, which stays above the panel line in landscape.
   */
  const handleSubmenuToggle = useCallback((menu: SubMenu) => {
    if (submenuTimeoutRef.current) clearTimeout(submenuTimeoutRef.current);
    if (activeSubmenu === menu) {
      if (hoverOpenedRef.current) {
        // The hover opened it a moment ago; this click confirms rather than undoes.
        hoverOpenedRef.current = false;
        return;
      }
      setActiveSubmenu(null);
      return;
    }
    hoverOpenedRef.current = false;
    setActiveSubmenu(menu);
  }, [activeSubmenu]);

  const handleSubmenuLeave = useCallback(() => {
    if (asSheet) return;
    if (submenuTimeoutRef.current) clearTimeout(submenuTimeoutRef.current);
    submenuTimeoutRef.current = setTimeout(() => setActiveSubmenu(null), 250);
  }, [asSheet]);

  const handleSubmenuKeepAlive = useCallback(() => {
    if (submenuTimeoutRef.current) clearTimeout(submenuTimeoutRef.current);
  }, []);

  const openModal = useCallback(
    (modal: ActiveModal) => {
      setActiveModal(modal);
      if (asSheet) return;
      // The popover has nowhere to sit behind a dialog, so it closes. A sheet
      // stays open underneath, which is what the child's back row returns to.
      setActiveSubmenu(null);
      onClose();
    },
    [asSheet, onClose],
  );

  const handleDeleteAllConversations = useCallback(() => {
    setActiveSubmenu(null);
    onClose();
    onDeleteAllConversations?.();
  }, [onClose, onDeleteAllConversations]);

  const handleOpenKeyboardShortcuts = useCallback(() => {
    setActiveSubmenu(null);
    onClose();
    onOpenKeyboardShortcuts?.();
  }, [onClose, onOpenKeyboardShortcuts]);

  // Profile name editing
  const handleStartEditName = useCallback(() => {
    setNameValue(profile?.display_name ?? "");
    setNameError(null);
    setEditingName(true);
  }, [profile]);

  const handleSaveName = useCallback(async () => {
    const trimmed = normalizeProfileName(nameValue);
    if (!trimmed || trimmed === profile?.display_name) {
      stopEditingName();
      return;
    }
    // Measured after trimming, and refused rather than truncated.
    if (profileNameExceeds(nameValue, DISPLAY_NAME_MAX_LENGTH)) {
      setNameError(
        t("settings.profile.display_name_too_long", {
          defaultValue: "Keep this to {{count}} characters or fewer.",
          count: DISPLAY_NAME_MAX_LENGTH,
        }),
      );
      return;
    }
    const session = editSessionRef.current;
    setIsSavingName(true);
    setNameError(null);
    try {
      // Handed on whatever the edit session: a save that outlived its dialog
      // still happened.
      await saveProfile({ display_name: trimmed }, applyPatchedProfile);
      if (isCurrentEditSession(session)) stopEditingName();
    } catch (err) {
      console.error("Failed to update display name", err);
      if (isCurrentEditSession(session)) {
        setNameError(
          t(
            "settings.profile.display_name_save_error",
            "Could not save that name yet.",
          ),
        );
      }
    } finally {
      if (isCurrentEditSession(session)) setIsSavingName(false);
    }
  }, [
    applyPatchedProfile,
    isCurrentEditSession,
    nameValue,
    profile,
    stopEditingName,
    t,
  ]);

  // A setting, never a memory: nothing infers this. Blank clears it.
  const handleSavePreferredName = useCallback(async () => {
    const trimmed = normalizeProfileName(preferredNameValue);
    const current = profile?.preferred_name ?? "";
    if (trimmed === current) {
      stopEditingPreferredName();
      return;
    }
    if (profileNameExceeds(preferredNameValue, PREFERRED_NAME_MAX_LENGTH)) {
      setPreferredNameError(
        t("settings.profile.preferred_name_too_long", {
          defaultValue: "Keep this to {{count}} characters or fewer.",
          count: PREFERRED_NAME_MAX_LENGTH,
        }),
      );
      return;
    }
    const session = editSessionRef.current;
    setIsSavingPreferredName(true);
    setPreferredNameError(null);
    try {
      await saveProfile({ preferred_name: trimmed || null }, applyPatchedProfile);
      if (isCurrentEditSession(session)) stopEditingPreferredName();
    } catch (err) {
      console.error("Failed to update preferred name", err);
      if (isCurrentEditSession(session)) {
        setPreferredNameError(
          t(
            "settings.profile.preferred_name_save_error",
            "Could not save that name yet.",
          ),
        );
      }
    } finally {
      if (isCurrentEditSession(session)) setIsSavingPreferredName(false);
    }
  }, [
    applyPatchedProfile,
    isCurrentEditSession,
    preferredNameValue,
    profile,
    stopEditingPreferredName,
    t,
  ]);

  const handleStartEditPreferredName = useCallback(() => {
    setPreferredNameValue(profile?.preferred_name ?? "");
    setPreferredNameError(null);
    setEditingPreferredName(true);
  }, [profile]);

  const currentLanguage = normalizeEnabledLanguage(
    profile?.language ?? i18n.language,
  );
  const currentLanguageAbbreviation =
    languageDisplayAbbreviation(currentLanguage);
  const avatarClassName =
    accountKind === "registered"
      ? avatarThemeClassName(profile?.avatar_theme)
      : "bg-[#191c1f] text-white dark:bg-white/10";
  const avatarStyle =
    accountKind === "registered"
      ? avatarThemeStyle(profile?.avatar_theme, "ambient")
      : undefined;
  const handleLanguageSelect = useCallback(
    async (code: string) => {
      if (isSavingLanguage) return;

      const session = editSessionRef.current;
      setIsSavingLanguage(true);
      setLanguageError(null);
      const saved = await saveProfileLanguage(i18n, code, {
        onShown: (language) =>
          setProfile((current) =>
            current
              ? { ...current, language, locale: localeForLanguage(language) }
              : current,
          ),
        onSaved: applyPatchedProfile,
      });
      setIsSavingLanguage(false);
      if (!isCurrentEditSession(session)) return;
      if (saved) {
        setIsLanguagePickerOpen(false);
        return;
      }
      setLanguageError(
        t("settings.profile.language_save_error", "Could not update language yet."),
      );
    },
    [applyPatchedProfile, i18n, isCurrentEditSession, isSavingLanguage, t],
  );

  const handleAvatarThemeSelect = useCallback(
    async (avatarTheme: AvatarTheme) => {
      if (!profile || accountKind !== "registered" || isSavingAvatarTheme) return;

      const previousTheme = profile.avatar_theme;
      const session = editSessionRef.current;
        setAvatarThemeError(null);
      setIsSavingAvatarTheme(true);
      setProfile((current) =>
        current ? { ...current, avatar_theme: avatarTheme } : current,
      );

      try {
        await saveProfile({ avatar_theme: avatarTheme }, applyPatchedProfile);
      } catch (err) {
        console.error("Failed to update avatar theme", err);
        setProfile((current) =>
          current ? { ...current, avatar_theme: previousTheme } : current,
        );
        if (isCurrentEditSession(session)) {
          setAvatarThemeError(
            t(
              "settings.profile.avatar_theme.save_error",
              "Could not update your avatar color yet.",
            ),
          );
        }
      } finally {
        setIsSavingAvatarTheme(false);
      }
    },
    [
      accountKind,
      applyPatchedProfile,
      isCurrentEditSession,
      isSavingAvatarTheme,
      profile,
      t,
    ],
  );

  const handleAvatarThemeKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLButtonElement>, currentIndex: number) => {
      if (isSavingAvatarTheme) return;

      const lastIndex = AVATAR_THEMES.length - 1;
      let nextIndex: number | null = null;

      switch (event.key) {
        case "ArrowRight":
        case "ArrowDown":
          nextIndex = currentIndex === lastIndex ? 0 : currentIndex + 1;
          break;
        case "ArrowLeft":
        case "ArrowUp":
          nextIndex = currentIndex === 0 ? lastIndex : currentIndex - 1;
          break;
        case "Home":
          nextIndex = 0;
          break;
        case "End":
          nextIndex = lastIndex;
          break;
        default:
          return;
      }

      event.preventDefault();
      avatarThemeDrawerRef.current
        ?.querySelectorAll<HTMLButtonElement>('[role="radio"]')
        [nextIndex]?.focus();
      void handleAvatarThemeSelect(AVATAR_THEMES[nextIndex].token);
    },
    [handleAvatarThemeSelect, isSavingAvatarTheme],
  );

  const handleOpenDeleteRequest = useCallback(() => {
    setDeleteRequestState("idle");
    setIsDeleteRequestOpen(true);
  }, []);

  const quickJumpItems = useMemo<ProfileQuickJumpItem[]>(() => {
    if (activeSubmenu === "data") {
      return [
        ...(memoryControlsAvailable
          ? [{ id: "memory", onSelect: () => openModal("memory") }]
          : []),
        ...(receiptsAvailable
          ? [{ id: "receipts", onSelect: () => openModal("receipts") }]
          : []),
        ...(!isBusiness ? [{ id: "archived", onSelect: () => openModal("archived") }] : []),
        { id: "deleted", onSelect: () => openModal("deleted") },
        {
          id: "security",
          onSelect: () =>
            navigateFromOverlay("/account/security", onClose),
        },
        ...(!isBusiness ? [{ id: "usage", onSelect: () => openModal("usage") }] : []),
        { id: "delete-all", onSelect: handleDeleteAllConversations },
        { id: "delete-account", onSelect: handleOpenDeleteRequest },
      ];
    }
    if (activeSubmenu === "settings") {
      return [
        { id: "appearance", onSelect: () => openModal("appearance") },
        { id: "language", onSelect: () => openModal("language") },
        ...(homeCountryAvailable
          ? [{ id: "country", onSelect: () => openModal("country") }]
          : []),
        ...(businessNameAvailable ? [{ id: "business_name", onSelect: () => openModal("business_name") }] : []),
        ...(whatsappLinkAvailable
          ? [{ id: "whatsapp", onSelect: () => openModal("whatsapp") }]
          : []),
        ...(onOpenSidebarPreference
          ? [
              {
                id: "sidebar",
                onSelect: () => {
                  onOpenSidebarPreference();
                  onClose();
                },
              },
            ]
          : []),
      ];
    }
    if (activeSubmenu === "help") {
      return [
        {
          id: "keyboard-shortcuts",
          onSelect: handleOpenKeyboardShortcuts,
        },
        ...(!isBusiness ? [
        {
          id: "terms",
          onSelect: () => navigateFromOverlay("/terms", onClose),
        },
        {
          id: "privacy",
          onSelect: () => navigateFromOverlay("/privacy", onClose),
        },
        ] : []),
      ];
    }
    if (activeSubmenu === "feedback") {
      return [
        {
          id: "feedback-bug",
          onSelect: () => {
            onFeedback?.("bug");
            onClose();
          },
        },
        {
          id: "feedback-feature",
          onSelect: () => {
            onFeedback?.("feature");
            onClose();
          },
        },
        {
          id: "feedback-general",
          onSelect: () => {
            onFeedback?.("general");
            onClose();
          },
        },
      ];
    }
    return [
      { id: "profile", onSelect: () => openModal("profile") },
      { id: "data", onSelect: () => handleSubmenuToggle("data") },
      { id: "settings", onSelect: () => handleSubmenuToggle("settings") },
      { id: "help", onSelect: () => handleSubmenuToggle("help") },
      { id: "feedback", onSelect: () => handleSubmenuToggle("feedback") },
    ];
  }, [
    activeSubmenu,
    isBusiness,
    handleDeleteAllConversations,
    handleOpenDeleteRequest,
    handleOpenKeyboardShortcuts,
    handleSubmenuToggle,
    homeCountryAvailable,
    whatsappLinkAvailable,
    businessNameAvailable,
    memoryControlsAvailable,
    receiptsAvailable,
    onClose,
    onFeedback,
    onOpenSidebarPreference,
    openModal,
  ]);
  const handleQuickJump = useCallback(
    (id: string) => {
      quickJumpItems.find((item) => item.id === id)?.onSelect();
    },
    [quickJumpItems],
  );
  const { isQuickJumpActive, numberFor } = useQuickJump({
    enabled: isMenuVisible,
    items: quickJumpItems,
    onSelect: handleQuickJump,
    usesCommandKey,
  });
  const quickJumpBadge = (id: string) => {
    const number = numberFor(id);
    return isQuickJumpActive && number !== null ? (
      <QuickJumpBadge
        number={number}
        presentation="shortcut_hint"
        usesCommandKey={usesCommandKey}
      />
    ) : null;
  };

  const handleSubmitDeleteRequest = useCallback(async () => {
    if (
      deleteRequestState === "submitting" ||
      deleteRequestState === "success" ||
      deleteRequestState === "in_progress" ||
      deleteRequestState === "requested"
    ) {
      return;
    }
    setDeleteRequestState("submitting");
    let outcome: DeleteRequestState;
    try {
      // 202 and a post-lock 503 are in_progress, never shown as done or as a
      // failure; 404 (command off here) falls back to a support ticket.
      outcome = await requestAccountDeletion(currentLanguage);
    } catch (err) {
      console.error("Account deletion failed", err);
      setDeleteRequestState("error");
      return;
    }
    setDeleteRequestState(outcome);
    // The session is dead: sign this browser out on the result itself, with
    // the dialog kept up as the signed-out confirmation.
    if (deletionEndsSession(outcome)) onLogout({ afterAccountDeletion: true });
  }, [currentLanguage, deleteRequestState, onLogout]);

  // Signed out on the result already, so Done never calls logout again: it
  // only clears this browser's state and leaves (Priya #801 note 10).
  const handleCloseDeleteRequest = useCallback(() => {
    if (deletionEndsSession(deleteRequestState)) {
      onLogout({ sessionEnded: true });
      return;
    }
    setIsDeleteRequestOpen(false);
  }, [deleteRequestState, onLogout]);

  const accountHint = profile?.email ? ` (${profile.email})` : "";
  const supportMailto = `mailto:${supportEmail}?subject=${encodeURIComponent(
    t(
      "settings.profile.request_deletion.email_subject",
      "Cuadrao account deletion request",
    ),
  )}&body=${encodeURIComponent(
    t(
      "settings.profile.request_deletion.email_body",
      "Please help me request deletion for my Cuadrao account{{account_hint}}.",
      { account_hint: accountHint },
    ),
  )}`;

  const deleteRequestDialog = isDeleteRequestOpen ? (
    <ProfileDeleteRequestDialog
      state={deleteRequestState}
      supportMailto={supportMailto}
      onClose={handleCloseDeleteRequest}
      onSubmit={handleSubmitDeleteRequest}
      returnFocusRef={anchorRef}
    />
  ) : null;

  if (!isOpen && !activeModal && !isDeleteRequestOpen) return null;

  // A child dialog replaces the settings surface, just like the other panels.
  // Keeping both mounted puts the centered request beneath the tablet sheet.
  if (deleteRequestDialog) {
    return deleteRequestDialog;
  }

  // ── Active modal rendering ──────────────────────────────────────────────
  if (activeModal !== null && activeModal !== "profile") {
    return (
      <ProfileSettingsPanels
        panel={activeModal}
        asSheet={asSheet}
        locale={localeForLanguage(
          normalizeEnabledLanguage(i18n.resolvedLanguage),
        )}
        anchorRef={anchorRef}
        onClose={() => setActiveModal(null)}
        onBack={(parent) => {
          setActiveModal(null);
          setActiveSubmenu(parent);
        }}
        onHistoryMutated={onHistoryMutated}
        onProfileSaved={applyPatchedProfile}
        profile={profile}
      />
    );
  }
  if (activeModal === "profile") {
    return (
      <ProfileDetailsDialog
        profile={profile}
        accountKind={accountKind}
        closeProfileModal={closeProfileModal}
        onEscape={handleProfileModalEscape}
        returnFocusRef={anchorRef}
        avatarClassName={avatarClassName}
        avatarStyle={avatarStyle}
        avatarTriggerRef={avatarTriggerRef}
        avatarThemeDrawerRef={avatarThemeDrawerRef}
        isAvatarPickerOpen={isAvatarPickerOpen}
        toggleAvatarPicker={toggleAvatarPicker}
        closeAvatarPicker={closeAvatarPicker}
        isSavingAvatarTheme={isSavingAvatarTheme}
        avatarThemeError={avatarThemeError}
        handleAvatarThemeSelect={handleAvatarThemeSelect}
        handleAvatarThemeKeyDown={handleAvatarThemeKeyDown}
        editingName={editingName}
        nameValue={nameValue}
        setNameValue={setNameValue}
        stopEditingName={stopEditingName}
        handleStartEditName={handleStartEditName}
        handleSaveName={handleSaveName}
        isSavingName={isSavingName}
        nameError={nameError}
        editingPreferredName={editingPreferredName}
        preferredNameValue={preferredNameValue}
        setPreferredNameValue={setPreferredNameValue}
        stopEditingPreferredName={stopEditingPreferredName}
        handleStartEditPreferredName={handleStartEditPreferredName}
        handleSavePreferredName={handleSavePreferredName}
        isSavingPreferredName={isSavingPreferredName}
        preferredNameError={preferredNameError}
        languagePickerRef={languagePickerRef}
        isLanguagePickerOpen={isLanguagePickerOpen}
        setIsLanguagePickerOpen={setIsLanguagePickerOpen}
        currentLanguage={currentLanguage}
        currentLanguageAbbreviation={currentLanguageAbbreviation}
        handleLanguageSelect={handleLanguageSelect}
        isSavingLanguage={isSavingLanguage}
        languageError={languageError}
      />
    );
  }

  if (!isOpen) return null;

  // ── Menu rendering ──────────────────────────────────────────────────────

  const { className: rawMenuClass, left: rawMenuLeft } = profileMenuClass(
    placement,
    sidebarCollapsed,
  );
  // Inside a sheet the shell is the panel, so the menu is just its rows.
  const menuClassName = asSheet
    ? "[&_button]:min-h-[44px] [&_a]:min-h-[44px]"
    : rawMenuClass;
  const menuLeft = asSheet ? undefined : rawMenuLeft;
  const submenuSurfaceClass = (railSizeClass: string) =>
    asSheet ? SHEET_SUBMENU_CLASS : profileSubmenuClass(placement, railSizeClass);
  const submenuAnchorClass = asSheet ? "" : profileSubmenuAnchorClass(placement);
  // In the sheet a submenu replaces the list rather than floating over it.
  // Drilled into a submenu, the sheet shows that submenu alone. The bodies
  // already render conditionally, so only the root-level rows need standing
  // down; moving them would mean relocating 200 lines of markup for a class.
  const showRootRows = !asSheet || !activeSubmenu;
  const rootRow = showRootRows ? "" : " hidden";
  const sheetTitles: Record<string, string> = {
    data: t("settings.data.title", "Data Controls"),
    settings: t("settings.app.title", "Preferences"),
    help: t("settings.help.title", "Help & Legal"),
    feedback: t("feedback.title", "Feedback"),
  };

  const menu = (
    <div
      ref={menuRef}
      data-profile-menu-surface
      className={menuClassName}
      style={{
        left: menuLeft,
        boxShadow: "0 8px 32px rgba(0,0,0,0.12), 0 2px 8px rgba(0,0,0,0.06)",
      }}
    >
      {/* Profile */}
      <button
        onClick={() => openModal("profile")}
        className={`font-display flex min-h-[38px] w-full items-center gap-2.5 px-3.5 py-2 text-[13px] font-medium text-black hover:bg-black/5 dark:text-white dark:hover:bg-white/5${rootRow}`}
      >
        <User className="h-4 w-4 text-black/50 dark:text-white/50" />
        {t("settings.profile.title", "Profile")}
        <span className="ml-auto flex shrink-0">{quickJumpBadge("profile")}</span>
      </button>

      {/* Data */}
      <div
        className={submenuAnchorClass}
        onMouseEnter={() => handleSubmenuEnter("data")}
        onMouseLeave={handleSubmenuLeave}
      >
        <button
          onClick={() => handleSubmenuToggle("data")}
          className={`font-display flex min-h-[38px] w-full items-center justify-between gap-2.5 px-3.5 py-2 text-[13px] font-medium text-black hover:bg-black/5 dark:text-white dark:hover:bg-white/5${rootRow}`}
        >
          <div className="flex items-center gap-2.5">
            <Database className="h-4 w-4 text-black/50 dark:text-white/50" />
            {t("settings.data.title", "Data Controls")}
          </div>
          <span className="ml-auto flex shrink-0">{quickJumpBadge("data")}</span>
          {!isQuickJumpActive && (
            <ChevronRight className="h-3.5 w-3.5 text-black/30 dark:text-white/30" />
          )}
        </button>
        {activeSubmenu === "data" && (
          <div
            className={submenuSurfaceClass("min-h-[294px] min-w-[304px]")}
            style={{ boxShadow: "0 4px 20px rgba(0,0,0,0.1)" }}
            onMouseEnter={handleSubmenuKeepAlive}
            onMouseLeave={handleSubmenuLeave}
          >
            {memoryControlsAvailable ? (
              <button
                onClick={() => openModal("memory")}
                className="flex min-h-[38px] w-full items-center gap-2.5 px-3.5 py-2 text-[13px] text-black hover:bg-black/5 dark:text-white dark:hover:bg-white/5"
              >
                <Brain className="h-3.5 w-3.5 text-black/60 dark:text-white/60" />
                <span className="whitespace-nowrap">
                  {t("settings.data.personalization.menu", "Personalization")}
                </span>
                <span className="ml-auto flex shrink-0">{quickJumpBadge("memory")}</span>
              </button>
            ) : null}
            {receiptsAvailable ? (
              <button
                onClick={() => openModal("receipts")}
                className="flex min-h-[38px] w-full items-center gap-2.5 px-3.5 py-2 text-[13px] text-black hover:bg-black/5 dark:text-white dark:hover:bg-white/5"
              >
                <Link2 className="h-3.5 w-3.5 text-black/60 dark:text-white/60" />
                <span className="whitespace-nowrap">
                  {t("settings.data.shared_links", "Shared links")}
                </span>
                <span className="ml-auto flex shrink-0">
                  {quickJumpBadge("receipts")}
                </span>
              </button>
            ) : null}
            {!isBusiness && (
            <button
              onClick={() => openModal("archived")}
              className="flex min-h-[38px] w-full items-center gap-2.5 px-3.5 py-2 text-[13px] text-black hover:bg-black/5 dark:text-white dark:hover:bg-white/5"
            >
              <Archive className="h-3.5 w-3.5 text-black/60 dark:text-white/60" />
              <span className="whitespace-nowrap">
                {t("settings.data.archived_chats", "Archived chats")}
              </span>
              <span className="ml-auto flex shrink-0">{quickJumpBadge("archived")}</span>
            </button>
            )}
            <button
              onClick={() => openModal("deleted")}
              className="flex min-h-[38px] w-full items-center gap-2.5 px-3.5 py-2 text-[13px] text-black hover:bg-black/5 dark:text-white dark:hover:bg-white/5"
            >
              <Trash2 className="h-3.5 w-3.5 text-black/60 dark:text-white/60" />
              <span className="whitespace-nowrap">
                {t("settings.data.recently_deleted", "Recently Deleted")}
              </span>
              <span className="ml-auto flex shrink-0">{quickJumpBadge("deleted")}</span>
            </button>
            <button
              onClick={() =>
                navigateFromOverlay("/account/security", onClose)
              }
              className="flex min-h-[38px] w-full items-center gap-2.5 px-3.5 py-2 text-[13px] text-black hover:bg-black/5 dark:text-white dark:hover:bg-white/5"
            >
              <Shield className="h-3.5 w-3.5 text-black/60 dark:text-white/60" />
              <span className="whitespace-nowrap">
                {t("settings.data.security", "Security")}
              </span>
              <span className="ml-auto flex shrink-0">{quickJumpBadge("security")}</span>
            </button>
            {!isBusiness && (
            <button
              onClick={() => openModal("usage")}
              className="flex min-h-11 w-full items-center gap-2.5 px-3.5 py-2 text-[13px] text-black hover:bg-black/5 dark:text-white dark:hover:bg-white/5"
            >
              <Activity className="h-3.5 w-3.5 text-black/60 dark:text-white/60" />
              <span className="whitespace-nowrap">
                {t("settings.data.usage", "Usage")}
              </span>
              <span className="ml-auto flex shrink-0">{quickJumpBadge("usage")}</span>
            </button>
            )}
            <div role="separator" className="my-1 border-t border-black/5 dark:border-white/5" />
            <button
              onClick={handleDeleteAllConversations}
              className="flex min-h-[38px] w-full items-center gap-2.5 px-3.5 py-2 text-[13px] font-medium text-[#d66d75] transition-colors hover:bg-[#d66d75]/10 dark:hover:bg-[#d66d75]/10"
            >
              <Trash2 className="h-3.5 w-3.5" />
              <span className="whitespace-nowrap">
                {t("settings.data.delete_all_conversations", "Delete all conversations")}
              </span>
              <span className="ml-auto flex shrink-0">{quickJumpBadge("delete-all")}</span>
            </button>
            <button
              type="button"
              onClick={handleOpenDeleteRequest}
              className="flex min-h-[88px] w-full flex-col items-start gap-1 px-3.5 py-2 text-left text-[#d66d75] transition-colors hover:bg-[#d66d75]/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#d66d75]/25 dark:hover:bg-[#d66d75]/10"
            >
              <span className="flex h-[22px] w-full items-center gap-2.5 text-[13px] font-medium">
                <Trash2 className="h-3.5 w-3.5" />
                <span className="whitespace-nowrap">
                  {t("settings.profile.delete_account", "Delete account")}
                </span>
                <span className="ml-auto flex shrink-0">{quickJumpBadge("delete-account")}</span>
              </span>
              <span className="pl-6 text-[11px] leading-snug text-black/35 dark:text-white/35">
                {t(
                  "settings.profile.delete_account_note",
                  "Permanently delete your Cuadrao account and your data.",
                )}
              </span>
            </button>
          </div>
        )}
      </div>

      {/* Preferences */}
      <div
        className={submenuAnchorClass}
        onMouseEnter={() => handleSubmenuEnter("settings")}
        onMouseLeave={handleSubmenuLeave}
      >
        <button
          onClick={() => handleSubmenuToggle("settings")}
          className={`font-display flex min-h-[38px] w-full items-center justify-between gap-2.5 px-3.5 py-2 text-[13px] font-medium text-black hover:bg-black/5 dark:text-white dark:hover:bg-white/5${rootRow}`}
        >
          <div className="flex items-center gap-2.5">
            <Palette className="h-4 w-4 text-black/50 dark:text-white/50" />
            {t("settings.preferences.title", "Preferences")}
          </div>
          <span className="ml-auto flex shrink-0">{quickJumpBadge("settings")}</span>
          {!isQuickJumpActive && (
            <ChevronRight className="h-3.5 w-3.5 text-black/30 dark:text-white/30" />
          )}
        </button>
        {activeSubmenu === "settings" && (
          <div
            aria-label={t("settings.preferences.title", "Preferences")}
            className={submenuSurfaceClass("min-w-[248px]")}
            style={{ boxShadow: "0 4px 20px rgba(0,0,0,0.1)" }}
            onMouseEnter={handleSubmenuKeepAlive}
            onMouseLeave={handleSubmenuLeave}
          >
            <button
              onClick={() => openModal("appearance")}
              className="flex min-h-[38px] w-full items-center gap-2.5 px-3.5 py-2 text-[13px] text-black hover:bg-black/5 dark:text-white dark:hover:bg-white/5"
            >
              <Palette className="h-3.5 w-3.5 text-black/60 dark:text-white/60" />
              <span className="whitespace-nowrap">
                {t("settings.app.appearance", "Appearance")}
              </span>
              <span className="ml-auto flex shrink-0">{quickJumpBadge("appearance")}</span>
            </button>
            <button
              onClick={() => openModal("language")}
              className="flex min-h-[38px] w-full items-center gap-2.5 px-3.5 py-2 text-[13px] text-black hover:bg-black/5 dark:text-white dark:hover:bg-white/5"
            >
              <Globe className="h-3.5 w-3.5 text-black/60 dark:text-white/60" />
              <span className="whitespace-nowrap">
                {t("settings.app.language", "Language")}
              </span>
              <span className="ml-auto flex shrink-0">{quickJumpBadge("language")}</span>
            </button>
            {homeCountryAvailable && (
              <button
                onClick={() => openModal("country")}
                className="flex min-h-[38px] w-full items-center gap-2.5 px-3.5 py-2 text-[13px] text-black hover:bg-black/5 dark:text-white dark:hover:bg-white/5"
              >
                <MapPin className="h-3.5 w-3.5 text-black/60 dark:text-white/60" />
                <span className="whitespace-nowrap">
                  {t("settings.app.home_country", "Country and currency")}
                </span>
                <span className="ml-auto flex shrink-0">{quickJumpBadge("country")}</span>
              </button>
            )}
            {businessNameAvailable && (
              <button onClick={() => openModal("business_name")} className="flex min-h-11 w-full items-center gap-2.5 px-3.5 py-2 text-[13px] text-black hover:bg-black/5 dark:text-white dark:hover:bg-white/5">
                <span>{businessNameCopy.title}</span>
                <span className="ml-auto flex shrink-0">{quickJumpBadge("business_name")}</span>
              </button>
            )}
            {whatsappLinkAvailable && (
              <button
                onClick={() => openModal("whatsapp")}
                className="flex min-h-[38px] w-full items-center gap-2.5 px-3.5 py-2 text-[13px] text-black hover:bg-black/5 dark:text-white dark:hover:bg-white/5"
              >
                <MessageCircle className="h-3.5 w-3.5 text-black/60 dark:text-white/60" />
                <span className="whitespace-nowrap">
                  {t("settings.whatsapp.title", "WhatsApp")}
                </span>
                <span className="ml-auto flex shrink-0">{quickJumpBadge("whatsapp")}</span>
              </button>
            )}
            {onOpenSidebarPreference && (
              <button
                onClick={() => {
                  onOpenSidebarPreference();
                  onClose();
                }}
                className="flex min-h-[38px] w-full items-center gap-2.5 px-3.5 py-2 text-[13px] text-black hover:bg-black/5 dark:text-white dark:hover:bg-white/5"
              >
                <PanelLeft className="h-3.5 w-3.5 text-black/60 dark:text-white/60" />
                <span className="whitespace-nowrap">
                  {t("settings.app.sidebar", "Sidebar")}
                </span>
                <span className="ml-auto flex shrink-0">{quickJumpBadge("sidebar")}</span>
              </button>
            )}
          </div>
        )}
      </div>

      {/* Help */}
      <div
        className={submenuAnchorClass}
        onMouseEnter={() => handleSubmenuEnter("help")}
        onMouseLeave={handleSubmenuLeave}
      >
        <button
          onClick={() => handleSubmenuToggle("help")}
          className={`font-display flex min-h-[38px] w-full items-center justify-between gap-2.5 px-3.5 py-2 text-[13px] font-medium text-black hover:bg-black/5 dark:text-white dark:hover:bg-white/5${rootRow}`}
        >
          <div className="flex items-center gap-2.5">
            <HelpCircle className="h-4 w-4 text-black/50 dark:text-white/50" />
            {t("settings.help.title", "Help & Legal")}
          </div>
          <span className="ml-auto flex shrink-0">{quickJumpBadge("help")}</span>
          {!isQuickJumpActive && (
            <ChevronRight className="h-3.5 w-3.5 text-black/30 dark:text-white/30" />
          )}
        </button>
        {activeSubmenu === "help" && (
          <div
            className={`${submenuSurfaceClass("min-w-[248px]")} [&>a]:mx-1 [&>a]:my-0.5 [&>a]:w-[calc(100%-0.5rem)] [&>a]:rounded-[10px]`}
            style={{ boxShadow: "0 4px 20px rgba(0,0,0,0.1)" }}
            onMouseEnter={handleSubmenuKeepAlive}
            onMouseLeave={handleSubmenuLeave}
          >
            {/* A phone has no keyboard to shortcut, so it is not offered there. */}
            {isDrawerPlacement ? null : (
            <button
              type="button"
              onClick={handleOpenKeyboardShortcuts}
              className="flex min-h-[38px] w-full items-center gap-2.5 px-3.5 py-2 text-[13px] text-black transition-colors hover:bg-black/5 dark:text-white dark:hover:bg-white/5"
            >
              <Keyboard className="h-3.5 w-3.5" />
              <span className="whitespace-nowrap">
                {t("keyboard_shortcuts.menu_item", "Keyboard shortcuts")}
              </span>
              <span className="ml-auto flex shrink-0">{quickJumpBadge("keyboard-shortcuts")}</span>
            </button>
            )}
            {!isBusiness && <>
            <a
              href="/terms"
              onClick={(event) => handlePageLinkClick(event, "/terms")}
              className="flex min-h-[38px] w-full items-center gap-2.5 px-3.5 py-2 text-[13px] text-black transition-colors hover:bg-black/5 dark:text-white dark:hover:bg-white/5"
            >
              <FileText className="h-3.5 w-3.5" />
              <span className="whitespace-nowrap">
                {t("settings.help.terms", "Terms of Use")}
              </span>
              <span className="ml-auto flex shrink-0">{quickJumpBadge("terms")}</span>
            </a>
            <a
              href="/privacy"
              onClick={(event) => handlePageLinkClick(event, "/privacy")}
              className="flex min-h-[38px] w-full items-center gap-2.5 px-3.5 py-2 text-[13px] text-black transition-colors hover:bg-black/5 dark:text-white dark:hover:bg-white/5"
            >
              <Shield className="h-3.5 w-3.5" />
              <span className="whitespace-nowrap">
                {t("settings.help.privacy", "Privacy Policy")}
              </span>
              <span className="ml-auto flex shrink-0">{quickJumpBadge("privacy")}</span>
            </a>
            </>}
          </div>
        )}
      </div>

      {/* Feedback */}
      <div
        className={submenuAnchorClass}
        onMouseEnter={() => handleSubmenuEnter("feedback")}
        onMouseLeave={handleSubmenuLeave}
      >
        <button
          onClick={() => handleSubmenuToggle("feedback")}
          className={`font-display flex min-h-[38px] w-full items-center justify-between gap-2.5 px-3.5 py-2 text-[13px] font-medium text-black hover:bg-black/5 dark:text-white dark:hover:bg-white/5${rootRow}`}
        >
          <div className="flex items-center gap-2.5">
            <MessageSquareText className="h-4 w-4 text-black/50 dark:text-white/50" />
            {t("feedback.eyebrow", "Feedback")}
          </div>
          <span className="ml-auto flex shrink-0">{quickJumpBadge("feedback")}</span>
          {!isQuickJumpActive && (
            <ChevronRight className="h-3.5 w-3.5 text-black/30 dark:text-white/30" />
          )}
        </button>
        {activeSubmenu === "feedback" && (
          <div
            className={submenuSurfaceClass("min-w-[248px]")}
            style={{ boxShadow: "0 4px 20px rgba(0,0,0,0.1)" }}
            onMouseEnter={handleSubmenuKeepAlive}
            onMouseLeave={handleSubmenuLeave}
          >
            <button
              onClick={() => {
                onFeedback?.("bug");
                onClose();
              }}
              className="flex min-h-[38px] w-full items-center gap-2.5 px-3.5 py-2 text-[13px] text-black hover:bg-black/5 dark:text-white dark:hover:bg-white/5"
            >
              <Bug className="h-3.5 w-3.5" />
              <span className="whitespace-nowrap">
                {t("feedback.type.bug", "Report a bug")}
              </span>
              <span className="ml-auto flex shrink-0">{quickJumpBadge("feedback-bug")}</span>
            </button>
            <button
              onClick={() => {
                onFeedback?.("feature");
                onClose();
              }}
              className="flex min-h-[38px] w-full items-center gap-2.5 px-3.5 py-2 text-[13px] text-black hover:bg-black/5 dark:text-white dark:hover:bg-white/5"
            >
              <Lightbulb className="h-3.5 w-3.5" />
              <span className="whitespace-nowrap">
                {t("feedback.type.feature", "Request a feature")}
              </span>
              <span className="ml-auto flex shrink-0">{quickJumpBadge("feedback-feature")}</span>
            </button>
            <button
              onClick={() => {
                onFeedback?.("general");
                onClose();
              }}
              className="flex min-h-[38px] w-full items-center gap-2.5 px-3.5 py-2 text-[13px] text-black hover:bg-black/5 dark:text-white dark:hover:bg-white/5"
            >
              <MessageCircle className="h-3.5 w-3.5" />
              <span className="whitespace-nowrap">
                {t("feedback.type.general", "General feedback")}
              </span>
              <span className="ml-auto flex shrink-0">{quickJumpBadge("feedback-general")}</span>
            </button>
          </div>
        )}
      </div>

      {/* Divider */}
      <div className={`my-1 border-t border-black/5 dark:border-white/5${rootRow}`} />

      {/* Log out */}
      <button
        onClick={() => {
          onLogout();
          onClose();
        }}
        className={`font-display flex w-full items-center gap-2.5 px-3.5 py-2 text-[13px] font-medium text-[#d66d75] hover:bg-black/5 dark:hover:bg-white/5${rootRow}`}
      >
        <LogOut className="h-4 w-4" />
        {t("settings.logout", "Log out")}
      </button>

      {!isBusiness && <>
      {/* Footer links */}
      <div className={`my-1 border-t border-black/5 dark:border-white/5${rootRow}`} />
      <div className={`flex items-center gap-1 px-3.5 py-1.5 text-[10px] text-black/25 dark:text-white/25${rootRow}`}>
        <a
          href="/terms"
          onClick={(event) => handlePageLinkClick(event, "/terms")}
          className="transition-colors hover:text-black dark:hover:text-white"
        >
          {t("settings.help.terms", "Terms of Use")}
        </a>
        <span aria-hidden="true">·</span>
        <a
          href="/privacy"
          onClick={(event) => handlePageLinkClick(event, "/privacy")}
          className="transition-colors hover:text-black dark:hover:text-white"
        >
          {t("settings.help.privacy", "Privacy Policy")}
        </a>
      </div>
      </>}
    </div>
  );

  if (typeof document === "undefined") return null;

  if (asSheet) {
    // The sheet supplies the panel, the title and the way back, so the menu
    // contributes only its rows.
    const sheet = (
      <AdaptivePanel
        title={
          activeSubmenu
            ? sheetTitles[activeSubmenu]
            : t("common.settings", "Settings")
        }
        closeLabel={t("common.close", "Close")}
        onClose={onClose}
        onBack={activeSubmenu ? () => setActiveSubmenu(null) : undefined}
        backLabel={t("common.settings", "Settings")}
      >
        {menu}
      </AdaptivePanel>
    );
    return sheet;
  }

  return isDrawerPlacement ? menu : createPortal(menu, document.body);
}
