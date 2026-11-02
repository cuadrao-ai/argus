import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { randomId } from "@/lib/random-id";
import { showToast } from "../foundation/toasts";
import { listoBatches, replayBatches, runListoBatches, type ListoBatch, type ListoFailure, type ListoTarget } from "./reception-approval";
import type { ListoApproval, ListoItem } from "@/lib/business-api";

type Options = {
  send: (items: readonly ListoItem[], key: string) => Promise<{ results: ListoApproval[] }>;
  reload: () => void;
  /** Failed rows stay selected; nothing else does. */
  select: (rowIds: string[]) => void;
  settled: () => void;
};

/** Asking, sending and what came back for one approval of Listos rows. Only the confirm sends. */
export function useListosApproval({ send, reload, select, settled }: Options) {
  const { t } = useTranslation();
  const [asking, setAsking] = useState<readonly ListoTarget[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState<readonly ListoFailure[]>([]);
  const [attempted, setAttempted] = useState(0);
  // A second press in the same frame must not send under a new key.
  const sending = useRef(false);
  const run = async (batches: readonly ListoBatch[], total: number, kept: readonly ListoFailure[]) => {
    if (sending.current) return;
    sending.current = true;
    setBusy(true);
    const result = await runListoBatches(send, batches);
    const remaining = [...kept, ...result.failed];
    sending.current = false;
    setBusy(false);
    setAsking(null);
    setFailed(remaining);
    setAttempted(total);
    select(remaining.map(failure => failure.target.rowId));
    reload();
    if (!remaining.length) showToast({ kind: "success", text: t("business.reception_preview.placeholder.approved", { count: result.applied.length }) });
    settled();
  };
  return {
    asking,
    busy,
    failed,
    attempted,
    ask: (targets: readonly ListoTarget[]) => { setFailed([]); setAsking(targets); },
    cancel: () => { if (!busy) setAsking(null); },
    confirm: () => { if (asking) void run(listoBatches(asking, randomId), asking.length, []); },
    retry: () => { void run(replayBatches(failed), attempted, failed.filter(failure => failure.kind === "refused")); },
    dismiss: () => setFailed([]),
  };
}
