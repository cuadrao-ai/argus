"use client";

import { ArrowsLeftRight, SquaresFour, Tray, type Icon } from "@phosphor-icons/react";

/** The Business screens' icons: one shape each, outline when idle and filled when it is the screen you are on. */
// Inicio is a dashboard of cards; the Bandeja is a tray (its dot says what arrived); Gastos becomes Transacciones, money in and out.
export const NAV_GLYPHS = { overview: SquaresFour, inbox: Tray, expenses: ArrowsLeftRight, transactions: ArrowsLeftRight } as const satisfies Record<string, Icon>;

export function navGlyph(Glyph: Icon, size = 20) {
  function NavGlyph(active: boolean) {
    return <Glyph aria-hidden="true" size={size} weight={active ? "fill" : "regular"} />;
  }
  return NavGlyph;
}
