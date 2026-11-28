# Eval fixtures and scorecards

The investing chat and Business agent are retired. WhatsApp receipt intake runs
through document routing. Its offline tests live in `tests/ingestion/`.

The Business prompt-freeze test still imports `business_invariants.py`. It
checks the archived scorecard against the surviving Business tool declarations.
That check uses `business_eval.py` to identify the frozen corpus and approved
models, and `business_variety.py` to load the varied case IDs. The seven frozen
cases, eight calibration examples and 24 varied cases are inputs to that check.

The measured fixture digests and scorecard path are recorded in
`.agent/interpreter_prompt_fingerprint.json` under `scoped_measurements.business`.

## Test Tiers

- **Mocked harness - every change (free, no API calls):**
  Run the first command under [Mocked Run](#mocked-run). It validates Business
  fixtures, mutation detection, and historical scorecards.
- **Live eval - only the 3 sanctioned moments:**
  1. Pre-merge on a PR that changes runtime behavior.
  2. Main promotion candidate.
  3. After any model/provider change.
  Live runs require explicit spend authorization. This directory has no live chat runner.
- **Browser QA is also real-API:** every turn spends tokens. Use it at gates, not
  per hypothesis.

## Mocked Run

```bash
CUADRAO_OPENROUTER_API_KEY_DEV= poetry run pytest \
  tests/evals/test_business*.py -q --no-cov
```

To check the evidence through its consumers, run:

```bash
poetry run pytest tests/test_interpreter_prompt_freeze.py \
  tests/test_private_alpha_release_docs.py tests/test_promotion_evidence_configuration.py \
  tests/evals/test_measurement_eval_scorecard.py -q --no-cov
```

## Release evidence

`measurement_eval_scorecard.py` reads the fixture names, case IDs and bytes
from the Git commit recorded in a promotion scorecard. Release-configuration
tests also use its candidate-commit lookup. The fixture identity tests create
synthetic Git repositories, including one whose current tree has no fixtures.
Historical replays use the harness and fixtures from the commit they measured.
`EVAL_INTEGRITY.md` records the checks that ran in September 2026.
