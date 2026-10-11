"use client";

import { useConversationSurface } from "@/components/chat/ChatWorkspace";
import Image from "next/image";
import { PanelLeft, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { ArgusLogo } from "@/components/ArgusLogo";
import { Tooltip } from "@/components/ui/Tooltip";

export type SidebarVariant = "rail" | "drawer";

export default function SidebarHeader({
  variant,
  isOpen,
  onToggle,
  onRequestClose,
}: {
  variant: SidebarVariant;
  isOpen: boolean;
  onToggle: () => void;
  onRequestClose?: () => void;
}) {
  const { t } = useTranslation();
  const isBusiness = useConversationSurface() === "business";
  const brandName = isBusiness ? "cuadrao" : "argus";
  const brandMark = (drawer = false) => isBusiness ? (
    <Image
      unoptimized
      loading="eager"
      src="/brand/cuadrao-mark-light.svg"
      width={32}
      height={32}
      alt=""
      aria-hidden="true"
      className="h-8 w-8 shrink-0"
      data-testid={drawer ? "sidebar-drawer-logo" : undefined}
    />
  ) : (
    <ArgusLogo
      className="h-8 w-8 shrink-0 text-black dark:text-white"
      aria-hidden="true"
      data-testid={drawer ? "sidebar-drawer-logo" : undefined}
    />
  );

  if (variant === "drawer") {
    return (
      <div className="flex h-20 items-center justify-between gap-2 px-3 pb-4 pt-6">
        <div className="flex min-w-0 items-center gap-2">
          {brandMark(true)}
          <span className="font-display truncate text-[22px] font-medium tracking-tight text-black dark:text-white">
            {brandName}
          </span>
        </div>
        <button
          type="button"
          onClick={onRequestClose}
          data-testid="sidebar-drawer-close"
          aria-label={t("sidebar.close", "Close sidebar")}
          className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full transition-colors hover:bg-black/5 focus-visible:outline-none focus-visible:ring-[0.125rem] focus-visible:ring-black/25 dark:hover:bg-white/5 dark:focus-visible:ring-white/30"
        >
          <X className="h-5 w-5 text-black/60 dark:text-white/60" aria-hidden="true" />
        </button>
      </div>
    );
  }

  return (
    <div className="flex h-20 items-center px-[6px] pb-4 pt-6">
      <Tooltip
        content={isOpen ? t("sidebar.close", "Close sidebar") : t("sidebar.open", "Open sidebar")}
        side="right"
        delay={150}
      >
        <button
          onClick={onToggle}
          className="flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-full transition-all duration-200 hover:bg-black/5 dark:hover:bg-white/5 active:scale-95"
          aria-label={isOpen ? "Collapse sidebar" : "Expand sidebar"}
        >
          {isOpen ? (
            <PanelLeft className="h-5 w-5 text-black/60 dark:text-white/60" />
          ) : (
            brandMark()
          )}
        </button>
      </Tooltip>
      <span
        className={`ml-1 whitespace-nowrap font-display text-[22px] font-medium tracking-tight text-black transition-[opacity,max-width] duration-300 ease-in-out dark:text-white ${
          isOpen ? "max-w-[200px] opacity-100" : "max-w-0 overflow-hidden opacity-0"
        }`}
      >
        {brandName}
      </span>
    </div>
  );
}
