"use client";

import { useEffect, useRef, type MouseEvent, type PointerEvent } from "react";
import { businessPath, type BusinessLocale, type BusinessPage } from "@/lib/site-routes";
import styles from "./business-language-toggle.module.css";

type Edges = { left: number; width: number };

export function BusinessLanguageToggle({
  locale,
  page,
  label,
}: {
  locale: BusinessLocale;
  page: BusinessPage;
  label: string;
}) {
  const track = useRef<HTMLSpanElement>(null);
  const thumb = useRef<HTMLSpanElement>(null);
  const active = useRef<Animation | null>(null);
  const request = useRef(0);

  const stop = () => {
    request.current += 1;
    active.current?.cancel();
    active.current = null;
  };

  useEffect(() => () => {
    request.current += 1;
    active.current?.cancel();
  }, []);

  const edges = (language: BusinessLocale): Edges | null => {
    const link = track.current?.querySelector<HTMLAnchorElement>(`a[lang="${language}"]`);
    return link ? { left: link.offsetLeft, width: link.offsetWidth } : null;
  };

  const currentEdges = (): Edges | null => {
    if (!track.current || !thumb.current) return null;
    const base = track.current.getBoundingClientRect();
    const current = thumb.current.getBoundingClientRect();
    return { left: current.left - base.left, width: current.width };
  };

  const animateTo = (target: Edges, duration: number, stretch = false): Animation | null => {
    const from = currentEdges();
    if (!from || !thumb.current?.animate) return null;
    stop();
    const middle = {
      left: `${(from.left + target.left) / 2 - (stretch ? 4 : 0)}px`,
      width: `${(from.width + target.width) / 2 + (stretch ? 8 : 0)}px`,
    };
    const animation = thumb.current.animate(
      [
        { left: `${from.left}px`, width: `${from.width}px` },
        middle,
        { left: `${target.left}px`, width: `${target.width}px` },
      ],
      { duration, easing: "cubic-bezier(.2,.75,.25,1)", fill: "forwards" },
    );
    active.current = animation;
    return animation;
  };

  const restore = () => {
    const target = edges(locale);
    if (target && !window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      animateTo(target, 160);
    } else {
      stop();
    }
  };

  const reach = (event: PointerEvent<HTMLAnchorElement>, language: BusinessLocale) => {
    if (language === locale || event.button !== 0 || event.metaKey || event.ctrlKey || event.altKey || event.shiftKey ||
        window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const from = edges(locale);
    const to = edges(language);
    if (!from || !to) return;
    animateTo(
      to.left > from.left
        ? { left: from.left, width: from.width + 14 }
        : { left: from.left - 14, width: from.width + 14 },
      120,
    );
  };

  const navigate = (event: MouseEvent<HTMLAnchorElement>, language: BusinessLocale) => {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.altKey || event.shiftKey ||
        language === locale || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const to = edges(language);
    if (!to || !thumb.current?.animate) return;
    event.preventDefault();
    const href = event.currentTarget.href;
    const animation = animateTo(to, 210, true);
    if (!animation) {
      window.location.assign(href);
      return;
    }
    const thisRequest = request.current;
    void animation.finished.then(() => {
      if (request.current === thisRequest) window.location.assign(href);
    }).catch(() => {});
  };

  return (
    <span ref={track} className={styles.track} role="group" aria-label={label} data-locale={locale}>
      <span ref={thumb} className={styles.thumb} aria-hidden="true" />
      {(["es", "en"] as const).map((language) => (
        <a
          key={language}
          href={businessPath(language, page)}
          hrefLang={language}
          lang={language}
          aria-current={locale === language ? "true" : undefined}
          onPointerDown={(event) => reach(event, language)}
          onPointerLeave={(event) => {
            if (event.pointerType === "mouse" && event.buttons === 1) restore();
          }}
          onPointerCancel={restore}
          onClick={(event) => navigate(event, language)}
        >
          {language.toUpperCase()}
        </a>
      ))}
    </span>
  );
}
