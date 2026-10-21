"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowLeft, Menu, X } from "lucide-react";
import { businessPath, type BusinessPage } from "@/lib/site-routes";
import { businessContent, type BusinessLocale } from "./content";
import styles from "./business.module.css";
import shell from "./touchup-shell.module.css";
import { siteCopy } from "./site-copy";

export function BusinessHeader({
  locale,
  page = "home",
}: {
  locale: BusinessLocale;
  page?: BusinessPage;
}) {
  const [open, setOpen] = useState(false);
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

  useEffect(() => {
    if (!open) return;
    menu.current?.querySelector<HTMLAnchorElement>("a")?.focus();
    const closeOnEscape = (event: KeyboardEvent): void => {
      if (event.key === "Escape") {
        setOpen(false);
        trigger.current?.focus();
      }
    };
    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
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

  const languageLinks = spanishOnly ? null : (
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
            ) : !personal ? (
              <>
                <a href={`${home}#el-producto`}>
                  {copy.howItWorks}
                </a>
                <a href={`${home}#nosotros`}>{copy.about}</a>
              </>
            ) : null}
            {languageLinks}
            {!secondary && (
              <a className={styles.buttonSmall} href={primaryHref}>
                {primaryLabel}
              </a>
            )}
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
              if ((event.target as HTMLElement).closest("a")) setOpen(false);
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
            {!personal && (
              <a href={`${home}#el-producto`}>{copy.howItWorks}</a>
            )}
            {!personal && <a href={`${home}#nosotros`}>{copy.about}</a>}
            {page !== "personal" && (
              <a href={`${home}#preguntas`}>{siteCopy[locale].faqLink}</a>
            )}
            {languageLinks}
            {secondary ? (
              backLink
            ) : (
              <a className={styles.button} href={primaryHref}>
                {primaryLabel}
              </a>
            )}
          </nav>
        )}
      </header>
    </>
  );
}
