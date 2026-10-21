"use client";

import { useState } from "react";
import BottomSheet, { type SheetSnaps } from "@/components/ui/BottomSheet";

// Neutral names on purpose. Naming these after product surfaces read as a list
// of shipped features and caused real confusion; the playground demonstrates
// the primitive, not a roadmap.
const detents: Array<{
  id: string;
  snaps: SheetSnaps;
  label: string;
  name: string;
}> = [
  { id: "all", snaps: ["peek", "half", "full"], label: "Peek, half and full", name: "Three snaps" },
  { id: "form", snaps: ["half", "full"], label: "Half and full", name: "Form" },
  { id: "full", snaps: ["full"], label: "Full only", name: "Long content" },
  { id: "fit", snaps: "fit", label: "Hugs its content", name: "Menu" },
];

export default function BottomSheetPlaygroundClient() {
  const [openHeight, setOpenHeight] = useState<string | null>(null);
  const [nested, setNested] = useState(false);
  const [isDark, setIsDark] = useState(true);

  const toggleTheme = () => {
    const root = document.documentElement;
    const nextIsDark = !root.classList.contains("dark");
    root.classList.toggle("dark", nextIsDark);
    setIsDark(nextIsDark);
  };

  const openDetent = detents.find((detent) => detent.id === openHeight);

  return (
    <main className="min-h-[100dvh] bg-[#eef0ed] px-4 py-6 text-black dark:bg-[#101113] dark:text-white">
      <div className="mx-auto flex w-full max-w-[720px] flex-col gap-6">
        <header className="flex flex-col gap-2">
          <p className="text-[12px] font-medium tracking-[0.16px] text-[#8d969e]">
            Dev only
          </p>
          <h1 className="font-display text-[32px] font-medium tracking-[-0.32px]">
            Bottom sheet playground
          </h1>
          <p className="max-w-[52ch] text-[14px] leading-relaxed text-black/60 dark:text-white/60">
            One primitive and its snap sets. Let go between two snaps and it
            springs to the nearest; a quick flick down closes it from any
            height; a slow drag closes it only below half of the lowest snap.
          </p>
        </header>

        <button
          type="button"
          onClick={toggleTheme}
          className="min-h-11 w-fit rounded-full border border-black/15 px-5 text-[14px] font-medium transition-colors hover:bg-black/5 focus-visible:outline-none focus-visible:ring-[0.125rem] focus-visible:ring-black/25 dark:border-white/20 dark:hover:bg-white/5 dark:focus-visible:ring-white/30"
        >
          {isDark ? "Switch to light" : "Switch to dark"}
        </button>

        <div className="grid gap-3">
          {detents.map((detent) => (
            <button
              key={detent.id}
              type="button"
              data-testid={`open-${detent.id}`}
              onClick={() => setOpenHeight(detent.id)}
              className="flex min-h-11 items-center justify-between gap-4 rounded-[16px] border border-black/10 bg-white px-5 py-3 text-left transition-colors hover:bg-black/[0.03] focus-visible:outline-none focus-visible:ring-[0.125rem] focus-visible:ring-black/25 dark:border-white/10 dark:bg-white/[0.03] dark:hover:bg-white/[0.06] dark:focus-visible:ring-white/30"
            >
              <span className="text-[15px] font-medium">{detent.name}</span>
              <span className="text-[13px] text-black/50 dark:text-white/50">
                {detent.label}
              </span>
            </button>
          ))}
        </div>
      </div>

      {openDetent && (
        <BottomSheet
          isOpen
          snaps={openDetent.snaps}
          title={openDetent.name}
          description={`Snaps: ${openDetent.label.toLowerCase()}.`}
          closeLabel="Close sheet"
          onClose={() => setOpenHeight(null)}
          footer={
            <button
              type="button"
              data-testid="sheet-primary-action"
              onClick={() => setOpenHeight(null)}
              className="min-h-11 w-full rounded-full bg-black px-6 text-[15px] font-medium text-white transition-opacity hover:opacity-85 focus-visible:outline-none focus-visible:ring-[0.125rem] focus-visible:ring-black/25 dark:bg-white dark:text-black dark:focus-visible:ring-white/30"
            >
              Primary action
            </button>
          }
        >
          <div className="flex flex-col gap-4 pt-2">
            <button type="button" data-testid="open-nested" onClick={() => setNested(true)} className="min-h-11 w-fit rounded-full border border-black/15 px-5 text-[14px] font-medium dark:border-white/20">
              Open a second sheet
            </button>
            <label className="flex flex-col gap-2">
              <span className="text-[13px] font-medium text-black/55 dark:text-white/55">
                Sample input
              </span>
              <input
                data-testid="sheet-input"
                defaultValue="10,000"
                className="min-h-11 w-full rounded-[12px] border border-black/10 bg-black/[0.02] px-3 outline-none focus:border-black/25 dark:border-white/10 dark:bg-white/[0.04] dark:focus:border-white/25"
              />
            </label>
            {Array.from({ length: 12 }, (_, index) => (
              <p
                key={index}
                className="text-[14px] leading-relaxed text-black/60 dark:text-white/60"
              >
                Scrollable body row {index + 1}. The body scrolls inside the
                sheet and contains its overscroll, so the page behind it stays
                put.
              </p>
            ))}
          </div>
        </BottomSheet>
      )}
      {openDetent && nested ? (
        <BottomSheet isOpen snaps={["half"]} title="Second sheet" closeLabel="Close sheet" backLabel="Back" onClose={() => setNested(false)}>
          <p className="pt-2 text-[14px] text-black/70 dark:text-white/70">This replaced the first sheet. The back arrow returns to it.</p>
        </BottomSheet>
      ) : null}
    </main>
  );
}
