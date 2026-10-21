"use client";

import { MoreVertical } from "lucide-react";
import ActionMenu from "../ActionMenu";
import { formatRelativeDay, todayIso } from "../business-format";
import { headerCurrency, segmentSections, type IgualarView } from "./transacciones-model";
import { SignedAmount, StateIcon } from "./transacciones-parts";
import { useRowCommands } from "./transacciones-commands";
import { useTransaccionesWords } from "./transacciones-words";
import { movementName, type TransaccionesController } from "./useTransacciones";

/**
 * Transacciones on a phone: two-line rows of at least 64px, whatever the
 * density. The state icon and the name, then the date and the reason; at the
 * right the amount and the state word; then a 44px kebab.
 */
export function TransaccionesList({ controller, view, rowRef }: {
  controller: TransaccionesController;
  view: IgualarView;
  rowRef: (id: string, node: HTMLElement | null) => void;
}) {
  const { t, locale, stateWord, detail } = useTransaccionesWords();
  const commandsOf = useRowCommands(controller);
  const header = headerCurrency(view.movements, view.accountCurrency);
  const today = todayIso();
  return (
    <div data-testid="transacciones-list" className="overflow-hidden rounded-surface border border-[#DCE0DA] bg-white dark:border-white/10 dark:bg-[#1f2225]">
      {segmentSections(view).map((section) => (
        <section key={section.group ?? "all"} aria-label={section.group ? t(`business.transactions.groups.${section.group}`) : undefined}>
          {section.group ? (
            <h3 className="border-b border-[#DCE0DA] bg-[#F7F5EE] px-4 py-2 text-[13px] font-medium text-[#56635e] dark:border-white/10 dark:bg-[#191c1f] dark:text-white/65">
              {t(`business.transactions.groups.${section.group}`)}{section.count !== null ? <span className="ml-2 font-normal tabular-nums">{section.count}</span> : null}
            </h3>
          ) : null}
          <ul>
            {section.rows.map((movement) => {
              const name = movementName(movement);
              const commands = commandsOf(movement);
              const selected = controller.tray?.movementId === movement.id;
              return (
                <li key={movement.id} data-movement-id={movement.id} data-state={movement.match.state} aria-current={selected ? "true" : undefined} className="flex min-h-16 items-center border-b border-[#DCE0DA] last:border-b-0 aria-[current=true]:bg-[#eef3ec] dark:border-white/10 dark:aria-[current=true]:bg-[#24302b]">
                  <button ref={(node) => rowRef(movement.id, node)} type="button" onClick={() => controller.open(movement.id)} className="flex min-w-0 flex-1 items-center gap-3 rounded-item py-2.5 pl-4 pr-2 text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-[var(--cuadrao-green)]">
                    <StateIcon state={movement.match.state} />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[15px] font-medium text-[#172b26] dark:text-white">{name}</span>
                      <span className="mt-0.5 block truncate text-[13px] text-[#56635e] dark:text-white/65">{formatRelativeDay(movement.occurredOn, today, locale)} · {detail(movement)}</span>
                    </span>
                    <span className="shrink-0 text-right">
                      <span className="block text-[15px] font-medium text-[#172b26] dark:text-white"><SignedAmount money={movement.money} header={header} /></span>
                      <span className="mt-0.5 block text-[12px] text-[#56635e] dark:text-white/65">{stateWord(movement.match.state)}</span>
                    </span>
                  </button>
                  {commands.length ? (
                    <ActionMenu
                      actions={commands}
                      label={t("business.transactions.actions.more", { name })}
                      placement="below-end"
                      portal
                      renderTrigger={({ ref, open, toggle, menuId }) => (
                        <button ref={ref} type="button" data-testid="row-kebab" aria-label={t("business.transactions.actions.more", { name })} aria-haspopup="menu" aria-expanded={open} aria-controls={open ? menuId : undefined} onClick={toggle} className="mr-1 flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-[#56635e] hover:bg-black/5 dark:text-white/65 dark:hover:bg-white/10">
                          <MoreVertical className="h-5 w-5" aria-hidden="true" />
                        </button>
                      )}
                    />
                  ) : <span className="mr-1 w-11 shrink-0" aria-hidden="true" />}
                </li>
              );
            })}
          </ul>
        </section>
      ))}
    </div>
  );
}
