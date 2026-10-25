"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { User } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { LogoutOptions } from "@/lib/account-deletion-api";
import type { ApiUser } from "@/lib/argus-api";
import ProfileMenu from "@/components/sidebar/ProfileMenu";

export default function BusinessPhoneAccount({
  avatar,
  onLogout,
  onFeedback,
  onHistoryMutated,
  onProfileUpdated,
  onOpenSidebarPreference,
  onOpenKeyboardShortcuts,
  settingsOpenRequest = 0,
}: {
  avatar?: ReactNode;
  onLogout: (options?: LogoutOptions) => void;
  onFeedback?: (type: "bug" | "feature" | "general") => void;
  onHistoryMutated?: () => void;
  onProfileUpdated?: (user: ApiUser) => void;
  onOpenSidebarPreference?: () => void;
  onOpenKeyboardShortcuts?: () => void;
  settingsOpenRequest?: number;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const previousRequest = useRef(settingsOpenRequest);

  useEffect(() => {
    if (settingsOpenRequest === previousRequest.current) return;
    previousRequest.current = settingsOpenRequest;
    setOpen(true);
  }, [settingsOpenRequest]);

  return (
    <div className="relative" data-testid="business-phone-account">
      <ProfileMenu
        isOpen={open}
        onClose={() => setOpen(false)}
        onLogout={onLogout}
        onFeedback={onFeedback}
        onHistoryMutated={onHistoryMutated}
        onProfileUpdated={onProfileUpdated}
        onOpenSidebarPreference={onOpenSidebarPreference}
        onOpenKeyboardShortcuts={onOpenKeyboardShortcuts}
        anchorRef={buttonRef}
        placement="header"
      />
      <button
        ref={buttonRef}
        type="button"
        data-testid="header-profile-trigger"
        aria-label={t("common.settings", "Ajustes")}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        className="flex h-11 w-11 items-center justify-center rounded-full border border-black/10 bg-white text-black/70 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f5a49] dark:border-white/10 dark:bg-[#1f2225] dark:text-white/70"
      >
        {avatar ?? <User className="h-5 w-5" strokeWidth={2} aria-hidden="true" />}
      </button>
    </div>
  );
}
