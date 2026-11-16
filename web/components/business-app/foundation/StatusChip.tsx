import type { ReactNode } from "react";
import palette from "../transacciones/records-overview-preview.module.css";
import chip from "./status-chip.module.css";

/** Every status chip is this wide, so a column of them lines up. */
export const STATUS_CHIP_WIDTH = 120;
/** Tones from the Registros palette: Listo's green, and the amber of Faltan datos for anything that needs a look. */
const TONES = { ready: palette.export, warning: palette.fiscal } as const;
export type StatusChipTone = keyof typeof TONES;

/** The fixed-width status chip: Estado in Registros, Diferente in the duplicate compare. */
export function StatusChip({ tone, children, ...data }: { tone: StatusChipTone; children: ReactNode } & { [attribute: `data-${string}`]: string }) {
  return <span {...data} style={{ width: STATUS_CHIP_WIDTH }} className={`${chip.workflow} ${chip.stage} ${TONES[tone]}`}>{children}</span>;
}
