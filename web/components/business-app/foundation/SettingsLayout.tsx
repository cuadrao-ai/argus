"use client";

import { useId, useState, type ReactNode } from "react";
import { ChevronDown } from "lucide-react";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import { FOCUS_RING } from "./presentation";

/**
 * Negocio's tabs share one frame: the tabs, 24px, then a 40rem main column at the canvas's left edge.
 * A tab may add one supporting column of 20rem beside it, only when the canvas has room for both;
 * otherwise the supporting content follows the main column, collapsed on a phone.
 */
export function SettingsLayout({ tabs, children }: { tabs: ReactNode; children: ReactNode }) {
  return (
    <div data-testid="settings-layout" className="@container">
      <div className="mb-6">{tabs}</div>
      {children}
    </div>
  );
}

type Compact = { label: string; detail?: string; content: ReactNode };

/** The main card keeps the same 40rem on every tab; `aside` never widens or narrows it. */
export function SettingsColumns({ main, aside, compact }: { main: ReactNode; aside?: ReactNode; compact?: Compact }) {
  const { isBelowTablet: phone } = useResponsiveLayout();
  return (
    <div data-testid="settings-columns" className={`grid items-start gap-6 ${aside ? "@[61.5rem]:grid-cols-[minmax(0,40rem)_20rem]" : ""}`}>
      <div className="min-w-0 max-w-[40rem] space-y-6">{main}</div>
      {aside ? <div className="min-w-0 max-w-[40rem]">{phone && compact ? <CompactAside {...compact} /> : aside}</div> : null}
    </div>
  );
}

function CompactAside({ label, detail, content }: Compact) {
  const [open, setOpen] = useState(false);
  const id = useId();
  return (
    <section className="rounded-surface border border-[#DCE0DA] bg-[#FFFEFA] p-2 dark:border-white/10 dark:bg-[#1f2225]">
      <button type="button" aria-expanded={open} aria-controls={id} onClick={() => setOpen((value) => !value)} className={`flex min-h-11 w-full items-center gap-3 rounded-item px-4 py-2 text-left ${FOCUS_RING}`}>
        <span className="min-w-0 flex-1">
          <span className="block text-[16px] font-medium text-[#172b26] dark:text-white">{label}</span>
          {detail ? <span className="block text-[14px] text-[#56635e] dark:text-white/70">{detail}</span> : null}
        </span>
        <ChevronDown aria-hidden="true" className={`h-4 w-4 shrink-0 text-[#56635e] transition-transform duration-150 ease-out motion-reduce:transition-none dark:text-white/70 ${open ? "rotate-180" : ""}`} />
      </button>
      <div id={id} hidden={!open} className="px-4 pb-2">{content}</div>
    </section>
  );
}
