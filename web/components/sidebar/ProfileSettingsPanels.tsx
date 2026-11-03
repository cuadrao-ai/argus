"use client";

import { useTranslation } from "react-i18next";
import { Activity, Archive, Brain, Globe, History, Link2, MapPin, MessageCircle, Palette, PanelLeft, type LucideIcon } from "lucide-react";

import BusinessNameSettings from "@/components/settings/BusinessNameSettings";
import AppearanceModal from "@/components/settings/AppearanceModal";
import LanguageModal from "@/components/settings/LanguageModal";
import ArchivedChatsView from "@/components/settings/ArchivedChatsView";
import DeletedItemsView from "@/components/settings/DeletedItemsView";
import HomeCountryModal from "@/components/settings/HomeCountryModal";
import MemoryControlsModal from "@/components/settings/MemoryControlsModal";
import SharedReceiptsView from "@/components/settings/SharedReceiptsView";
import UsageModal from "@/components/settings/UsageModal";
import WhatsAppLinkModal from "@/components/settings/WhatsAppLinkModal";
import SidebarPreferenceModal, { type SidebarMode } from "@/components/settings/SidebarPreferenceModal";
import type { ApiUser } from "@/lib/argus-api";

/* Every settings surface the profile menu opens, registered once. A new panel
 * is an import and an entry: the key set is the type, and the menu derives its
 * ActiveModal union from it. The mobile-shell invariant enumerates the imports
 * above, so a panel cannot ship without a managed layer. */

export type SettingsPanelParent = "settings" | "data";

type SettingsPanelContext = {
  locale: "en-US" | "es-419";
  /** Where focus returns when a panel that took it closes. */
  anchorRef: React.RefObject<HTMLElement | null>;
  onClose: () => void;
  /** Only a sheet has a way back; above the panel line this is undefined. */
  onBack: (() => void) | undefined;
  backLabel: string;
  onHistoryMutated?: () => void;
  /** The menu's hand-off, so a panel's save reaches the shell like the menu's own. */
  onProfileSaved: (user: ApiUser) => void;
  /** The account as the menu last read it. */
  profile: ApiUser | null;
  /** The rail's saved mode and its setter, where the shell has a rail. */
  sidebar?: SidebarPreference;
};

export type SidebarPreference = { mode: SidebarMode; business: boolean; onSelect: (mode: SidebarMode) => void };

type SettingsPanelEntry = {
  /** The submenu a sheet's back row returns to, and the group it sits in inside Ajustes. */
  parent: SettingsPanelParent;
  /** Its row in Ajustes; absent for a panel Ajustes does not list. */
  nav?: { label: [string, string]; icon: LucideIcon };
  render: (context: SettingsPanelContext) => React.ReactElement | null;
};

const SETTINGS_PANELS = {
  business_name: {
    parent: "settings",
    render: ({ onClose }) => <BusinessNameSettings onClose={onClose} />,
  },
  whatsapp: {
    parent: "settings",
    nav: { label: ["settings.whatsapp.title", "WhatsApp"], icon: MessageCircle },
    render: ({ onClose, onBack, backLabel }) => (
      <WhatsAppLinkModal onClose={onClose} onBack={onBack} backLabel={backLabel} />
    ),
  },
  appearance: {
    parent: "settings",
    nav: { label: ["settings.app.appearance", "Appearance"], icon: Palette },
    render: ({ onClose, onBack, backLabel }) => (
      <AppearanceModal
        onClose={onClose}
        onBack={onBack}
        backLabel={backLabel}
      />
    ),
  },
  language: {
    parent: "settings",
    nav: { label: ["settings.app.language", "Language"], icon: Globe },
    render: ({ onClose, onBack, backLabel, onProfileSaved }) => (
      <LanguageModal
        onClose={onClose}
        onBack={onBack}
        backLabel={backLabel}
        onProfileSaved={onProfileSaved}
      />
    ),
  },
  country: {
    parent: "settings",
    nav: { label: ["settings.app.home_country", "Country and currency"], icon: MapPin },
    render: ({ onClose, onBack, backLabel, onProfileSaved, profile }) => (
      <HomeCountryModal
        profile={profile}
        onClose={onClose}
        onBack={onBack}
        backLabel={backLabel}
        onProfileSaved={onProfileSaved}
      />
    ),
  },
  archived: {
    parent: "data",
    nav: { label: ["settings.data.archived_chats", "Archived chats"], icon: Archive },
    render: ({ onClose, onBack, backLabel, onHistoryMutated }) => (
      <ArchivedChatsView
        onClose={onClose}
        onBack={onBack}
        backLabel={backLabel}
        onRestored={onHistoryMutated}
      />
    ),
  },
  deleted: {
    parent: "data",
    nav: { label: ["settings.data.recently_deleted", "Recently Deleted"], icon: History },
    render: ({ onClose, onBack, backLabel, onHistoryMutated }) => (
      <DeletedItemsView
        onClose={onClose}
        onBack={onBack}
        backLabel={backLabel}
        onRestored={onHistoryMutated}
      />
    ),
  },
  usage: {
    parent: "data",
    nav: { label: ["settings.data.usage", "Usage"], icon: Activity },
    render: ({ locale, onClose, onBack, backLabel, anchorRef }) => (
      <UsageModal
        locale={locale}
        onClose={onClose}
        onBack={onBack}
        backLabel={backLabel}
        returnFocusRef={anchorRef}
      />
    ),
  },
  sidebar: {
    parent: "settings",
    nav: { label: ["settings.app.sidebar", "Sidebar"], icon: PanelLeft },
    render: ({ onClose, onBack, backLabel, sidebar }) =>
      sidebar ? (
        <SidebarPreferenceModal
          mode={sidebar.mode}
          business={sidebar.business}
          onSelect={sidebar.onSelect}
          onClose={onClose}
          onBack={onBack}
          backLabel={backLabel}
        />
      ) : null,
  },
  memory: {
    parent: "data",
    nav: { label: ["settings.data.personalization.menu", "Personalization"], icon: Brain },
    render: ({ locale, onClose, onBack, backLabel, anchorRef }) => (
      <MemoryControlsModal
        locale={locale}
        onClose={onClose}
        onBack={onBack}
        backLabel={backLabel}
        returnFocusRef={anchorRef}
      />
    ),
  },
  receipts: {
    parent: "data",
    nav: { label: ["settings.data.shared_links", "Shared links"], icon: Link2 },
    render: ({ onClose, onBack, backLabel, anchorRef }) => (
      <SharedReceiptsView
        onClose={onClose}
        onBack={onBack}
        backLabel={backLabel}
        returnFocusRef={anchorRef}
      />
    ),
  },
} satisfies Record<string, SettingsPanelEntry>;

export type SettingsPanel = keyof typeof SETTINGS_PANELS;

/** Ajustes lists these, in this order, within each group. */
export const SETTINGS_WINDOW_ORDER: readonly SettingsPanel[] = [
  "appearance",
  "language",
  "country",
  "sidebar",
  "whatsapp",
  "memory",
  "receipts",
  "archived",
  "deleted",
  "usage",
];

export function settingsPanelNav(panel: SettingsPanel): { group: SettingsPanelParent; label: [string, string]; icon: LucideIcon } | null {
  const entry: SettingsPanelEntry = SETTINGS_PANELS[panel];
  return entry.nav ? { group: entry.parent, ...entry.nav } : null;
}

export const SETTINGS_GROUP_TITLE: Record<SettingsPanelParent, [string, string]> = {
  settings: ["settings.app.title", "Preferences"],
  data: ["settings.data.title", "Data Controls"],
};

type ProfileSettingsPanelsProps = {
  panel: SettingsPanel;
  /** Below the panel line a panel is a sheet, which is the only case with a way back. */
  asSheet: boolean;
  locale: "en-US" | "es-419";
  anchorRef: React.RefObject<HTMLElement | null>;
  onClose: () => void;
  onBack: (parent: SettingsPanelParent) => void;
  onHistoryMutated?: () => void;
  onProfileSaved: (user: ApiUser) => void;
  profile: ApiUser | null;
  sidebar?: SidebarPreference;
};

export default function ProfileSettingsPanels({
  panel,
  asSheet,
  locale,
  anchorRef,
  onClose,
  onBack,
  onHistoryMutated,
  onProfileSaved,
  profile,
  sidebar,
}: ProfileSettingsPanelsProps) {
  const { t } = useTranslation();
  const { parent, render } = SETTINGS_PANELS[panel];
  const [titleKey, titleFallback] = SETTINGS_GROUP_TITLE[parent];

  return render({
    locale,
    anchorRef,
    onClose,
    onBack: asSheet ? () => onBack(parent) : undefined,
    backLabel: t(titleKey, titleFallback),
    onHistoryMutated,
    onProfileSaved,
    profile,
    sidebar,
  });
}
