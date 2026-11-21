import Image from "next/image";
import type { ReactNode } from "react";
import { quietButtonClass } from "../business-ui";
import inboxArt from "./assets/inbox-empty.png";

export type ReceptionEmptyKind = "first_run" | "filtered" | "done";

/**
 * The Bandeja's empty state and tray art, shared with Inicio's first day. `compact` is the in-card spacing (as the
 * foundation EmptyState's), so a card grows only by the art; `children` takes the place of `action` when the caller
 * keeps its own button.
 */
export default function ReceptionEmptyState({ title, body, kind, action, compact = false, children }: { title: string; body: string; kind: ReceptionEmptyKind; action?: { label: string; run: () => void }; compact?: boolean; children?: ReactNode }) {
  return <div data-testid="reception-empty" data-empty-kind={kind} data-compact={compact ? "true" : undefined} className={`flex flex-col items-center text-center ${compact ? "px-5 py-6" : "py-12"}`}>
    <Image src={inboxArt} alt="" width={144} height={144} sizes="144px" className="object-contain" />
    <h3 className="mt-4 font-display text-[17px] font-medium text-[#172b26] dark:text-white">{title}</h3>
    <p className="mt-1 max-w-sm text-[14px] leading-relaxed text-[#56635e] dark:text-white/70">{body}</p>
    {action ? <button type="button" className={`mt-5 ${quietButtonClass}`} onClick={action.run}>{action.label}</button> : null}
    {children}
  </div>;
}
