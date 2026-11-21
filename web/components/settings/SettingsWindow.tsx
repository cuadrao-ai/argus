"use client";

import { useId, useRef, useState, type KeyboardEvent, type ReactNode, type RefObject } from "react";
import { ArrowLeft, ChevronRight, X, type LucideIcon } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useModalSurface } from "@/components/layout/useModalSurface";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import { withViewportPortal } from "@/components/ui/withViewportPortal";
import { SettingsWindowSection, type SettingsStep } from "@/components/settings/SettingsSurface";
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
 * A section may open a second step in place (Cuenta's confirmation): the
 * header then carries that step's title and an arrow back to the section.
 * A step with no way back (a finished deletion) holds the window: every exit
 * closes Ajustes, so nothing returns to the list or another section.
 */

type SettingsRow = { id: SettingsPanel; label: string; icon: LucideIcon };

type SettingsGroup = { id: SettingsPanelParent; title: string; rows: SettingsRow[] };

type LegalLink = { id: string; href: string; label: string };

type SettingsWindowProps = {
  /** The sections this account has, in order. */
  sections: readonly SettingsPanel[];
  renderSection: (panel: SettingsPanel) => ReactNode;
  legalLinks: readonly LegalLink[];
  returnFocusRef: RefObject<HTMLElement | null>;
  onClose: () => void;
};

const rowBase =
  "flex min-h-11 w-full items-center gap-3 rounded-item px-2.5 py-2 text-left text-[16px] transition-colors duration-150 ease-out focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-[var(--cuadrao-green)]";
const muted = "text-[#56635e] dark:text-white/70";
const hairline = "border-[#DCE0DA] dark:border-white/10";

function useGroups(sections: readonly SettingsPanel[]): SettingsGroup[] {
  const { t } = useTranslation();
  const groups: SettingsGroup[] = (["settings", "data"] as const).map((id) => ({
    id,
    title: t(...SETTINGS_GROUP_TITLE[id]),
    rows: sections.flatMap((panel) => {
      const nav = settingsPanelNav(panel);
      return nav && nav.group === id ? [{ id: panel, label: t(...nav.label), icon: nav.icon }] : [];
    }),
  }));
  return groups.filter((group) => group.rows.length > 0);
}

function rowTone(active: boolean): string {
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

function BackButton({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      aria-label={label}
      data-testid="settings-window-back"
      onClick={onClick}
      className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-black/60 transition-colors hover:bg-black/5 hover:text-black focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--cuadrao-green)] dark:text-white/60 dark:hover:bg-white/10 dark:hover:text-white"
    >
      <ArrowLeft className="h-5 w-5" aria-hidden="true" />
    </button>
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

function DesktopWindow({ sections, renderSection, legalLinks, returnFocusRef, onClose }: SettingsWindowProps) {
  const { t } = useTranslation();
  const overlayId = useId();
  const titleId = useId();
  const paneTitleId = useId();
  const panelRef = useRef<HTMLDivElement>(null);
  const activeRowRef = useRef<HTMLButtonElement>(null);
  const navRef = useRef<HTMLElement>(null);
  const [active, setActive] = useState<SettingsPanel | undefined>(sections[0]);
  const [step, setStep] = useState<SettingsStep | null>(null);
  if (active !== undefined && !sections.includes(active)) {
    setActive(sections[0]);
  }
  const groups = useGroups(sections);
  const held = step !== null && !step.onBack;
  useModalSurface({ isOpen: true, overlayId, containerRef: panelRef, onDismiss: onClose, onEscape: step?.onBack ?? onClose, initialFocusRef: activeRowRef, returnFocusRef });

  // Up and Down walk the list; landing on a section shows it, as a settings list does.
  const walk = (event: KeyboardEvent<HTMLElement>) => {
    const step = event.key === "ArrowDown" ? 1 : event.key === "ArrowUp" ? -1 : 0;
    if (!step || held) return;
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
                    const isActive = row.id === active;
                    const Icon = row.icon;
                    return (
                      <li key={row.id}>
                        <button
                          ref={isActive ? activeRowRef : undefined}
                          type="button"
                          data-settings-row
                          data-section={row.id}
                          data-testid={`settings-nav-${row.id}`}
                          aria-current={isActive ? "page" : undefined}
                          disabled={held}
                          onClick={() => setActive(row.id)}
                          className={`${rowBase} ${rowTone(isActive)}`}
                        >
                          <Icon className={`h-[18px] w-[18px] shrink-0 ${isActive ? "text-black dark:text-white" : muted}`} aria-hidden="true" />
                          <span className="min-w-0 flex-1">{row.label}</span>
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
            {step?.onBack ? (
              <div className="-ml-2.5 flex min-w-0 items-center gap-1">
                <BackButton label={t("common.back", "Back")} onClick={step.onBack} />
                <h3 id={paneTitleId} className="font-display text-[21px] font-medium">{step.title}</h3>
              </div>
            ) : (
              <h3 id={paneTitleId} className="pt-1 font-display text-[21px] font-medium">
                {step?.title ?? (activeNav ? t(...activeNav.label) : null)}
              </h3>
            )}
            <CloseButton label={t("common.close", "Close")} onClick={onClose} />
          </header>
          {active ? (
            <div key={active} data-testid={`settings-pane-${active}`} className={`flex min-h-0 flex-1 flex-col ${styles.pane}`}>
              <SettingsWindowSection onStep={setStep}>{renderSection(active)}</SettingsWindowSection>
            </div>
          ) : null}
        </section>
      </div>
    </div>
  );
}

function PhoneSection({ panel, renderSection, onBack, onClose, returnFocusRef }: { panel: SettingsPanel; renderSection: (panel: SettingsPanel) => ReactNode; onBack: () => void; onClose: () => void; returnFocusRef: RefObject<HTMLElement | null> }) {
  const { t } = useTranslation();
  const overlayId = useId();
  const titleId = useId();
  const ref = useRef<HTMLDivElement>(null);
  const backRef = useRef<HTMLButtonElement>(null);
  const [step, setStep] = useState<SettingsStep | null>(null);
  const held = step !== null && !step.onBack;
  const leave = held ? onClose : onBack;
  const exit = step?.onBack ?? leave;
  // Its own layer, so Escape and system back go up one level; a held step closes Ajustes instead.
  useModalSurface({ isOpen: true, overlayId, containerRef: ref, onDismiss: leave, onEscape: exit, initialFocusRef: backRef, returnFocusRef });
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
      <PhoneHeader
        titleId={titleId}
        title={step?.title ?? (nav ? t(...nav.label) : "")}
        closes={held}
        exitLabel={held ? t("common.close", "Close") : step?.onBack ? t("common.back", "Back") : t("common.settings", "Settings")}
        onExit={exit}
        exitRef={backRef}
      />
      <div className="flex min-h-0 flex-1 flex-col">
        <SettingsWindowSection onStep={setStep}>{renderSection(panel)}</SettingsWindowSection>
      </div>
    </div>
  );
}

function PhoneHeader({ titleId, title, closes = false, exitLabel, onExit, exitRef }: { titleId: string; title: string; closes?: boolean; exitLabel: string; onExit: () => void; exitRef?: RefObject<HTMLButtonElement | null> }) {
  const Icon = closes ? X : ArrowLeft;
  return (
    <header className={`flex shrink-0 items-center gap-1 border-b px-2 pb-2 pt-[max(8px,env(safe-area-inset-top))] ${hairline}`}>
      <button
        ref={exitRef}
        type="button"
        aria-label={exitLabel}
        data-testid={closes ? "settings-window-close" : "settings-window-back"}
        onClick={onExit}
        className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-black/70 hover:bg-black/5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--cuadrao-green)] dark:text-white/70 dark:hover:bg-white/10"
      >
        <Icon className="h-5 w-5" aria-hidden="true" />
      </button>
      <h2 id={titleId} className="min-w-0 font-display text-[21px] font-medium">{title}</h2>
    </header>
  );
}

function PhoneScreen({ sections, renderSection, legalLinks, returnFocusRef, onClose }: SettingsWindowProps) {
  const { t } = useTranslation();
  const overlayId = useId();
  const titleId = useId();
  const ref = useRef<HTMLDivElement>(null);
  const backRef = useRef<HTMLButtonElement>(null);
  const openerRef = useRef<HTMLElement | null>(null);
  const [section, setSection] = useState<SettingsPanel | null>(null);
  if (section !== null && !sections.includes(section)) {
    setSection(sections[0] ?? null);
  }
  const groups = useGroups(sections);
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
        <PhoneHeader titleId={titleId} title={t("common.settings", "Settings")} exitLabel={t("common.back", "Back")} onExit={onClose} exitRef={backRef} />
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
                        type="button"
                        data-testid={`settings-nav-${row.id}`}
                        onClick={(event) => {
                          openerRef.current = event.currentTarget;
                          setSection(row.id);
                        }}
                        className="flex min-h-[52px] w-full items-center gap-3 px-4 text-left text-[16px] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-[var(--cuadrao-green)]"
                      >
                        <Icon className={`h-5 w-5 shrink-0 ${muted}`} aria-hidden="true" />
                        <span className="min-w-0 flex-1">{row.label}</span>
                        <ChevronRight className={`h-4 w-4 shrink-0 ${muted}`} aria-hidden="true" />
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
      {section ? <PhoneSection panel={section} renderSection={renderSection} onBack={() => setSection(null)} onClose={onClose} returnFocusRef={openerRef} /> : null}
    </>
  );
}

function SettingsWindowSurface(props: SettingsWindowProps) {
  const { isBelowDesktop } = useResponsiveLayout();
  return isBelowDesktop ? <PhoneScreen {...props} /> : <DesktopWindow {...props} />;
}

export default withViewportPortal(SettingsWindowSurface);
