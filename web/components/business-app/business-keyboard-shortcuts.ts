"use client";

import { useTranslation } from "react-i18next";
import type { WorkspaceKeyboardShortcut } from "@/lib/keyboard-shortcuts";
import type { GrantedSpace } from "@/lib/business-api";
import type { BusinessActions } from "./business-actions";
import type { BusinessPanelState } from "./BusinessWorkspace";
import { useRunReviewShortcut } from "./BusinessReviewShortcuts";

export const BUSINESS_SECTIONS = ["overview", "inbox", "expenses", "updates"] as const;
export function useBusinessKeyboardShortcuts({ openPanel, actions, chosen }: { openPanel: (panel: BusinessPanelState) => void; actions: BusinessActions; chosen: GrantedSpace | null }): readonly WorkspaceKeyboardShortcut[] {
  const { t, i18n } = useTranslation();
  const spanish = (i18n.resolvedLanguage ?? i18n.language).startsWith("es");
  const review = useRunReviewShortcut();
  const label = (approved: string, key: string, fallback: string) => spanish ? approved : t(key, fallback);
  return [
    { id: "approve", label: label("Aprobar", "business.dossier.approve", "Approve expense"), code: "Enter", keyLabel: "Enter", shift: true, run: () => review("approve") },
    { id: "approve_next", label: t("business.dossier.approve_next", "Approve and next"), code: "KeyS", keyLabel: "S", shift: true, run: () => review("approve_next") },
    { id: "previous", label: spanish ? "Recibo anterior" : `${t("business.review.title", "Review receipt")} ↑`, code: "ArrowUp", keyLabel: "↑", shift: true, run: () => review("previous") },
    { id: "next", label: spanish ? "Recibo siguiente" : `${t("business.review.title", "Review receipt")} ↓`, code: "ArrowDown", keyLabel: "↓", shift: true, run: () => review("next") },
    { id: "edit", label: label("Editar dato", "business.dossier.edit", "Edit details"), code: "KeyE", keyLabel: "E", shift: true, run: () => review("edit") },
    { id: "upload", label: t("business.actions.upload_receipt", "Upload receipt"), code: "Period", keyLabel: ".", shift: true, run: () => { const action = chosen?.role === "owner" ? actions.create.find((action) => action.id === "upload_receipt") : undefined; action?.run(); return Boolean(action); } },
    ...BUSINESS_SECTIONS.map((section, index) => ({ id: section, label: spanish ? `Ir a ${t(`business.nav.${section}`)}` : t(`business.nav.${section}`), code: `Digit${index + 1}`, keyLabel: String(index + 1), jumpIndex: index, run: () => { openPanel({ kind: section }); return true; } })),
    { id: "search", label: t("common.search", "Search"), code: "KeyK", keyLabel: "K" },
    { id: "keyboard_shortcuts", label: t("keyboard_shortcuts.title", "Keyboard shortcuts"), code: "Slash", keyLabel: "/" },
    { id: "sidebar", label: label("Mostrar u ocultar barra lateral", "settings.app.sidebar", "Sidebar"), code: "Backslash", keyLabel: "\\", shift: true },
    { id: "settings", label: label("Ajustes", "common.settings", "Settings"), code: "Semicolon", keyLabel: ";", shift: true },
  ];
}
