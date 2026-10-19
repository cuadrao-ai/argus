"use client";

import { useEffect, useState, type CSSProperties, type ReactNode } from "react";
import { cardClass } from "./business-ui";
import styles from "./business-skeletons.module.css";

export const SKELETON_DELAY_MS = 300;
export const CONTENT_FADE_MS = 150;
/** The screen-reader label is this word, and it is never visible. */
export const SCREEN_READER_LOADING_LABEL = "Cargando";

export type SkeletonLayout = "overview" | "inbox" | "updates" | "expenses" | "access" | "detail" | "rows";

export function placeholderPhase(elapsedMs: number, delayMs = SKELETON_DELAY_MS): "blank" | "skeleton" {
  return elapsedMs < delayMs ? "blank" : "skeleton";
}

export function useDelayedPending(pending: boolean): boolean {
  const [watch, setWatch] = useState(pending);
  const [elapsed, setElapsed] = useState(0);
  const currentElapsed = watch === pending ? elapsed : 0;
  // Reset during render so a new wait paints blank. An effect would run after that frame.
  if (watch !== pending) {
    setWatch(pending);
    setElapsed(0);
  }
  useEffect(() => {
    if (!pending) return;
    const id = window.setTimeout(() => setElapsed(SKELETON_DELAY_MS), SKELETON_DELAY_MS);
    return () => window.clearTimeout(id);
  }, [pending]);
  return pending && placeholderPhase(currentElapsed) === "skeleton";
}

function Bar({ className }: { className: string }) {
  return <span data-testid="business-skeleton-shimmer" className={`${styles.shimmer} ${styles.block} block ${className}`} />;
}

function ListShell({ children }: { children: ReactNode }) {
  return <div className={`${cardClass} divide-y divide-black/[0.05] p-2 dark:divide-white/[0.05]`}>{children}</div>;
}

function InboxRow() {
  return (
    <div className="flex items-center gap-3 px-3 py-3">
      <Bar className="h-11 w-11 shrink-0 rounded-[12px]" />
      <span className="min-w-0 flex-1 space-y-2">
        <Bar className="h-[15px] w-2/5" />
        <Bar className="h-[13px] w-3/5" />
      </span>
      <Bar className="h-[15px] w-16 shrink-0" />
      <Bar className="h-6 w-20 shrink-0 rounded-full" />
      <span className="h-4 w-4 shrink-0" />
    </div>
  );
}

function UpdateRow() {
  return (
    <div className="flex items-start gap-3 px-3 py-3">
      <Bar className="mt-0.5 h-5 w-5 shrink-0" />
      <Bar className="h-[14px] min-w-0 flex-1" />
      <Bar className="h-3 w-14 shrink-0" />
    </div>
  );
}

function ExpenseRow() {
  return (
    <div className="px-3 py-1">
      <div className="flex min-h-11 items-center gap-3 py-2">
        <span className="min-w-0 flex-1">
          <span className="flex h-[1lh] items-center text-[15px]"><Bar className="h-[15px] w-2/5" /></span>
          <span className="mt-0.5 flex h-[1lh] items-center text-[13px]"><Bar className="h-[13px] w-3/5" /></span>
        </span>
        <Bar className="h-[15px] w-16 shrink-0" />
        <span className="h-4 w-4 shrink-0" />
      </div>
    </div>
  );
}

function AccessRow() {
  return (
    <div className="flex items-center gap-3 px-3 py-3">
      <Bar className="h-11 w-11 shrink-0 rounded-[12px]" />
      <span className="min-w-0 flex-1 space-y-2">
        <Bar className="h-[15px] w-2/5" />
        <Bar className="h-[13px] w-3/5" />
      </span>
      <Bar className="h-11 w-28 shrink-0 rounded-full" />
    </div>
  );
}

type ListLayout = Exclude<SkeletonLayout, "overview" | "detail">;

const LIST_ROWS: Record<ListLayout, () => ReactNode> = {
  inbox: InboxRow,
  rows: InboxRow,
  updates: UpdateRow,
  expenses: ExpenseRow,
  access: AccessRow,
};

function OverviewSkeleton() {
  return (
    <div className="grid gap-3 tablet:grid-cols-2">
      <div className={`${cardClass} flex items-center gap-3 tablet:col-span-2`}>
        <Bar className="h-5 w-5 shrink-0 rounded-[12px]" />
        <span className="min-w-0 flex-1 space-y-2">
          <Bar className="h-5 w-2/5" />
          <Bar className="h-[13px] w-1/4" />
        </span>
      </div>
      <div className={cardClass}>
        <Bar className="h-[13px] w-2/5" />
        <Bar className="mt-3 h-6 w-1/2" />
        <Bar className="mt-3 h-3 w-3/5" />
      </div>
      <div className={cardClass}>
        <Bar className="h-[13px] w-2/5" />
        <Bar className="mt-3 h-6 w-1/2" />
        <Bar className="mt-3 h-3 w-3/5" />
      </div>
    </div>
  );
}

function DetailSkeleton() {
  return (
    <>
      <div className="mb-4 flex min-h-11 items-center">
        <Bar className="h-4 w-24" />
      </div>
      <div className="mb-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <Bar className="h-[25px] w-2/5 max-w-full" />
          <Bar className="h-6 w-24 shrink-0 rounded-full" />
        </div>
      </div>
      <div className="grid items-start gap-4 desktop:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div className={`${cardClass} p-3`}>
          <div data-testid="business-skeleton-preview" className={`${styles.shimmer} ${styles.block} hidden min-h-[200px] overflow-hidden rounded-[14px] desktop:flex desktop:min-h-[280px]`} />
        </div>
        <div className={`${cardClass} space-y-4`}>
          {Array.from({ length: 4 }, (_, index) => <Bar key={index} className="h-4 w-full" />)}
        </div>
      </div>
    </>
  );
}

function Rows({ count, layout }: { count: number; layout: ListLayout }) {
  const Row = LIST_ROWS[layout];
  return (
    <ListShell>
      {Array.from({ length: count }, (_, index) => <Row key={index} />)}
    </ListShell>
  );
}

export function BusinessSkeleton({ layout, rows = 3 }: { layout: SkeletonLayout; rows?: number }) {
  const count = layout === "rows" ? rows : 3;
  return (
    <div role="status" aria-live="polite" data-testid="business-loading" data-layout={layout}>
      <span className="sr-only">{SCREEN_READER_LOADING_LABEL}</span>
      <div aria-hidden="true">
        {layout === "overview" ? <OverviewSkeleton /> : layout === "detail" ? <DetailSkeleton /> : <Rows count={count} layout={layout} />}
      </div>
    </div>
  );
}

const fadeStyle = { "--business-content-fade": `${CONTENT_FADE_MS}ms` } as CSSProperties;

export function ContentFade({ children }: { children: ReactNode }) {
  return <div className={styles.fade} style={fadeStyle}>{children}</div>;
}

export function Settle({ pending, layout, rows = 3, children = null }: { pending: boolean; layout: SkeletonLayout; rows?: number; children?: ReactNode }) {
  const showSkeleton = useDelayedPending(pending);
  if (pending) return showSkeleton ? <BusinessSkeleton layout={layout} rows={rows} /> : null;
  return <ContentFade>{children}</ContentFade>;
}

export function DelayedSourceWell() {
  const ready = useDelayedPending(true);
  if (!ready) return null;
  return (
    <span role="status" aria-live="polite" className="block h-full w-full">
      <span className="sr-only">{SCREEN_READER_LOADING_LABEL}</span>
      <span aria-hidden="true" data-testid="business-skeleton-shimmer" className={`${styles.shimmer} ${styles.block} block h-full w-full rounded-[14px]`} />
    </span>
  );
}
