import type { BusinessDraftRevision } from "@/lib/business-dossier";

export function hasNoteChange(revision: BusinessDraftRevision): revision is BusinessDraftRevision & { after_current_note: string } {
  return revision.after_current_note != null && (revision.before_current_note ?? "") !== revision.after_current_note;
}

export function latestNoteChange(history: BusinessDraftRevision[]) {
  return history.filter(hasNoteChange).reduce<BusinessDraftRevision | undefined>(
    (latest, revision) => !latest || latest.version < revision.version ? revision : latest,
    undefined,
  );
}
