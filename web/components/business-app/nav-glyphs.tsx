"use client";

import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import styles from "./nav-glyphs.module.css";

type Weight = "regular" | "fill";

/** A screen icon drawn in parts, so each part can act out the screen's meaning. */
export type NavGlyph = {
  name: "overview" | "inbox" | "transactions";
  /** Whether the move plays again when the pointer leaves: true for moves that read the same both ways. */
  replayOnLeave: boolean;
  draw: (weight: Weight, uid: string) => ReactNode;
};

// Each part is one subpath group of the Phosphor 2.1 icon of the same weight, copied so the icon at rest is the Phosphor icon.
const TILES: Record<Weight, readonly string[]> = {
  regular: [
    "M104,40H56A16,16,0,0,0,40,56v48a16,16,0,0,0,16,16h48a16,16,0,0,0,16-16V56A16,16,0,0,0,104,40Zm0,64H56V56h48v48Z",
    "M200,40H152a16,16,0,0,0-16,16v48a16,16,0,0,0,16,16h48a16,16,0,0,0,16-16V56A16,16,0,0,0,200,40Zm0,64H152V56h48v48Z",
    "M104,136H56a16,16,0,0,0-16,16v48a16,16,0,0,0,16,16h48a16,16,0,0,0,16-16V152A16,16,0,0,0,104,136Zm0,64H56V152h48v48Z",
    "M200,136H152a16,16,0,0,0-16,16v48a16,16,0,0,0,16,16h48a16,16,0,0,0,16-16V152A16,16,0,0,0,200,136Zm0,64H152V152h48v48Z",
  ],
  fill: [
    "M120,56v48a16,16,0,0,1-16,16H56a16,16,0,0,1-16-16V56A16,16,0,0,1,56,40h48A16,16,0,0,1,120,56Z",
    "M200,40H152a16,16,0,0,0-16,16v48a16,16,0,0,0,16,16h48a16,16,0,0,0,16-16V56A16,16,0,0,0,200,40Z",
    "M104,136H56a16,16,0,0,0-16,16v48a16,16,0,0,0,16,16h48a16,16,0,0,0,16-16V152A16,16,0,0,0,104,136Z",
    "M200,136H152a16,16,0,0,0-16,16v48a16,16,0,0,0,16,16h48a16,16,0,0,0,16-16V152A16,16,0,0,0,200,136Z",
  ],
};

const TRAY: Record<Weight, string> = {
  regular: "M208,32H48A16,16,0,0,0,32,48V208a16,16,0,0,0,16,16H208a16,16,0,0,0,16-16V48A16,16,0,0,0,208,32Zm0,16V152h-28.7A15.86,15.86,0,0,0,168,156.69L148.69,176H107.31L88,156.69A15.86,15.86,0,0,0,76.69,152H48V48Zm0,160H48V168H76.69L96,187.31A15.86,15.86,0,0,0,107.31,192h41.38A15.86,15.86,0,0,0,160,187.31L179.31,168H208v40Z",
  fill: "M208,32H48A16,16,0,0,0,32,48V208a16,16,0,0,0,16,16H208a16,16,0,0,0,16-16V48A16,16,0,0,0,208,32Zm0,176H48V168H76.69L96,187.32A15.89,15.89,0,0,0,107.31,192h41.38A15.86,15.86,0,0,0,160,187.31L179.31,168H208v40Z",
};
/** The open space above the tray's lip: a receipt shows only inside it, so it slips in under the rim and out behind the lip. */
const TRAY_OPENING = "M208,48V152h-28.7A15.86,15.86,0,0,0,168,156.69L148.69,176H107.31L88,156.69A15.86,15.86,0,0,0,76.69,152H48V48Z";
const RECEIPT = "M92,64H164a8,8,0,0,1,8,8v64a8,8,0,0,1-8,8H92a8,8,0,0,1-8-8V72A8,8,0,0,1,92,64Zm8,16v48h56V80Z";

const ARROWS: Record<Weight, { left: string; right: string }> = {
  regular: {
    left: "M74.34,117.66a8,8,0,0,0,11.32-11.32L67.31,88H208a8,8,0,0,0,0-16H67.31L85.66,53.66A8,8,0,0,0,74.34,42.34l-32,32a8,8,0,0,0,0,11.32Z",
    right: "M213.66,181.66l-32,32a8,8,0,0,1-11.32-11.32L188.69,184H48a8,8,0,0,1,0-16H188.69l-18.35-18.34a8,8,0,0,1,11.32-11.32l32,32A8,8,0,0,1,213.66,181.66Z",
  },
  fill: {
    left: "M42.34,85.66a8,8,0,0,1,0-11.32l32-32A8,8,0,0,1,88,48V72H208a8,8,0,0,1,0,16H88v24a8,8,0,0,1-13.66,5.66Z",
    right: "M213.66,170.34l-32-32A8,8,0,0,0,168,144v24H48a8,8,0,0,0,0,16H168v24a8,8,0,0,0,13.66,5.66l32-32A8,8,0,0,0,213.66,170.34Z",
  },
};

/** The Business screens' icons. Inicio's cards settle into place; a receipt drops into the Bandeja; Transacciones' money goes out and comes in. */
export const NAV_GLYPHS = {
  overview: {
    name: "overview",
    replayOnLeave: true,
    // A lone filled tile is convex, which Chrome draws with a slightly different edge than the joined icon, so the tiles stand in for the whole only while they move.
    draw: (weight) => <>
      {TILES[weight].map((d) => <path key={d} data-part="tile" d={d} />)}
      <path data-rest="" d={TILES[weight].join("")} />
    </>,
  },
  inbox: {
    name: "inbox",
    replayOnLeave: false,
    draw: (weight, uid) => {
      // The filled tray has no open space to show a receipt in, so the receipt is cut out of it instead.
      const receipt = <g clipPath={`url(#${uid}-opening)`}><path data-part="receipt" d={RECEIPT} fill={weight === "fill" ? "#000" : undefined} /></g>;
      return <>
        <defs>
          <clipPath id={`${uid}-opening`}><path d={TRAY_OPENING} /></clipPath>
          {weight === "fill" ? <mask id={`${uid}-cut`} maskUnits="userSpaceOnUse" x="0" y="0" width="256" height="256"><rect width="256" height="256" fill="#fff" />{receipt}</mask> : null}
        </defs>
        <g data-part="tray">
          <path d={TRAY[weight]} mask={weight === "fill" ? `url(#${uid}-cut)` : undefined} />
          {weight === "regular" ? receipt : null}
        </g>
      </>;
    },
  },
  transactions: {
    name: "transactions",
    replayOnLeave: true,
    draw: (weight) => <>
      <path data-part="arrow-left" d={ARROWS[weight].left} />
      <path data-part="arrow-right" d={ARROWS[weight].right} />
    </>,
  },
} as const satisfies Record<string, NavGlyph>;

/**
 * Plays the icon's move once. A move already playing finishes rather than restarting, and every
 * keyframe starts and ends at rest, so cutting a move short can only return the icon to rest.
 */
function playMove(icon: HTMLElement) {
  if (icon.dataset.move !== undefined || typeof icon.getAnimations !== "function") return;
  icon.dataset.move = "";
  const moves = icon.getAnimations({ subtree: true }).filter((animation) => {
    const target = (animation.effect as KeyframeEffect | null)?.target;
    return target instanceof Element && target.hasAttribute("data-part");
  });
  void Promise.all(moves.map((move) => move.finished)).catch(() => undefined).then(() => {
    delete icon.dataset.move;
  });
}

/**
 * One nav icon. Its row (the `button` around it) plays the move on pointer enter, on keyboard focus,
 * and when the icon becomes the current screen, never on first paint.
 */
export function NavIcon({ glyph, active, size = 20 }: { glyph: NavGlyph; active: boolean; size?: number }) {
  const ref = useRef<HTMLSpanElement>(null);
  const uid = `nav-${useId().replace(/[^\w-]/g, "")}`;
  const [shown, setShown] = useState(active);
  const [switched, setSwitched] = useState(false);
  if (shown !== active) {
    setShown(active);
    setSwitched(true);
  }

  useEffect(() => {
    const icon = ref.current;
    const row = icon?.closest("button");
    if (!icon || !row) return;
    const enter = (event: PointerEvent) => { if (event.pointerType !== "touch") playMove(icon); };
    const leave = (event: PointerEvent) => { if (event.pointerType !== "touch" && glyph.replayOnLeave) playMove(icon); };
    const focus = () => { if (row.matches(":focus-visible")) playMove(icon); };
    row.addEventListener("pointerenter", enter);
    row.addEventListener("pointerleave", leave);
    row.addEventListener("focus", focus);
    return () => {
      row.removeEventListener("pointerenter", enter);
      row.removeEventListener("pointerleave", leave);
      row.removeEventListener("focus", focus);
    };
  }, [glyph]);

  useEffect(() => {
    if (switched && active && ref.current) playMove(ref.current);
  }, [switched, active]);

  return (
    <span ref={ref} aria-hidden="true" data-nav-icon="" data-glyph={glyph.name} data-active={active} data-settle={switched && active ? "" : undefined} className={styles.icon}>
      {(["regular", "fill"] as const).map((weight) => (
        <svg key={weight} data-weight={weight} className={`${styles.layer} ${weight === "regular" ? styles.outline : styles.fill}`} xmlns="http://www.w3.org/2000/svg" width={size} height={size} fill="currentColor" viewBox="0 0 256 256">
          {glyph.draw(weight, `${uid}-${weight}`)}
        </svg>
      ))}
    </span>
  );
}

export function navGlyph(glyph: NavGlyph, size = 20) {
  function NavGlyphRow(active: boolean) {
    return <NavIcon glyph={glyph} active={active} size={size} />;
  }
  return NavGlyphRow;
}
