-- A decision attaches to a computation, not to a run.
--
-- Every decision_notes row so far hangs off a backtest: its evidence artifact,
-- idea, and idea version were required, so the decision index could only ever
-- hold backtest decisions. A decision on a computed answer has none of those.
-- It attaches to the assistant message that carried the answer and stores
-- the computation the answer declared (a registered kind plus its typed
-- inputs), so it can be re-run when the user opens it, even after the
-- message is gone.
--
-- Backtest decisions are unchanged: they keep their artifact spine and store
-- no computation, because the immutable run behind the artifact owns those
-- inputs and readers derive them. The check constraints below make the two
-- attachments mutually exclusive and keep the idea lineage welded to the
-- artifact, mirroring the DecisionNote model validator.
--
-- The three lineage columns lose NOT NULL and nothing else changes shape; no
-- row is rewritten. Owner scoping, RLS, grants, and the recall index are
-- untouched, and the guest lifecycle functions key on user_id only.

alter table public.decision_notes
  alter column idea_id drop not null;

alter table public.decision_notes
  alter column idea_version_id drop not null;

alter table public.decision_notes
  alter column evidence_artifact_id drop not null;

alter table public.decision_notes
  add column if not exists source_message_id uuid
    references public.messages(id) on delete set null,
  add column if not exists computation jsonb;

alter table public.decision_notes
  add constraint decision_notes_attachment_check
    check ((evidence_artifact_id is not null) <> (computation is not null));

alter table public.decision_notes
  add constraint decision_notes_evidence_lineage_check
    check (
      ((evidence_artifact_id is null) = (idea_id is null))
      and ((evidence_artifact_id is null) = (idea_version_id is null))
    );

alter table public.decision_notes
  add constraint decision_notes_user_message_unique
    unique (user_id, source_message_id);
