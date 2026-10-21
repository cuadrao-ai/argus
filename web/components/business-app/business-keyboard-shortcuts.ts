"use client";

import { useTranslation } from "react-i18next";
import type { WorkspaceKeyboardShortcut } from "@/lib/keyboard-shortcuts";
import { businessSearchEnabledFromEnv } from "@/lib/private-alpha-flags";
import type { GrantedSpace } from "@/lib/business-api";
import type { BusinessActions } from "./business-actions";
import type { BusinessPanelState } from "./BusinessWorkspace";
import { useRunReviewShortcut } from "./BusinessReviewShortcuts";
import { canAddRecords } from "./business-ui";

/** The three screens in the rail and the tabs. */
export const BUSINESS_SECTIONS = ["overview", "inbox", "transactions"] as const;

export function useBusinessKeyboardShortcuts({ openPanel, actions, chosen }: { openPanel: (panel: BusinessPanelState) => void; actions: BusinessActions; chosen: GrantedSpace | null }): readonly WorkspaceKeyboardShortcut[] {
  const { t } = useTranslation();
  const review = useRunReviewShortcut();
  return [
    { id: "approve", label: t("business.dossier.approve_action", "Approve expense"), code: "Enter", keyLabel: "Enter", shift: true, run: () => review("approve") },
    { id: "approve_next", label: t("business.dossier.approve_next", "Approve and next"), code: "KeyS", keyLabel: "S", shift: true, run: () => review("approve_next") },
    { id: "previous", label: t("business.shortcuts.previous_receipt", "Previous receipt"), code: "ArrowUp", keyLabel: "↑", shift: true, run: () => review("previous") },
    { id: "next", label: t("business.shortcuts.next_receipt", "Next receipt"), code: "ArrowDown", keyLabel: "↓", shift: true, run: () => review("next") },
    { id: "edit", label: t("business.shortcuts.edit_detail", "Edit a detail"), code: "KeyE", keyLabel: "E", shift: true, run: () => review("edit") },
    { id: "upload", label: t("business.actions.add", "Add"), code: "Period", keyLabel: ".", shift: true, run: () => { const action = canAddRecords(chosen) ? actions.create.find((action) => action.id === "upload_receipt") : undefined; action?.run(); return Boolean(action); } },
    ...BUSINESS_SECTIONS.map((section, index) => ({ id: section, label: t("business.shortcuts.go_to", { section: t(`business.nav.${section}`), defaultValue: "Go to {{section}}" }), code: `Digit${index + 1}`, keyLabel: String(index + 1), jumpIndex: index, run: () => { openPanel({ kind: section }); return true; } })),
    ...(businessSearchEnabledFromEnv() ? [{ id: "search", label: t("common.search", "Search"), code: "KeyK", keyLabel: "K" }] : []),
    { id: "keyboard_shortcuts", label: t("keyboard_shortcuts.title", "Keyboard shortcuts"), code: "Slash", keyLabel: "/" },
    { id: "sidebar", label: t("business.shortcuts.sidebar", "Show or hide the sidebar"), code: "Backslash", keyLabel: "\\", shift: true },
    { id: "settings", label: t("common.settings", "Settings"), code: "Semicolon", keyLabel: ";", shift: true },
  ];
}
