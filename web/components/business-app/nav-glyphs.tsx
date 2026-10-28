"use client";

import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { ClockCounterClockwise, House, Receipt, Table, Tray, type Icon } from "@phosphor-icons/react";
import styles from "./nav-glyphs.module.css";

type Weight = "regular" | "fill";

/** A screen icon drawn in parts, so each part can act out the screen's meaning. */
export type NavGlyph = {
  name: "overview" | "inbox" | "transactions" | "invoicing" | "activity";
  /** Whether the move plays again when the pointer leaves: true for moves that read the same both ways. */
  replayOnLeave: boolean;
  draw: (weight: Weight, uid: string) => ReactNode;
};

// Each part is one subpath group of the Phosphor 2.1 icon of the same weight, copied so the icon at rest is the Phosphor icon.
const HOUSE: Record<Weight, string> = {
  regular: "M219.31,108.68l-80-80a16,16,0,0,0-22.62,0l-80,80A15.87,15.87,0,0,0,32,120v96a8,8,0,0,0,8,8h64a8,8,0,0,0,8-8V160h32v56a8,8,0,0,0,8,8h64a8,8,0,0,0,8-8V120A15.87,15.87,0,0,0,219.31,108.68ZM208,208H160V152a8,8,0,0,0-8-8H104a8,8,0,0,0-8,8v56H48V120l80-80,80,80Z",
  fill: "M224,120v96a8,8,0,0,1-8,8H160a8,8,0,0,1-8-8V164a4,4,0,0,0-4-4H108a4,4,0,0,0-4,4v52a8,8,0,0,1-8,8H40a8,8,0,0,1-8-8V120a16,16,0,0,1,4.69-11.31l80-80a16,16,0,0,1,22.62,0l80,80A16,16,0,0,1,224,120Z",
};

const TRAY: Record<Weight, string> = {
  regular: "M208,32H48A16,16,0,0,0,32,48V208a16,16,0,0,0,16,16H208a16,16,0,0,0,16-16V48A16,16,0,0,0,208,32Zm0,16V152h-28.7A15.86,15.86,0,0,0,168,156.69L148.69,176H107.31L88,156.69A15.86,15.86,0,0,0,76.69,152H48V48Zm0,160H48V168H76.69L96,187.31A15.86,15.86,0,0,0,107.31,192h41.38A15.86,15.86,0,0,0,160,187.31L179.31,168H208v40Z",
  fill: "M208,32H48A16,16,0,0,0,32,48V208a16,16,0,0,0,16,16H208a16,16,0,0,0,16-16V48A16,16,0,0,0,208,32Zm0,176H48V168H76.69L96,187.32A15.89,15.89,0,0,0,107.31,192h41.38A15.86,15.86,0,0,0,160,187.31L179.31,168H208v40Z",
};
/** The open space above the tray's lip: a receipt shows only inside it, so it slips in under the rim and out behind the lip. */
const TRAY_OPENING = "M208,48V152h-28.7A15.86,15.86,0,0,0,168,156.69L148.69,176H107.31L88,156.69A15.86,15.86,0,0,0,76.69,152H48V48Z";
const RECEIPT = "M92,64H164a8,8,0,0,1,8,8v64a8,8,0,0,1-8,8H92a8,8,0,0,1-8-8V72A8,8,0,0,1,92,64Zm8,16v48h56V80Z";

// Phosphor's table. Its cells are holes in the one frame path, so it moves as a whole.
const TABLE: Record<Weight, string> = {
  regular: "M224,48H32a8,8,0,0,0-8,8V192a16,16,0,0,0,16,16H216a16,16,0,0,0,16-16V56A8,8,0,0,0,224,48ZM40,112H80v32H40Zm56,0H216v32H96ZM216,64V96H40V64ZM40,160H80v32H40Zm176,32H96V160H216v32Z",
  fill: "M224,48H32a8,8,0,0,0-8,8V192a16,16,0,0,0,16,16H216a16,16,0,0,0,16-16V56A8,8,0,0,0,224,48ZM40,112H80v32H40Zm56,0H216v32H96ZM40,160H80v32H40Zm176,32H96V160H216v32Z",
};

/**
 * Which Phosphor icon means each screen. The rail draws these same icons in parts (below) so they can move;
 * everywhere else a screen's icon appears, such as its heading sentence, it uses this map.
 */
export const SCREEN_ICON: Record<NavGlyph["name"], Icon> = { overview: House, inbox: Tray, transactions: Table, invoicing: Receipt, activity: ClockCounterClockwise };

/** Phosphor's clock-counter-clockwise, split into its hands and its dial with the rewind arrow, so the hands can turn back. */
const CLOCK: Record<Weight, { hands: string; dial: string }> = {
  regular: {
    hands: "M136,80v43.47l36.12,21.67a8,8,0,0,1-8.24,13.72l-40-24A8,8,0,0,1,120,128V80a8,8,0,0,1,16,0Z",
    dial: "M128,32A95.44,95.44,0,0,0,60.08,60.15C52.81,67.51,46.35,74.59,40,82V64a8,8,0,0,0-16,0v40a8,8,0,0,0,8,8H72a8,8,0,0,0,0-16H49c7.15-8.42,14.27-16.35,22.39-24.57a80,80,0,1,1,1.66,114.75,8,8,0,1,0-11,11.64A96,96,0,1,0,128,32Z",
  },
  fill: {
    hands: "M128,72a8,8,0,0,0-8,8v48a8,8,0,0,0,3.88,6.86l40,24a8,8,0,1,0,8.24-13.72L136,123.47V80A8,8,0,0,0,128,72Z",
    dial: "M224,128A96,96,0,0,1,62.11,197.82a8,8,0,1,1,11-11.64A80,80,0,1,0,71.43,71.43C67.9,75,64.58,78.51,61.35,82L77.66,98.34A8,8,0,0,1,72,112H32a8,8,0,0,1-8-8V64a8,8,0,0,1,13.66-5.66L50,70.7c3.22-3.49,6.54-7,10.06-10.55A96,96,0,0,1,224,128Z",
  },
};

/** The Business screens' icons. Inicio's house hops and lands; a receipt drops into the Bandeja; Registros' table unfolds and settles. */
export const NAV_GLYPHS = {
  overview: {
    name: "overview",
    replayOnLeave: false,
    draw: (weight) => <path data-part="house" d={HOUSE[weight]} />,
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
    replayOnLeave: false,
    draw: (weight) => <path data-part="table" d={TABLE[weight]} />,
  },
  invoicing: {
    name: "invoicing",
    replayOnLeave: false,
    draw: (weight) => <g data-part="invoice-document"><Receipt weight={weight} size={256} /></g>,
  },
  activity: {
    name: "activity",
    replayOnLeave: false,
    draw: (weight) => <>
      <path data-part="clock-dial" d={CLOCK[weight].dial} />
      <path data-part="clock-hands" d={CLOCK[weight].hands} />
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
