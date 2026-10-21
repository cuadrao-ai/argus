"use client";

import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { ArrowDown, FileText, Landmark, MoreHorizontal, Plus } from "lucide-react";
import { currencySymbol } from "@/lib/money-entry";
import pointerAffordances from "@/components/sidebar/pointerAffordances.module.css";
import ActionMenu from "../ActionMenu";
import { formatRelativeDay, todayIso } from "../business-format";
import { DENSITY_ROW_PX, type Density } from "./table-density";
import { headerCurrency, segmentSections, type IgualarView, type Movement, type Section } from "./transacciones-model";
import { AccountLabel, KeyHint, SignedAmount, StateIcon, Truncated, Unknown } from "./transacciones-parts";
import { commandForKey, useRowCommands, type Command } from "./transacciones-commands";
import { useTransaccionesWords } from "./transacciones-words";
import { movementName, type TransaccionesController } from "./useTransacciones";

export type ColumnKey = "contraparte" | "fecha" | "monto" | "detalle" | "categoria" | "cuenta" | "comprobante";

/** The columns, left to right: text left, numbers right; Contraparte pins left and Comprobante right. */
export const COLUMNS: readonly { key: ColumnKey; width: number | null; align: "left" | "right"; pin?: "left" | "right" }[] = [
  { key: "contraparte", width: 260, align: "left", pin: "left" },
  { key: "fecha", width: 84, align: "left" },
  { key: "monto", width: 136, align: "right" },
  { key: "detalle", width: null, align: "left" },
  { key: "categoria", width: 144, align: "left" },
  { key: "cuenta", width: 176, align: "left" },
  { key: "comprobante", width: 112, align: "right", pin: "right" },
];

export const PIN_CLASS = { left: "sticky left-0 z-10 shadow-[inset_-1px_0_0_#DCE0DA] dark:shadow-[inset_-1px_0_0_rgba(255,255,255,0.1)]", right: "sticky right-0 z-10 shadow-[inset_1px_0_0_#DCE0DA] dark:shadow-[inset_1px_0_0_rgba(255,255,255,0.1)]" } as const;
/** Opaque cells, so a pinned column covers what scrolls under it. Hover lights the row in 80ms; the open row is green-tinted. */
export const CELL = "border-b border-[#DCE0DA] bg-white px-3 transition-colors duration-[80ms] ease-out group-hover:bg-[#F7F5EE] group-aria-selected:bg-[#eef3ec] motion-reduce:transition-none dark:border-white/10 dark:bg-[#1f2225] dark:group-hover:bg-[#25292c] dark:group-aria-selected:bg-[#24302b]";
const ACTION = "inline-flex h-7 items-center whitespace-nowrap rounded-full border border-[#7d8a84]/50 bg-white px-2.5 text-[13px] font-medium text-[#172b26] transition-colors duration-100 hover:bg-[#F7F5EE] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--cuadrao-green)] dark:border-white/20 dark:bg-[#1f2225] dark:text-white dark:hover:bg-white/[0.06]";

const isField = (target: EventTarget | null) => target instanceof HTMLElement && (target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName));

export function TransaccionesTable({ controller, view, density, onSegmentStep, onRunKey, rowRef }: {
  controller: TransaccionesController;
  view: IgualarView;
  density: Density;
  onSegmentStep: (step: 1 | -1) => void;
  onRunKey: () => void;
  rowRef: (id: string, node: HTMLTableRowElement | null) => void;
}) {
  const { t, locale } = useTransaccionesWords();
  const commandsOf = useRowCommands(controller);
  const sections = segmentSections(view);
  const rows = sections.flatMap((section) => section.rows);
  const header = headerCurrency(view.movements);
  const today = todayIso();
  const [focusedId, setFocusedId] = useState<string | null>(null);
  const table = useRef<HTMLTableElement>(null);
  const lastIndex = useRef(0);
  const height = DENSITY_ROW_PX[density];
  // The server lists a segment newest first; Por igualar comes in its groups instead.
  const sorted = view.segment !== "por_igualar";

  const rowNode = (id: string) => table.current?.querySelector<HTMLTableRowElement>(`tr[data-movement-id="${CSS.escape(id)}"]`) ?? null;
  const ids = rows.map((row) => row.id).join("|");
  // A row that left the view (igualada, declined) hands focus to the row that took its place, so a run of keys keeps going.
  useEffect(() => {
    if (!focusedId || rows.some((row) => row.id === focusedId)) return;
    const next = rows[Math.min(lastIndex.current, rows.length - 1)];
    const hadFocus = !document.activeElement || document.activeElement === document.body || table.current?.contains(document.activeElement);
    setFocusedId(next?.id ?? null);
    if (next && hadFocus) rowNode(next.id)?.focus();
    // `ids` names the rows; the list object changes on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ids, focusedId]);

  const tabStop = focusedId && rows.some((row) => row.id === focusedId) ? focusedId : rows[0]?.id;

  const onKeyDown = (event: KeyboardEvent<HTMLTableElement>) => {
    if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.altKey || isField(event.target)) return;
    const row = (event.target as HTMLElement).closest<HTMLTableRowElement>("tr[data-movement-id]");
    const id = row?.dataset.movementId;
    const index = id ? rows.findIndex((item) => item.id === id) : -1;
    const move = (to: number) => {
      const target = rows[Math.max(0, Math.min(rows.length - 1, to))];
      if (!target) return;
      setFocusedId(target.id);
      rowNode(target.id)?.focus();
      // With the tray open, the tray follows the row: ↑ ↓ walk the run.
      if (controller.tray) controller.open(target.id);
    };
    const handled = (() => {
      if (event.key === "ArrowDown") return move(index + 1), true;
      if (event.key === "ArrowUp") return move(index - 1), true;
      if (event.key === "]") return onSegmentStep(1), true;
      if (event.key === "[") return onSegmentStep(-1), true;
      if (event.key === "Escape" && controller.tray) return controller.close(), true;
      const movement = id ? controller.byId.get(id) : undefined;
      if (!movement) return false;
      if (event.key === "Enter") return controller.open(movement.id), true;
      const command = commandForKey(commandsOf(movement), event.key);
      if (command) return command.run(), true;
      if (event.key.toLowerCase() === "i") return onRunKey(), true;
      return false;
    })();
    if (handled) event.preventDefault();
  };

  return (
    <div data-testid="transacciones-scroll" className="argus-thin-scrollbar relative max-h-[calc(100dvh-15rem)] min-h-[16rem] overflow-auto rounded-surface border border-[#DCE0DA] bg-white dark:border-white/10 dark:bg-[#1f2225]">
      <table
        ref={table}
        role="grid"
        aria-label={t("business.transactions.title")}
        aria-rowcount={rows.length}
        data-testid="transacciones-grid"
        data-density={density}
        onKeyDown={onKeyDown}
        className="w-full min-w-[1100px] table-fixed border-separate border-spacing-0 text-[14px] text-[#172b26] dark:text-white"
      >
        <colgroup>{COLUMNS.map((column) => <col key={column.key} style={column.width ? { width: column.width } : undefined} />)}</colgroup>
        <thead>
          <tr>
            {COLUMNS.map((column) => {
              const label = column.key === "monto" ? t("business.transactions.columns.monto", { currency: header ? currencySymbol(header) : "" }).trim() : t(`business.transactions.columns.${column.key}`);
              const sortHere = sorted && column.key === "fecha";
              return (
                <th
                  key={column.key}
                  scope="col"
                  data-col={column.key}
                  data-pinned={column.pin ? `top ${column.pin}` : "top"}
                  aria-sort={sortHere ? "descending" : undefined}
                  className={`sticky top-0 h-11 border-b border-[#DCE0DA] bg-white px-3 text-[13px] font-normal text-[#56635e] dark:border-white/10 dark:bg-[#1f2225] dark:text-white/65 ${column.align === "right" ? "text-right" : "text-left"} ${column.pin ? `${column.pin === "left" ? "left-0" : "right-0"} z-30` : "z-20"}`}
                >
                  {sortHere ? (
                    <span className="inline-flex min-h-7 items-center gap-1 font-medium text-[#172b26] dark:text-white">
                      {label}
                      <ArrowDown data-testid="sort-arrow" className="h-3.5 w-3.5" aria-hidden="true" />
                    </span>
                  ) : label}
                </th>
              );
            })}
          </tr>
        </thead>
        {sections.map((section) => (
          <SectionRows
            key={section.group ?? "all"}
            section={section}
            controller={controller}
            commandsOf={commandsOf}
            header={header}
            today={today}
            locale={locale}
            height={height}
            tabStop={tabStop}
            onFocusRow={(id) => {
              setFocusedId(id);
              lastIndex.current = rows.findIndex((row) => row.id === id);
            }}
            rowRef={rowRef}
          />
        ))}
      </table>
    </div>
  );
}

function SectionRows({ section, controller, commandsOf, header, today, locale, height, tabStop, onFocusRow, rowRef }: {
  section: Section;
  controller: TransaccionesController;
  commandsOf: (movement: Movement) => Command[];
  header: string | null;
  today: string;
  locale: string;
  height: number;
  tabStop: string | undefined;
  onFocusRow: (id: string) => void;
  rowRef: (id: string, node: HTMLTableRowElement | null) => void;
}) {
  const { t, detail } = useTransaccionesWords();
  return (
    <tbody>
      {section.group ? (
        <tr data-group={section.group}>
          <th colSpan={COLUMNS.length} scope="colgroup" className="h-9 border-b border-[#DCE0DA] bg-[#F7F5EE] px-3 text-left text-[13px] font-medium text-[#56635e] dark:border-white/10 dark:bg-[#191c1f] dark:text-white/65">
            <span className="sticky left-3">{t(`business.transactions.groups.${section.group}`)}{section.count !== null ? <span className="ml-2 font-normal tabular-nums">{section.count}</span> : null}</span>
          </th>
        </tr>
      ) : null}
      {section.rows.map((movement) => {
        const selected = controller.tray?.movementId === movement.id;
        const commands = commandsOf(movement);
        const name = movementName(movement);
        const sentence = detail(movement);
        return (
          <tr
            key={movement.id}
            ref={(node) => rowRef(movement.id, node)}
            data-movement-id={movement.id}
            data-state={movement.match.state}
            aria-selected={selected}
            tabIndex={movement.id === tabStop ? 0 : -1}
            style={{ height }}
            onFocus={(event) => { if (event.target === event.currentTarget) onFocusRow(movement.id); }}
            onClick={() => controller.open(movement.id)}
            className="group cursor-pointer outline-none focus-visible:[&>td]:shadow-[inset_0_2px_0_var(--cuadrao-green),inset_0_-2px_0_var(--cuadrao-green)]"
          >
            <td data-col="contraparte" data-pinned="left" className={`${CELL} ${PIN_CLASS.left} text-left group-aria-selected:shadow-[inset_2px_0_0_var(--cuadrao-green),inset_-1px_0_0_#DCE0DA]`}>
              <span className="flex min-w-0 items-center gap-2.5">
                <StateIcon state={movement.match.state} />
                <Truncated text={name} className="font-medium" />
              </span>
            </td>
            <td data-col="fecha" className={`${CELL} whitespace-nowrap text-left text-[#56635e] dark:text-white/65`}>{formatRelativeDay(movement.occurredOn, today, locale)}</td>
            <td data-col="monto" className={`${CELL} text-right font-medium tabular-nums`}><SignedAmount money={movement.money} header={header} /></td>
            <td data-col="detalle" className={`${CELL} text-left text-[#56635e] dark:text-white/65`}><Truncated text={sentence} /></td>
            <td data-col="categoria" className={`${CELL} text-left`}>{movement.categoryId ? <Truncated text={t(`business.category.${movement.categoryId}`, { defaultValue: movement.categoryId })} /> : <Unknown />}</td>
            <td data-col="cuenta" className={`${CELL} relative text-left`}>
              <AccountLabel account={movement.account} />
              <RowActions name={name} commands={commands.slice(0, 2)} all={commands} />
            </td>
            <td data-col="comprobante" data-pinned="right" className={`${CELL} ${PIN_CLASS.right} text-right`}>
              <ProofSlot movement={movement} name={name} commands={commands} onOpen={() => controller.open(movement.id)} />
            </td>
          </tr>
        );
      })}
    </tbody>
  );
}

/** Hover and keyboard focus reveal the row's actions over Categoría and Cuenta, never over a number; touch gets a kebab. */
function RowActions({ name, commands, all }: { name: string; commands: readonly Command[]; all: readonly Command[] }) {
  const { t } = useTransaccionesWords();
  if (all.length === 0) return null;
  return (
    <>
      <span className={`pointer-events-none absolute inset-y-0 right-0 items-center gap-1.5 bg-inherit pl-3 pr-2 opacity-0 transition-opacity duration-100 ease-out group-focus-within:pointer-events-auto group-focus-within:opacity-100 group-hover:pointer-events-auto group-hover:opacity-100 motion-reduce:transition-none ${pointerAffordances.finePointerActions}`}>
        {commands.map((command) => (
          <button
            key={command.id}
            type="button"
            tabIndex={-1}
            data-row-action={command.id}
            aria-label={`${command.label}: ${name}`}
            onClick={(event) => { event.stopPropagation(); command.run(); }}
            className={ACTION}
          >
            {command.label}<KeyHint>{command.key}</KeyHint>
          </button>
        ))}
      </span>
      <span className={`absolute inset-y-0 right-1 items-center ${pointerAffordances.touchSafeActions}`} onClick={(event) => event.stopPropagation()}>
        <ActionMenu
          actions={all}
          label={t("business.transactions.actions.more", { name })}
          placement="below-end"
          portal
          renderTrigger={({ ref, open, toggle, menuId }) => (
            <button ref={ref} type="button" data-testid="row-kebab" aria-label={t("business.transactions.actions.more", { name })} aria-haspopup="menu" aria-expanded={open} aria-controls={open ? menuId : undefined} onClick={toggle} className="flex h-11 w-11 items-center justify-center rounded-full text-[#56635e] hover:bg-black/5 dark:text-white/65 dark:hover:bg-white/10">
              <MoreHorizontal className="h-5 w-5" aria-hidden="true" />
            </button>
          )}
        />
      </span>
    </>
  );
}

/** The igualar slot: "¿Este?" on a suggestion, the proof's icon once igualada, a round "+" when proof is missing. */
function ProofSlot({ movement, name, commands, onOpen }: { movement: Movement; name: string; commands: readonly Command[]; onOpen: () => void }) {
  const { t } = useTransaccionesWords();
  const stop = (run: () => void) => (event: React.MouseEvent) => { event.stopPropagation(); run(); };
  const state = movement.match.state;
  if (state === "sugerencia") {
    return <button type="button" tabIndex={-1} onClick={stop(onOpen)} aria-label={t("business.transactions.actions.open_for", { name })} className="inline-flex h-7 items-center rounded-full border border-dashed border-[#56635e] px-2.5 text-[13px] font-medium text-[#172b26] hover:bg-[#F7F5EE] dark:border-white/50 dark:text-white dark:hover:bg-white/[0.06]">¿Este?</button>;
  }
  if (state === "igualada") {
    return <button type="button" tabIndex={-1} onClick={stop(onOpen)} aria-label={t("business.transactions.actions.open_for", { name })} className="inline-flex h-8 w-8 items-center justify-center rounded-full text-[#56635e] hover:bg-black/5 dark:text-white/65 dark:hover:bg-white/10"><FileText className="h-4 w-4" aria-hidden="true" /></button>;
  }
  if (state === "sin_movimiento") {
    return <span className="inline-flex h-8 w-8 items-center justify-center text-[#56635e] dark:text-white/65"><Landmark className="h-4 w-4" aria-hidden="true" /></span>;
  }
  const add = commands.find((command) => command.id === "agregar");
  if (state === "falta_comprobante") {
    return (
      <button type="button" tabIndex={-1} onClick={stop(add?.run ?? onOpen)} aria-label={t("business.transactions.actions.add_for", { name })} className="inline-flex h-8 w-8 items-center justify-center rounded-full border border-[#7d8a84]/60 text-[#172b26] hover:bg-[#F7F5EE] dark:border-white/30 dark:text-white dark:hover:bg-white/[0.06]">
        <Plus className="h-4 w-4" aria-hidden="true" />
      </button>
    );
  }
  // No lleva comprobante: a dash that says so, never an empty cell.
  return <Unknown meaning={t("business.transactions.states.no_lleva")} />;
}
