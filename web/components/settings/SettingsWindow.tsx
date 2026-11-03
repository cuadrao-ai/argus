"use client";

import { useId, useRef, useState, type KeyboardEvent, type ReactNode, type RefObject } from "react";
import { ArrowLeft, ArrowUpRight, ChevronRight, Shield, Trash2, X, type LucideIcon } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useModalSurface } from "@/components/layout/useModalSurface";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import { withViewportPortal } from "@/components/ui/withViewportPortal";
import { SettingsWindowSection } from "@/components/settings/SettingsSurface";
import type { AccountDeletionEligibility } from "@/lib/account-deletion-api";
import {
  SETTINGS_GROUP_TITLE,
  settingsPanelNav,
  type SettingsPanel,
  type SettingsPanelParent,
} from "@/components/sidebar/ProfileSettingsPanels";
import dialogStyles from "@/components/ui/centered-dialog.module.css";
import styles from "./settings-window.module.css";

/**
 * Ajustes: every account setting in one window. A short list of sections on
 * the left, the chosen one on the right, and moving between them happens in
 * place, so nothing stacks and there is no chain of backs. A phone gets the
 * same list as a full screen; a section replaces it and its arrow returns.
 * A step that cannot be undone still asks in its own alert, above the window.
 */

type SettingsRow =
  | { kind: "section"; id: SettingsPanel; label: string; icon: LucideIcon }
  | { kind: "action"; id: "security" | "delete-account"; label: string; icon: LucideIcon; onSelect: () => void; leaves?: boolean; danger?: boolean; note?: string };

type SettingsGroup = { id: SettingsPanelParent; title: string; rows: SettingsRow[] };

type LegalLink = { id: string; href: string; label: string };

type SettingsWindowProps = {
  /** The sections this account has, in order. */
  sections: readonly SettingsPanel[];
  renderSection: (panel: SettingsPanel) => ReactNode;
  onSecurity: () => void;
  onDeleteAccount: () => void;
  /** The server's answer on deleting this account, read as Ajustes opened; null until it lands. */
  deletionAnswer?: AccountDeletionEligibility | null;
  /** Where the delete alert returns focus when it closes over the window. */
  deleteAccountRef: RefObject<HTMLButtonElement | null>;
  legalLinks: readonly LegalLink[];
  returnFocusRef: RefObject<HTMLElement | null>;
  onClose: () => void;
};

const rowBase =
  "flex min-h-11 w-full items-center gap-3 rounded-item px-2.5 py-2 text-left text-[16px] transition-colors duration-150 ease-out focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-[var(--cuadrao-green)]";
const muted = "text-[#56635e] dark:text-white/70";
const hairline = "border-[#DCE0DA] dark:border-white/10";

function useGroups(sections: readonly SettingsPanel[], onSecurity: () => void, onDeleteAccount: () => void, deletionAnswer: AccountDeletionEligibility | null | undefined): SettingsGroup[] {
  const { t, i18n } = useTranslation();
  // The row says before anyone presses it which Businesses stand in the way, as the server named them.
  const owned = deletionAnswer && "blockers" in deletionAnswer ? deletionAnswer.blockers.flatMap(blocker => blocker.kind === "business_owner" ? [blocker.business_name] : []) : [];
  const deleteNote = owned.length
    ? t("settings.profile.delete_account_owner_note", { names: new Intl.ListFormat(i18n.resolvedLanguage ?? "es-419", { type: "conjunction" }).format(owned) })
    : undefined;
  const groups: SettingsGroup[] = (["settings", "data"] as const).map((id) => ({
    id,
    title: t(...SETTINGS_GROUP_TITLE[id]),
    rows: sections.flatMap((panel) => {
      const nav = settingsPanelNav(panel);
      return nav && nav.group === id ? [{ kind: "section" as const, id: panel, label: t(...nav.label), icon: nav.icon }] : [];
    }),
  }));
  groups[1].rows.push(
    { kind: "action", id: "security", label: t("settings.data.security", "Security"), icon: Shield, onSelect: onSecurity, leaves: true },
    { kind: "action", id: "delete-account", label: t("settings.profile.delete_account", "Delete account"), icon: Trash2, onSelect: onDeleteAccount, danger: true, note: deleteNote },
  );
  return groups.filter((group) => group.rows.length > 0);
}

function rowTone(row: SettingsRow, active: boolean): string {
  if (row.kind === "action" && row.danger) return "text-[#9e2f39] hover:bg-[#9e2f39]/[0.06] dark:text-[#ec9aa0] dark:hover:bg-[#ec9aa0]/10";
  if (active) return "bg-black/[0.06] font-medium text-black dark:bg-white/[0.08] dark:text-white";
  return "text-black hover:bg-black/[0.04] dark:text-white dark:hover:bg-white/[0.05]";
}

function LegalFooter({ links, className }: { links: readonly LegalLink[]; className: string }) {
  return (
    <p data-testid="settings-legal-footer" className={`flex flex-wrap items-center gap-x-1 text-[14px] ${muted} ${className}`}>
      {links.map((link, index) => (
        <span key={link.id} className="flex items-center gap-1">
          {index > 0 ? <span aria-hidden="true">·</span> : null}
          <a
            href={link.href}
            target="_blank"
            rel="noreferrer"
            className="inline-flex min-h-11 items-center rounded-mark px-1 transition-colors hover:text-black focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--cuadrao-green)] dark:hover:text-white"
          >
            {link.label}
          </a>
        </span>
      ))}
    </p>
  );
}

function CloseButton({ label, onClick, buttonRef }: { label: string; onClick: () => void; buttonRef?: RefObject<HTMLButtonElement | null> }) {
  return (
    <button
      ref={buttonRef}
      type="button"
      aria-label={label}
      data-testid="settings-window-close"
      onClick={onClick}
      className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-black/60 transition-colors hover:bg-black/5 hover:text-black focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--cuadrao-green)] dark:text-white/60 dark:hover:bg-white/10 dark:hover:text-white"
    >
      <X className="h-5 w-5" aria-hidden="true" />
    </button>
  );
}

function DesktopWindow({ sections, renderSection, onSecurity, onDeleteAccount, deletionAnswer, deleteAccountRef, legalLinks, returnFocusRef, onClose }: SettingsWindowProps) {
  const { t } = useTranslation();
  const overlayId = useId();
  const titleId = useId();
  const paneTitleId = useId();
  const panelRef = useRef<HTMLDivElement>(null);
  const activeRowRef = useRef<HTMLButtonElement>(null);
  const navRef = useRef<HTMLElement>(null);
  const [active, setActive] = useState<SettingsPanel | undefined>(sections[0]);
  const groups = useGroups(sections, onSecurity, onDeleteAccount, deletionAnswer);
  useModalSurface({ isOpen: true, overlayId, containerRef: panelRef, onDismiss: onClose, initialFocusRef: activeRowRef, returnFocusRef });

  // Up and Down walk the list; landing on a section shows it, as a settings list does.
  const walk = (event: KeyboardEvent<HTMLElement>) => {
    const step = event.key === "ArrowDown" ? 1 : event.key === "ArrowUp" ? -1 : 0;
    if (!step) return;
    const rows = Array.from(navRef.current?.querySelectorAll<HTMLButtonElement>("[data-settings-row]") ?? []);
    const next = rows[rows.indexOf(document.activeElement as HTMLButtonElement) + step];
    if (!next) return;
    event.preventDefault();
    next.focus();
    const section = next.dataset.section as SettingsPanel | undefined;
    if (section) setActive(section);
  };

  const activeNav = active ? settingsPanelNav(active) : null;

  return (
    <div className={`fixed inset-0 z-[70] flex items-center justify-center bg-black/40 p-8 dark:bg-black/60 ${dialogStyles.scrim}`}>
      <button type="button" tabIndex={-1} aria-label={t("common.close", "Close")} className="absolute inset-0 cursor-default" onClick={onClose} />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        data-testid="settings-window"
        className={`relative flex h-[min(640px,calc(100dvh-64px))] w-[min(860px,100%)] overflow-hidden rounded-surface border bg-white text-[#172b26] dark:bg-[#1b1d20] dark:text-white ${hairline} ${dialogStyles.dialog}`}
      >
        <nav ref={navRef} aria-labelledby={titleId} onKeyDown={walk} className={`flex w-[264px] shrink-0 flex-col border-r ${hairline}`}>
          <h2 id={titleId} className="px-5 pb-2 pt-5 font-display text-[21px] font-medium">
            {t("common.settings", "Settings")}
          </h2>
          <div className="argus-thin-scrollbar min-h-0 flex-1 overflow-y-auto px-2.5 pb-3">
            {groups.map((group) => (
              <div key={group.id} className="pt-[13px]">
                <p className={`px-2.5 pb-1 text-[14px] ${muted}`}>{group.title}</p>
                <ul className="flex flex-col gap-0.5">
                  {group.rows.map((row) => {
                    const isActive = row.kind === "section" && row.id === active;
                    const Icon = row.icon;
                    return (
                      <li key={row.id}>
                        <button
                          ref={isActive ? activeRowRef : row.id === "delete-account" ? deleteAccountRef : undefined}
                          type="button"
                          data-settings-row
                          data-section={row.kind === "section" ? row.id : undefined}
                          data-testid={`settings-nav-${row.id}`}
                          aria-current={isActive ? "page" : undefined}
                          onClick={row.kind === "section" ? () => setActive(row.id) : row.onSelect}
                          className={`${rowBase} ${rowTone(row, isActive)}`}
                        >
                          <Icon className={`h-[18px] w-[18px] shrink-0 ${row.kind === "action" && row.danger ? "" : isActive ? "text-black dark:text-white" : muted}`} aria-hidden="true" />
                          <span className="min-w-0 flex-1">
                            {row.label}
                            {row.kind === "action" && row.note ? <span data-testid="delete-account-note" className={`block text-[14px] ${muted}`}>{row.note}</span> : null}
                          </span>
                          {row.kind === "action" && row.leaves ? <ArrowUpRight className={`h-4 w-4 shrink-0 ${muted}`} aria-hidden="true" /> : null}
                        </button>
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))}
          </div>
          <LegalFooter links={legalLinks} className={`border-t px-4 py-1 ${hairline}`} />
        </nav>
        <section aria-labelledby={paneTitleId} className="flex min-w-0 flex-1 flex-col">
          <header className="flex shrink-0 items-center justify-between gap-3 pb-1 pl-5 pr-3 pt-3">
            <h3 id={paneTitleId} className="pt-1 font-display text-[21px] font-medium">
              {activeNav ? t(...activeNav.label) : null}
            </h3>
            <CloseButton label={t("common.close", "Close")} onClick={onClose} />
          </header>
          {active ? (
            <div key={active} data-testid={`settings-pane-${active}`} className={`flex min-h-0 flex-1 flex-col ${styles.pane}`}>
              <SettingsWindowSection>{renderSection(active)}</SettingsWindowSection>
            </div>
          ) : null}
        </section>
      </div>
    </div>
  );
}

function PhoneSection({ panel, renderSection, onBack, returnFocusRef }: { panel: SettingsPanel; renderSection: (panel: SettingsPanel) => ReactNode; onBack: () => void; returnFocusRef: RefObject<HTMLElement | null> }) {
  const { t } = useTranslation();
  const overlayId = useId();
  const titleId = useId();
  const ref = useRef<HTMLDivElement>(null);
  const backRef = useRef<HTMLButtonElement>(null);
  // Its own layer, so Escape and system back return to the list: one press, one level.
  useModalSurface({ isOpen: true, overlayId, containerRef: ref, onDismiss: onBack, initialFocusRef: backRef, returnFocusRef });
  const nav = settingsPanelNav(panel);
  return (
    <div
      ref={ref}
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
      data-testid={`settings-pane-${panel}`}
      className={`fixed inset-0 z-[71] flex flex-col bg-white text-[#172b26] dark:bg-[#1b1d20] dark:text-white ${styles.push}`}
    >
      <PhoneHeader titleId={titleId} title={nav ? t(...nav.label) : ""} backLabel={t("common.settings", "Settings")} onBack={onBack} backRef={backRef} />
      <div className="flex min-h-0 flex-1 flex-col">
        <SettingsWindowSection>{renderSection(panel)}</SettingsWindowSection>
      </div>
    </div>
  );
}

function PhoneHeader({ titleId, title, backLabel, onBack, backRef }: { titleId: string; title: string; backLabel: string; onBack: () => void; backRef?: RefObject<HTMLButtonElement | null> }) {
  return (
    <header className={`flex shrink-0 items-center gap-1 border-b px-2 pb-2 pt-[max(8px,env(safe-area-inset-top))] ${hairline}`}>
      <button
        ref={backRef}
        type="button"
        aria-label={backLabel}
        data-testid="settings-window-back"
        onClick={onBack}
        className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-black/70 hover:bg-black/5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--cuadrao-green)] dark:text-white/70 dark:hover:bg-white/10"
      >
        <ArrowLeft className="h-5 w-5" aria-hidden="true" />
      </button>
      <h2 id={titleId} className="min-w-0 font-display text-[21px] font-medium">{title}</h2>
    </header>
  );
}

function PhoneScreen({ sections, renderSection, onSecurity, onDeleteAccount, deletionAnswer, deleteAccountRef, legalLinks, returnFocusRef, onClose }: SettingsWindowProps) {
  const { t } = useTranslation();
  const overlayId = useId();
  const titleId = useId();
  const ref = useRef<HTMLDivElement>(null);
  const backRef = useRef<HTMLButtonElement>(null);
  const openerRef = useRef<HTMLElement | null>(null);
  const [section, setSection] = useState<SettingsPanel | null>(null);
  const groups = useGroups(sections, onSecurity, onDeleteAccount, deletionAnswer);
  useModalSurface({ isOpen: true, overlayId, containerRef: ref, onDismiss: onClose, initialFocusRef: backRef, returnFocusRef });

  return (
    <>
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        data-testid="settings-window"
        className={`fixed inset-0 z-[70] flex flex-col bg-[#F7F5EE] text-[#172b26] dark:bg-[#141517] dark:text-white ${dialogStyles.scrim}`}
      >
        <PhoneHeader titleId={titleId} title={t("common.settings", "Settings")} backLabel={t("common.back", "Back")} onBack={onClose} backRef={backRef} />
        <div className="min-h-0 flex-1 overflow-y-auto px-4 pb-[max(16px,env(safe-area-inset-bottom))]">
          {groups.map((group) => (
            <div key={group.id} className="pt-[21px]">
              <p className={`px-1 pb-2 text-[14px] ${muted}`}>{group.title}</p>
              <ul className={`overflow-hidden rounded-surface border bg-white dark:bg-[#1f2225] ${hairline}`}>
                {group.rows.map((row, index) => {
                  const Icon = row.icon;
                  return (
                    <li key={row.id} className={index > 0 ? `border-t ${hairline}` : undefined}>
                      <button
                        ref={row.id === "delete-account" ? deleteAccountRef : undefined}
                        type="button"
                        data-testid={`settings-nav-${row.id}`}
                        onClick={(event) => {
                          if (row.kind === "action") return row.onSelect();
                          openerRef.current = event.currentTarget;
                          setSection(row.id);
                        }}
                        className={`flex min-h-[52px] w-full items-center gap-3 px-4 text-left text-[16px] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-[var(--cuadrao-green)] ${
                          row.kind === "action" && row.danger ? "text-[#9e2f39] dark:text-[#ec9aa0]" : ""
                        }`}
                      >
                        <Icon className={`h-5 w-5 shrink-0 ${row.kind === "action" && row.danger ? "" : muted}`} aria-hidden="true" />
                        <span className="min-w-0 flex-1 py-2">
                          {row.label}
                          {row.kind === "action" && row.note ? <span data-testid="delete-account-note" className={`block text-[14px] ${muted}`}>{row.note}</span> : null}
                        </span>
                        {row.kind === "section" ? <ChevronRight className={`h-4 w-4 shrink-0 ${muted}`} aria-hidden="true" /> : row.leaves ? <ArrowUpRight className={`h-4 w-4 shrink-0 ${muted}`} aria-hidden="true" /> : null}
                      </button>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
          <LegalFooter links={legalLinks} className="justify-center pt-[21px]" />
        </div>
      </div>
      {section ? <PhoneSection panel={section} renderSection={renderSection} onBack={() => setSection(null)} returnFocusRef={openerRef} /> : null}
    </>
  );
}

function SettingsWindowSurface(props: SettingsWindowProps) {
  const { isBelowDesktop } = useResponsiveLayout();
  return isBelowDesktop ? <PhoneScreen {...props} /> : <DesktopWindow {...props} />;
}

export default withViewportPortal(SettingsWindowSurface);
