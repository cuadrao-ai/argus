import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { BusinessDossier, BusinessFactPatch } from "@/lib/business-dossier";
import type { DgiiDeclaration, DgiiFields, DgiiReview, PurchaseChoice } from "@/lib/business-dgii";
import { referenceCode } from "@/lib/failure-screen";
import { randomId } from "@/lib/random-id";
import type { BusinessDataSource } from "./business-data";
import type { ReviewRow } from "./receipt-fact-rows";

/** A row on the open draft that saves on its own: a fact, or one of the owner's two 606 choices. */
export type SaveRow = ReviewRow | keyof PurchaseChoice;

/** One edit, by the write that owns its fact. */
export type ReviewChange =
  | { write: "facts"; facts: BusinessFactPatch }
  | { write: "fiscal"; fiscal: Partial<DgiiReview["fiscal"]> }
  | { write: "purchase"; purchase: PurchaseChoice };

/** Where a row's last save stands. `unknown` is a save whose outcome never came back, so its edit cannot be dropped. */
export type RowSave =
  | { state: "saving" }
  | { state: "saved" }
  | { state: "failed"; message: string; reference: string; retry: boolean; unknown: boolean };

type Attempt = { change: ReviewChange; base?: BusinessDossier; key?: string };
type Failure = Omit<Extract<RowSave, { state: "failed" }>, "state">;

function currentFiscal(dossier: BusinessDossier): DgiiReview["fiscal"] {
  const fiscal = dossier.facts.fiscal;
  return { rnc: fiscal?.rnc.value ?? null, ncf: fiscal?.ecf.value ?? fiscal?.ncf.value ?? null, itbis: fiscal?.itbis.value ?? null };
}

/** The declaration a fiscal write carries unchanged. The server has no fiscal write without one. */
function keptDeclaration(dossier: BusinessDossier, fields: DgiiFields | null): DgiiDeclaration | null {
  if (dossier.dgii) return dossier.dgii;
  if (!fields) return null;
  const form = dossier.facts.kind.value === "income" ? "607" : "606";
  const blank: DgiiDeclaration = { form };
  for (const field of fields[form]) if (!(field.name in currentFiscal(dossier))) blank[field.name] = null;
  if (form === "606") { blank.actual_refund = false; blank.purchase_activity_id = null; }
  return blank;
}

/** Whether the edit says anything the record does not already say. */
export function changesRecord(dossier: BusinessDossier, change: ReviewChange): boolean {
  if (change.write === "facts") return Object.entries(change.facts).some(([name, next]) => {
    const fact = dossier.facts[name as keyof BusinessFactPatch];
    return fact.state !== next.state || JSON.stringify(fact.value) !== JSON.stringify(next.value);
  });
  if (change.write === "fiscal") {
    const current = currentFiscal(dossier);
    return Object.entries(change.fiscal).some(([name, next]) => (current[name as keyof typeof current] ?? "") !== (next ?? ""));
  }
  return true;
}

function send(source: BusinessDataSource, dossier: BusinessDossier, change: ReviewChange, fields: DgiiFields | null, key: string): Promise<BusinessDossier> {
  const { draft_id: id, version } = dossier;
  if (change.write === "facts") return source.reviewDraft(id, version, change.facts, key);
  if (change.write === "purchase") return source.reviewPurchase(id, version, change.purchase, key);
  const declaration = keptDeclaration(dossier, fields);
  if (!declaration) throw Object.assign(new Error("tax fields unavailable"), { code: "fields_unavailable" });
  return source.reviewFiscal(id, version, { fiscal: { ...currentFiscal(dossier), ...change.fiscal }, declaration }, key);
}

/**
 * Saves each edit on its own, one at a time, each on the revision the last one
 * left. A failed row keeps what it needs to try again. A save whose outcome
 * never came back retries with its same key and revision, so the server
 * answers it once. A version conflict loads the current revision and keeps the
 * person's edit. Lost access hands the page to `onLost`.
 */
export function useReviewAutosave({ source, draftId, dossier, fields, label, onSaved, onLost }: {
  source: BusinessDataSource;
  draftId: string;
  dossier: BusinessDossier | null;
  fields: DgiiFields | null;
  /** The row's name in a failure message. */
  label: (row: SaveRow) => string;
  onSaved: (next: BusinessDossier) => void;
  onLost: (reference: string) => void;
}) {
  const { t } = useTranslation();
  const [saves, setSaves] = useState<Partial<Record<SaveRow, RowSave>>>({});
  const attempts = useRef<Partial<Record<SaveRow, Attempt>>>({});
  const queue = useRef<Promise<unknown>>(Promise.resolve());
  const latest = useRef(dossier);
  useEffect(() => { latest.current = dossier; }, [dossier]);

  const mark = useCallback((row: SaveRow, save: RowSave | null) => setSaves((current) => {
    // One row says "saved" at a time: the last one.
    const others = Object.entries(current).filter(([name, other]) => name !== row && (save?.state !== "saved" || other.state !== "saved"));
    return Object.fromEntries(save ? [...others, [row, save]] : others);
  }), []);

  const refused = (row: SaveRow, code?: string) => t(`business.dgii.error.${code}`, "") || t(`business.dossier.blocker.${code}`, "") || t("business.dossier.placeholder.save_refused", { field: label(row), defaultValue: "{{field}} wasn't saved. Check the value." });

  const failure = async (row: SaveRow, attempt: Attempt, base: BusinessDossier, key: string, error: unknown): Promise<Failure | null> => {
    const { code, status } = error as { code?: string; status?: number };
    const reference = referenceCode(error);
    if (code === "fields_unavailable") return { message: t("business.dgii.load_failed", "We couldn't load the tax fields."), reference, retry: false, unknown: false };
    if (code === "stale_version") {
      const fresh = await source.dossier(draftId).catch(() => null);
      if (fresh) { latest.current = fresh; onSaved(fresh); }
      attempts.current[row] = { change: attempt.change };
      return { message: t("business.dossier.placeholder.save_stale", "This record changed while you edited. You're seeing the current version; your change is still here."), reference, retry: true, unknown: false };
    }
    if (status === 401 || status === 403 || status === 404 || code === "permission_denied") { onLost(reference); return null; }
    if (status && status >= 400 && status < 500) return { message: refused(row, code), reference, retry: false, unknown: false };
    attempts.current[row] = { change: attempt.change, base, key };
    return { message: t("business.dossier.placeholder.save_lost", { field: label(row), defaultValue: "We couldn't confirm that {{field}} was saved. Approval is paused." }), reference, retry: true, unknown: true };
  };

  const run = (row: SaveRow, attempt: Attempt): Promise<boolean> => {
    mark(row, { state: "saving" });
    const task = queue.current.then(async () => {
      const base = attempt.base ?? latest.current;
      if (!base) return false;
      const key = attempt.key ?? randomId();
      try {
        const next = await send(source, base, attempt.change, fields, key);
        latest.current = next;
        delete attempts.current[row];
        onSaved(next);
        mark(row, { state: "saved" });
        return true;
      } catch (error) {
        const failed = await failure(row, attempt, base, key, error);
        mark(row, failed && { state: "failed", ...failed });
        return false;
      }
    });
    queue.current = task;
    return task;
  };

  const save = (row: SaveRow, change: ReviewChange) => run(row, { change });
  const retry = (row: SaveRow) => { const attempt = attempts.current[row]; return attempt ? run(row, attempt) : Promise.resolve(false); };
  const clear = (row: SaveRow) => { delete attempts.current[row]; mark(row, null); };
  const states = Object.values(saves);
  return {
    saves,
    save,
    retry,
    clear,
    busy: states.some((item) => item.state === "saving"),
    /** A row whose edit did not land: nothing is approved while the screen shows a value the record does not hold. */
    failed: states.some((item) => item.state === "failed"),
  };
}
