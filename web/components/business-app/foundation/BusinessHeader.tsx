"use client";

import { useLayoutEffect, useRef, type ReactNode } from "react";
import { Search, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { HeaderSearch } from "./HeaderSearch";
import BusinessAddMenu from "../BusinessAddMenu";
import { useListSearchLoan, type SearchableList } from "./list-search";
import styles from "./business-header.module.css";
import { HomeHeading } from "./HomeHeading";
import { HOME_CANVAS_MAX, INICIO_REDESIGN_PREVIEW } from "../inicio/preview";
import { PageDescription, usePageIntro } from "./PageHeading";

export default function BusinessHeader({ home, name, business, title, screen, onSearch }: { home: boolean; name: string | null; business?: string; title?: string; screen?: string; onSearch?: (query?: string) => void }) {
  const intro = usePageIntro(screen);
  const group = useRef<HTMLDivElement>(null);
  const sentence = intro?.description;
  // Inicio's redesign keeps its greeting in the bar, inset to the same capped box as its content.
  const homeBar = INICIO_REDESIGN_PREVIEW && home;
  const fitted = Boolean(sentence) || homeBar;
  // A heading group (a sentence, or Inicio's date and greeting) sizes the bar: its height plus 21px above and
  // below, whatever it wraps to, with the other actions on its first row. The shell's bar, fade, gutter and
  // content offset read these; otherwise they keep their 80px, centered default.
  useLayoutEffect(() => {
    const node = group.current;
    if (!fitted || !node) return;
    const body = document.body.style;
    const fit = () => body.setProperty("--workspace-bar", `${Math.max(80, Math.ceil(node.getBoundingClientRect().height) + 42)}px`);
    body.setProperty("--workspace-bar-align", "flex-start");
    body.setProperty("--workspace-bar-inset", "21px");
    fit();
    const observer = new ResizeObserver(fit);
    observer.observe(node);
    return () => { observer.disconnect(); for (const name of ["--workspace-bar", "--workspace-bar-align", "--workspace-bar-inset"]) body.removeProperty(name); };
  }, [fitted]);
  // In the preview every Business screen shares Inicio's bounded box: the canvas and the bar are capped and centered
  // on it, and the bar is opaque under its heading so scrolled content never shows behind it.
  useLayoutEffect(() => {
    if (!INICIO_REDESIGN_PREVIEW) return;
    const body = document.body;
    body.style.setProperty("--workspace-canvas-max", HOME_CANVAS_MAX);
    body.dataset.workspaceBounded = "";
    return () => { body.style.removeProperty("--workspace-canvas-max"); delete body.dataset.workspaceBounded; };
  }, []);
  // In the preview every Business screen's bar holds the same tools in one order after its heading: search, then
  // the one Agregar (never on Negocio, which adds no documents). The share, privacy, notification and profile
  // controls follow from the shell. Each screen's own Agregar is retired as its owner moves to this one.
  const tools = INICIO_REDESIGN_PREVIEW ? (
    <div data-testid="business-bar-tools" className={styles.tools}>
      {onSearch ? screen === "inbox" || screen === "transactions" ? <ScopedSearch list={screen} onOpen={onSearch} /> : <StableSearch onOpen={onSearch} /> : null}
      {screen && screen !== "business" ? <BusinessAddMenu placement="header" /> : null}
    </div>
  ) : null;
  return (
    <div ref={group} data-business-search-anchor data-testid="business-desktop-header" data-intro={sentence ? "" : undefined} className={`${styles.header} ${INICIO_REDESIGN_PREVIEW ? styles.toolbar : ""}`}>
      {home ? <>
        <HomeHeading name={name} business={business} className={styles.welcome} />
        {tools ?? (onSearch ? <div className={styles.search}><HeaderSearch onOpen={onSearch} /></div> : null)}
        {/* Inicio's sentence takes its own row under the greeting and search, so the search never narrows it. */}
        {intro ? <div className={`${styles.intro} ${styles.introRow}`}><PageDescription text={intro.description} icon={intro.icon} /></div> : null}
      </> : intro ? <><div className={styles.welcome}>
        {/* Title and its sentence read as one group; the sentence takes the line Inicio gives its date. */}
        <h1 className={`${styles.greeting} ${styles.titleLine} font-display`}>{intro.title}</h1>
        <div className={styles.intro}><PageDescription text={intro.description} icon={intro.icon} /></div>
      </div>{tools}</> : title ? <><div className={styles.welcome}>
        <span aria-hidden="true" className={styles.date} style={{ height: "1.5em" }} />
        <h1 className={`${styles.greeting} ${styles.titleLine} font-display`}>{title}</h1>
      </div>{tools}</> : tools}
    </div>
  );
}

/**
 * Search in the toolbar holds still: a fixed-width field where the bar has room, a 44px button where it does not.
 * Both open the one search (⌘K too); nothing grows on hover, so the controls beside it never move.
 */
function StableSearch({ onOpen, field, scoped = false }: { onOpen: () => void; field?: ReactNode; scoped?: boolean }) {
  const { t } = useTranslation();
  const label = t("business.search.placeholder", "Search merchant, amount or note");
  const command = typeof navigator !== "undefined" && /Mac|iPhone|iPad|iPod/.test(navigator.userAgent);
  return (
    <div data-testid="stable-search" data-scoped={scoped ? "" : undefined} className="flex shrink-0 justify-end">
      <div className={styles.stableField}>{field ?? <HeaderSearch onOpen={onOpen} short />}</div>
      <button type="button" data-testid="header-search-button" onClick={onOpen} aria-label={label} aria-keyshortcuts={command ? "Meta+K" : "Control+K"} className={`${styles.stableButton} h-11 w-11 items-center justify-center rounded-full border border-[#DCE0DA] bg-[#FFFEFA] text-[#56635e] transition-colors hover:border-[#7d8a84] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f5a49] dark:border-white/10 dark:bg-[#1f2225] dark:text-white/65`}>
        <Search className="h-4 w-4" aria-hidden="true" />
      </button>
    </div>
  );
}

/**
 * On a list (Bandeja, Registros) the bar's search button carries the list's scope, and the filter it applied:
 * "En Bandeja · colmado". It opens the one search window, scoped to that list and holding that filter; the × clears
 * the list's filter. A list that lends no query (a phone, or one not wired) keeps the plain button.
 */
function ScopedSearch({ list, onOpen }: { list: SearchableList; onOpen: (query?: string) => void }) {
  const { t } = useTranslation();
  const loan = useListSearchLoan(list);
  if (!loan) return <StableSearch onOpen={onOpen} />;
  const place = list === "inbox" ? t("business.nav.inbox", "Inbox") : t("business.nav.transactions", "Records");
  const scopeLabel = t("business.search.scoped_label", { place, defaultValue: "Search {{place}}" });
  const command = typeof navigator !== "undefined" && /Mac|iPhone|iPad|iPod/.test(navigator.userAgent);
  const field = (
    <div className={styles.scopedField} data-testid="scoped-search">
      <button type="button" data-testid="scoped-search-open" onClick={() => onOpen(loan.query)} aria-label={loan.query ? `${scopeLabel}: ${loan.query}` : scopeLabel} aria-keyshortcuts={command ? "Meta+K" : "Control+K"} className={`${styles.scopedButton} rounded-full`}>
        <Search className="h-4 w-4 shrink-0" aria-hidden="true" />
        <span className={`${styles.scopePill} rounded-mark`}>{t("business.search.scope_in", { place, defaultValue: "In {{place}}" })}</span>
        <span className={`${styles.scopedText} ${loan.query ? styles.scopedQuery : ""}`}>{loan.query || t("common.search", "Search")}</span>
        {loan.query ? null : <kbd aria-hidden="true" className={`${styles.scopedKbd} rounded-mark`}>{command ? "⌘K" : "Ctrl K"}</kbd>}
      </button>
      {loan.query ? <button type="button" data-testid="scoped-search-clear" aria-label={t("business.search.clear_filter", { place, defaultValue: "Clear the {{place}} search" })} onClick={() => loan.setQuery("")} className={`${styles.scopedClear} rounded-full`}><X className="h-4 w-4" aria-hidden="true" /></button> : null}
    </div>
  );
  return <StableSearch onOpen={() => onOpen(loan.query)} field={field} scoped />;
}
