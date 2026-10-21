"use client";

import { House, Receipt, Tray, type Icon } from "@phosphor-icons/react";

/** The Business screens' icons: one shape each, outline when idle and filled when it is the screen you are on. */
export const NAV_GLYPHS = { overview: House, inbox: Tray, expenses: Receipt } as const satisfies Record<string, Icon>;

export function navGlyph(Glyph: Icon, size = 20) {
  function NavGlyph(active: boolean) {
    return <Glyph aria-hidden="true" size={size} weight={active ? "fill" : "regular"} />;
  }
  return NavGlyph;
}
