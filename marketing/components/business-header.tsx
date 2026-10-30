"use client";

import { useEffect, useLayoutEffect, useRef, useState, useSyncExternalStore } from "react";
import { ArrowLeft, Menu, X } from "lucide-react";
import { businessSignInHref } from "@/lib/business-signin";
import { languageSwitch } from "@/lib/language-link";
import { businessPath, type BusinessLocale, type BusinessPage } from "@/lib/site-routes";
import { businessContent } from "./content";
import styles from "./business.module.css";
import languageStyles from "./business-language-link.module.css";
import shell from "./touchup-shell.module.css";
import { siteCopy } from "./site-copy";

function LanguageSwitch({
  locale,
  page,
  phone = false,
}: {
  locale: BusinessLocale;
  page: BusinessPage;
  phone?: boolean;
}) {
  const link = languageSwitch(locale, page);
  return (
    <span className={languageStyles.slot}>
      <a
        className={languageStyles.link}
        href={link.href}
        hrefLang={link.lang}
        lang={link.lang}
        data-language-switch=""
      >
        {phone ? (
          <span className={languageStyles.srOnly} lang={locale}>
            {link.phoneLabel}
          </span>
        ) : null}
        {link.label}
      </a>
    </span>
  );
}

const subscribeToHostname = () => () => {};
const getSignInSnapshot = () => businessSignInHref(window.location.hostname);
const getServerSignInSnapshot = () => null;

export function BusinessHeader({
  locale,
  page = "home",
}: {
  locale: BusinessLocale;
  page?: BusinessPage;
}) {
  const [open, setOpen] = useState(false);
  const signInHref = useSyncExternalStore(
    subscribeToHostname,
    getSignInSnapshot,
    getServerSignInSnapshot,
  );
  const header = useRef<HTMLElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLElement>(null);
  const copy = businessContent[locale].navigation;
  const home = businessPath(locale);
  const personal = page === "personal";
  const spanishOnly = page === "terms" || page === "deletion";
  const secondary = page === "contact" || page === "privacy" || spanishOnly;
  const primaryHref = personal
    ? "#early-access"
    : businessPath("es", "contact");
  const primaryLabel = personal
    ? locale === "es"
      ? "Acceso anticipado"
      : "Early access"
    : copy.demo;

  useLayoutEffect(() => {
    if (!open) return;
    const panel = menu.current;
    const control = trigger.current;
    if (!panel || !control) return;
    const viewport = window.visualViewport;
    const update = () => {
      if (getComputedStyle(control).display === "none") {
        if (panel.contains(document.activeElement) || document.activeElement === control) {
          header.current?.querySelector<HTMLAnchorElement>("a")?.focus({ preventScroll: true });
        }
        setOpen(false);
        return false;
      }
      const bottom = (viewport?.offsetTop ?? 0) + (viewport?.height ?? window.innerHeight);
      panel.style.setProperty("--mobile-nav-height", `${Math.max(0, bottom - panel.getBoundingClientRect().top)}px`);
      return true;
    };
    if (!update()) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    update();
    panel.querySelector<HTMLAnchorElement>("a")?.focus({ preventScroll: true });
    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.key === "Escape") {
        setOpen(false);
        control.focus({ preventScroll: true });
      } else if (event.key === "Tab") {
        const last = Array.from(panel.querySelectorAll<HTMLElement>("a[href],button:not([disabled])")).at(-1);
        if (!last) return;
        if (event.shiftKey && document.activeElement === control) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          control.focus({ preventScroll: true });
        }
      }
    };
    document.addEventListener("keydown", onKeyDown);
    window.addEventListener("resize", update);
    viewport?.addEventListener("resize", update);
    viewport?.addEventListener("scroll", update);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("resize", update);
      viewport?.removeEventListener("resize", update);
      viewport?.removeEventListener("scroll", update);
    };
  }, [open]);

  useEffect(() => {
    let frame = 0;
    const update = () => {
      header.current?.style.setProperty(
        "--scroll",
        String(Math.min(1, Math.max(0, window.scrollY / 160))),
      );
      header.current?.setAttribute(
        "data-condensed",
        window.scrollY > 0 ? "true" : "false",
      );
      frame = 0;
    };
    const scroll = () => {
      if (!frame) frame = window.requestAnimationFrame(update);
    };
    update();
    window.addEventListener("scroll", scroll, { passive: true });
    return () => {
      window.removeEventListener("scroll", scroll);
      window.cancelAnimationFrame(frame);
    };
  }, []);

  const languageLinks = spanishOnly ? null : personal ? (
    <span className={styles.languages} role="group" aria-label={copy.language}>
      {(["es", "en"] as const).map((language) => (
        <a
          key={language}
          href={businessPath(language, page)}
          hrefLang={language}
          lang={language}
          aria-current={locale === language ? "true" : undefined}
        >
          {language.toUpperCase()}
        </a>
      ))}
    </span>
  ) : (
    <LanguageSwitch locale={locale} page={page} />
  );
  const phoneLanguage = spanishOnly || personal ? languageLinks : (
    <LanguageSwitch locale={locale} page={page} phone />
  );
  const signIn = signInHref ? (
    <a className={styles.loginLink} href={signInHref}>
      {copy.login}
    </a>
  ) : (
    <button className={styles.loginLink} type="button" data-preview-unwired="true">
      {copy.login}
    </button>
  );
  const backLink = (
    <a href={home} className={styles.backLink}>
      <ArrowLeft size={16} aria-hidden="true" />
      {copy.back}
    </a>
  );

  return (
    <>
      <a className={styles.skip} href="#business-main">
        {copy.skip}
      </a>
      <header
        ref={header}
        data-condensed="false"
        className={`${styles.header} ${shell.header}`}
      >
        <a
          className={styles.wordmark}
          href={personal ? businessPath(locale, "personal") : home}
          aria-label={
            page === "personal" ? "Cuadrao Personal" : "Cuadrao Business"
          }
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src="/cuadrao-site/cuadrao-lockup-light.svg"
            width="150"
            height="40"
            alt="cuadrao"
          />
        </a>
        <span className={styles.mobileAudience}>
          {page === "personal" ? copy.personal : copy.business}
        </span>
        <nav className={styles.desktopNav} aria-label={copy.label}>
          <div className={styles.audienceNav}>
            <a
              className={page !== "personal" ? styles.activeNav : undefined}
              href={home}
              aria-current={page === "home" ? "page" : undefined}
            >
              {copy.business}
            </a>
            <a
              className={page === "personal" ? styles.activeNav : undefined}
              href={businessPath(locale, "personal")}
              aria-current={page === "personal" ? "page" : undefined}
            >
              {copy.personal}
            </a>
          </div>
          <div className={styles.utilityNav}>
            {secondary ? (
              backLink
            ) : null}
            {!secondary && (
              <a className={styles.buttonSmall} data-header-cta data-business-cta={!personal ? true : undefined} href={primaryHref}>
                {primaryLabel}
              </a>
            )}
            {!personal && !secondary && signIn}
            {languageLinks}
          </div>
        </nav>
        <button
          ref={trigger}
          type="button"
          className={styles.menuButton}
          aria-label={open ? copy.close : copy.menu}
          aria-expanded={open}
          aria-controls="business-mobile-menu"
          onClick={() => setOpen(!open)}
        >
          {open ? (
            <X size={23} aria-hidden="true" />
          ) : (
            <Menu size={23} aria-hidden="true" />
          )}
        </button>
        {open && (
          <nav
            ref={menu}
            id="business-mobile-menu"
            className={styles.mobileNav}
            aria-label={copy.label}
            onClick={(event) => {
              if (!event.defaultPrevented && (event.target as HTMLElement).closest("a")) setOpen(false);
            }}
          >
            <a href={home} aria-current={page === "home" ? "page" : undefined}>
              {copy.business}
            </a>
            <a
              href={businessPath(locale, "personal")}
              aria-current={page === "personal" ? "page" : undefined}
            >
              {copy.personal}
            </a>
            {page !== "personal" && (
              <a href={`${home}#preguntas`}>{siteCopy[locale].faqLink}</a>
            )}
            {secondary ? (
              backLink
            ) : (
              <a className={styles.button} href={primaryHref}>
                {primaryLabel}
              </a>
            )}
            {!personal && !secondary && signIn}
            {phoneLanguage}
          </nav>
        )}
      </header>
    </>
  );
}
