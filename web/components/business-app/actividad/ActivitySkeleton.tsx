"use client";

import { Fragment } from "react";
import { SCREEN_READER_LOADING_LABEL, useDelayedPending } from "../business-skeletons";
import styles from "../business-skeletons.module.css";
import { ACTIVITY_CARD, ACTIVITY_DAY, ACTIVITY_GRID, ACTIVITY_GRID_LIVE, ACTIVITY_HEADER_ROW, ACTIVITY_ROW } from "./activity-layout";

/** Bar widths vary row to row, as real names and actions do; fixed so the placeholder never flickers. */
const ROWS = [
  { name: "w-24", what: "w-32", record: "w-40" },
  { name: "w-20", what: "w-28", record: "w-36" },
  { name: "w-28", what: "w-36", record: "w-32" },
  { name: "w-24", what: "w-24", record: "w-44" },
  { name: "w-20", what: "w-40", record: "w-28" },
  { name: "w-28", what: "w-28", record: "w-36" },
  { name: "w-24", what: "w-32", record: "w-32" },
  { name: "w-20", what: "w-36", record: "w-40" },
] as const;
/** A second day starts after the fifth row, as a real history usually does. */
const DAY_BREAKS = new Set([0, 5]);

function Bar({ className }: { className: string }) {
  return <span data-testid="business-skeleton-shimmer" className={`${styles.shimmer} ${styles.block} block rounded-mark ${className}`} />;
}

/**
 * Actividad while its first page loads: the same card, column header, day bands and row heights as
 * the history, so content lands in place. Shown only after the shared 300ms delay; the shimmer stops
 * under reduced motion through the shared skeleton styles.
 */
export default function ActivitySkeleton({ columns, withRecord = true }: { columns: readonly string[]; withRecord?: boolean }) {
  const grid = withRecord ? ACTIVITY_GRID : ACTIVITY_GRID_LIVE;
  const show = useDelayedPending(true);
  if (!show) return null;
  return (
    <div role="status" aria-live="polite" data-testid="activity-loading">
      <span className="sr-only">{SCREEN_READER_LOADING_LABEL}</span>
      <div aria-hidden="true" className={ACTIVITY_CARD}>
        <div className={`${ACTIVITY_HEADER_ROW} ${grid}`}>
          {columns.map((label, index) => <span key={label} className={index === columns.length - 1 ? "text-right" : undefined}>{label}</span>)}
        </div>
        {ROWS.map((row, index) => (
          <Fragment key={index}>
            {/* Each bar sits in a box the height of the text line it stands for, so every band and row matches the loaded history. */}
            {DAY_BREAKS.has(index) ? <div className={ACTIVITY_DAY}><span className="flex h-5 items-center"><Bar className="h-[13px] w-24" /></span></div> : null}
            <div className="border-b border-[#dce0da] last:border-0 dark:border-white/10"><div className={`${ACTIVITY_ROW} ${grid}`}>
              {/* Desktop: avatar and name, what happened, record, area, time on the right. */}
              <span className="hidden items-center gap-2.5 md:flex"><Bar className="h-6 w-6 shrink-0 !rounded-full" /><Bar className={`h-[14px] ${row.name}`} /></span>
              <Bar className={`hidden h-[14px] md:block ${row.what}`} />
              {withRecord ? <Bar className={`hidden h-[14px] md:block ${row.record}`} /> : null}
              <Bar className="hidden h-[14px] w-20 md:block" />
              <Bar className="ml-auto hidden h-[14px] w-16 md:block" />
              {/* Phone: avatar, the sentence, the record, then area and time. */}
              <span className="flex gap-3 md:hidden">
                <Bar className="mt-0.5 h-8 w-8 shrink-0 !rounded-full" />
                <span className="min-w-0 flex-1">
                  <span className="flex h-[20.625px] items-center"><Bar className="h-[15px] w-4/5" /></span>
                  {withRecord ? <span className="mt-0.5 flex h-[20.625px] items-center"><Bar className="h-[15px] w-1/2" /></span> : null}
                  <span className="mt-1 flex h-[19.5px] items-center"><Bar className="h-[13px] w-1/3" /></span>
                </span>
              </span>
            </div></div>
          </Fragment>
        ))}
      </div>
    </div>
  );
}
