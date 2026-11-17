import type { ReactNode } from "react";
import palette from "../transacciones/records-overview-preview.module.css";
import chip from "./status-chip.module.css";

/** Every status chip is this wide, so a column of them lines up. */
export const STATUS_CHIP_WIDTH = 120;
/** Tones from the Registros palette (Listo's green, the amber of Faltan datos for anything that needs a look) and Bandeja's softer pairs. */
const TONES = { ready: palette.export, warning: palette.fiscal, attention: chip.attention, reading: chip.reading, approved: chip.approved, neutral: chip.neutral } as const;
export type StatusChipTone = keyof typeof TONES;
type ChipProps = { tone: StatusChipTone; children: ReactNode } & { [attribute: `data-${string}`]: string };

/** The fixed-width status chip: Estado in Registros, Diferente in the duplicate compare. */
export function StatusChip({ tone, children, ...data }: ChipProps) {
  return <span {...data} style={{ width: STATUS_CHIP_WIDTH }} className={`${chip.workflow} ${chip.stage} ${TONES[tone]}`}>{children}</span>;
}

/** The same chip at the width of its words: Estado in Bandeja, where "En espera hasta mañana" needs more than the fixed width. */
export function StatusPill({ tone, children, ...data }: ChipProps) {
  return <span {...data} className={`${chip.workflow} ${TONES[tone]}`}>{children}</span>;
}
