import type { RefreshOutcome } from "@/components/ui/pull-to-refresh";

/** The lists one workspace reload asks again for. */
export const RELOADED_LISTS = ["records", "notes", "emails"] as const;
export type ReloadedList = (typeof RELOADED_LISTS)[number];

/**
 * Who waits on a reload. A reload is the next revision; each list says when
 * it answered at a revision, and a wait ends once every list has answered at
 * or after its own. An answer from a load started earlier never ends it.
 */
export function createReloadWaits() {
  let shown = 0;
  let waits: { at: number; left: Set<ReloadedList>; failed: boolean; done: (outcome: RefreshOutcome) => void }[] = [];
  return {
    committed(revision: number) {
      shown = revision;
    },
    next: () => new Promise<RefreshOutcome>((done) => {
      waits.push({ at: shown + 1, left: new Set(RELOADED_LISTS), failed: false, done });
    }),
    answered(list: ReloadedList, at: number, ok: boolean) {
      waits = waits.filter((wait) => {
        if (at < wait.at) return true;
        wait.left.delete(list);
        wait.failed ||= !ok;
        if (wait.left.size) return true;
        wait.done(wait.failed ? "failed" : "updated");
        return false;
      });
    },
  };
}
