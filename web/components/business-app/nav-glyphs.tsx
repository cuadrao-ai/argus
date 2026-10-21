"use client";

import { useState } from "react";
import { ArrowsLeftRight, SquaresFour, Tray, type Icon } from "@phosphor-icons/react";
import styles from "./nav-glyphs.module.css";

/** The Business screens' icons: one shape each, outline when idle and filled when it is the screen you are on. */
// Inicio is a dashboard of cards; the Bandeja is a tray (its dot says what arrived); Transacciones is money in and out.
export const NAV_GLYPHS = { overview: SquaresFour, inbox: Tray, transactions: ArrowsLeftRight } as const satisfies Record<string, Icon>;

/** One nav icon. It settles into place only when it becomes the current screen, never on first paint. Its row is the `group` whose hover lifts it. */
export function NavIcon({ glyph: Glyph, active, size = 20 }: { glyph: Icon; active: boolean; size?: number }) {
  const [shown, setShown] = useState(active);
  const [switched, setSwitched] = useState(false);
  if (shown !== active) {
    setShown(active);
    setSwitched(true);
  }
  return (
    <span aria-hidden="true" data-nav-icon="" data-active={active} data-settle={switched && active ? "" : undefined} className={`${styles.icon} group-hover:data-[active=false]:-translate-y-px`}>
      <Glyph data-weight="regular" className={`${styles.layer} ${styles.outline}`} size={size} weight="regular" />
      <Glyph data-weight="fill" className={`${styles.layer} ${styles.fill}`} size={size} weight="fill" />
    </span>
  );
}

export function navGlyph(Glyph: Icon, size = 20) {
  function NavGlyph(active: boolean) {
    return <NavIcon glyph={Glyph} active={active} size={size} />;
  }
  return NavGlyph;
}
