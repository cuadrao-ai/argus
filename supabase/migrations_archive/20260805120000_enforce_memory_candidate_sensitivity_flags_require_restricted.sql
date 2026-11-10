-- Defense-in-depth: the Python `SensitivityAssessment` contract rejects any
-- sensitivity flags unless the status is 'restricted', but the base
-- memory_candidates migration only validated flag *names*, not this
-- cross-column relationship. A direct privileged-backend insert/upsert could
-- otherwise persist sensitivity_status = 'clear' alongside a nonempty
-- sensitivity_flags, which the Python read path is not built to tolerate.

alter table public.memory_candidates
  add constraint sensitivity_flags_require_restricted
  check (
    sensitivity_flags = '{}'::text[]
    or sensitivity_status = 'restricted'
  );
