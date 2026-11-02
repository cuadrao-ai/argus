import type { ListoApproval, ListoItem } from "@/lib/business-api";
import { loadFailure } from "../bandeja-sources";

/** The route takes this many items; a longer selection is sent as several requests. */
export const LISTO_LIMIT = 50;

export type ListoTarget = ListoItem & { rowId: string; title: string };
export type ListoBatch = { key: string; targets: readonly ListoTarget[] };
/** `refused` needs a person; `unknown` settles by replaying `key`, never under a new one. */
export type ListoFailure = { target: ListoTarget; kind: "refused" | "unknown"; code: string | null; reference: string | null; key: string };
export type ListoRun = { applied: string[]; failed: ListoFailure[] };
type Send = (items: readonly ListoItem[], key: string) => Promise<{ results: ListoApproval[] }>;

export function listoBatches(targets: readonly ListoTarget[], newKey: () => string): ListoBatch[] {
  const batches: ListoBatch[] = [];
  for (let start = 0; start < targets.length; start += LISTO_LIMIT) batches.push({ key: newKey(), targets: targets.slice(start, start + LISTO_LIMIT) });
  return batches;
}

/** What may be asked again, each under the key it was first sent with, so nothing posts twice. */
export function replayBatches(failed: readonly ListoFailure[]): ListoBatch[] {
  const byKey = new Map<string, ListoTarget[]>();
  for (const failure of failed) if (failure.kind === "unknown") byKey.set(failure.key, [...(byKey.get(failure.key) ?? []), failure.target]);
  return [...byKey].map(([key, targets]) => ({ key, targets }));
}

const codeOf = (error: unknown) => (typeof error === "object" && error !== null && "code" in error && typeof error.code === "string" ? error.code : null);

async function runBatch(send: Send, { key, targets }: ListoBatch): Promise<ListoRun> {
  const answered = await send(targets.map(({ draft_id, version }) => ({ draft_id, version })), key).then(({ results }) => ({ results, error: null }), (error: unknown) => ({ results: [] as ListoApproval[], error }));
  const run: ListoRun = { applied: [], failed: [] };
  const failure = answered.error === null ? null : loadFailure(answered.error);
  for (const target of targets) {
    const result = answered.results.find(item => item.draft_id === target.draft_id);
    if (result?.outcome === "applied") run.applied.push(target.rowId);
    else if (result) run.failed.push({ target, key, kind: result.outcome === "refused" ? "refused" : "unknown", code: result.code ?? null, reference: null });
    else run.failed.push({ target, key, kind: failure?.refused ? "refused" : "unknown", code: codeOf(answered.error), reference: failure?.reference ?? null });
  }
  return run;
}

/** Every batch runs whatever the one before it answered, as every item of a list does. */
export async function runListoBatches(send: Send, batches: readonly ListoBatch[]): Promise<ListoRun> {
  const run: ListoRun = { applied: [], failed: [] };
  for (const batch of batches) {
    const part = await runBatch(send, batch);
    run.applied.push(...part.applied);
    run.failed.push(...part.failed);
  }
  return run;
}
