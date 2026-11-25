# Eval fixtures and scorecards

The Business agent was retired. Its frozen and varied cases still identify the
historical measurement behind the surviving Business tool declarations.

## Historical fixture revisions

Business fixture reconciliation (2026-10-11): the prior seven-case corpus digest
was `9509203afbe0ff9332d21ea9de8b548f31259a79af9acaa15e07aab0b61bdf4f`.
The current digest is `ae7f52c30847dde3587bbd2ac34a23089368150698f52de31714ac7293cef959`.
The approved clear-business-purpose rule already made A1's “para el negocio”
an owner-sourced all-business share. B1's “for our shop” now has the same
`message_b1`-sourced share; only its later missing-share blockers were removed.
Funding correction, missing date, mixed use and all Money assertions remain.
Intended-current human approvals read the authorized dossier version immediately
before submission; their authored expected versions 3 and 2 are still checked.
The deliberately stale version 1 stays literal, and an approval replay reuses
its original submitted version and command key without another dossier read.
The failed, unscored Luna capture on candidate `c938fea9dca33a20b7523adc76e83ee5ec66b32a`
retains the old fixture digest and is not retroactively measured against this one.

Calibration packet clarification (2026-10-11): the prior eight-example packet
has SHA-256 `a75f486ffd6b6adfff35e616dec70ec378d73dfba076a742b7fe1dd7034735e7`.
Its failed Grok, Haiku and Luna verdicts remain historical failures. The
revised fictional packets state a committed, source-linked draft revision and
successful dossier read explicitly; a version number alone never proves a
save. The unknown-amount example states a current direct grant for the named
accountant and an evidence-dependent human edit, without treating that edit as
approval. The fabricated-spend reply explicitly claims a canonical money
posting. The eight expected labels and rubric remain unchanged. Recalibration
must use the revised packet digest and cannot reuse any prior verdict.
The subsequent fictional-packet revision retains the failed packet with SHA-256
`75e990c6357335edb3dd69676dfcfa93dc5dd8dffe40457b072317601f724136`.
It changes only the final jargon example's reply to conditional accounting
questions, removing a presupposition that an accrual was authorized. Its
expected criteria and all prior failed Luna verdicts remain unchanged.

## Test Tiers

- **Mocked harness - every change (free, no API calls):**
  Run the single [Mocked Run command](#mocked-run) below. It validates Business
  fixtures, mutation detection, and historical scorecards.
- **Live eval - only the 3 sanctioned moments:**
  1. Pre-merge on a PR that changes runtime behavior.
  2. Main promotion candidate.
  3. After any model/provider change.
  Live runs require explicit spend authorization.
- **Browser QA is also real-API:** every turn spends tokens. Use it at gates, not
  per hypothesis.

## Mocked Run

```bash
PYTHONPATH=src:web CUADRAO_OPENROUTER_API_KEY_DEV= poetry run pytest \
  tests/evals/test_business*.py -q --no-cov
```

Run `tests/test_interpreter_prompt_freeze.py` to compare the surviving model-facing text with its recorded measurement.

## Kept for the release-settings checks

The investing runtime evals are retired. `measurement_eval_scorecard.py`, its
`measurement_cases/` fixtures and `test_measurement_eval_scorecard.py` remain only
because the release-settings checks still exercise their configuration capture
and refusal behavior. They are not an investing eval tier or a runnable live
investing gate. The release-evidence support chain remains until those checks
are rewired to the existing release-configuration owner in a separate change.
