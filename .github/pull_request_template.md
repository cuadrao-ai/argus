## Merge Danger

- Door: <one-way or two-way>
- Blast radius: <files, tables, routes, flags>
- Rollback: <steps>
- Eval tier: <No Eval, Light, or Full>

## Eval tiers (agreed with the evaluator, use verbatim)

- No Eval: docs-only PRs. They land on green CI.
- Light Eval: two-way-door changes with a narrow blast radius: no auth, money math, security, secrets, migrations, tables, grants or RLS, and no flag turned on in production. Examples are tooling, CI, tests, copy and contained UI. Eval confirms the exact head SHA and green CI, a clean trial merge onto the current tip, that the diff matches the Merge Danger block's blast radius and rollback, and the evidence-media gate. Eval runs the touched tests itself, including any touched e2e spec CI doesn't run. No full repro or adversarial pass.
- Full Eval (always): anything touching auth, money, security, secrets or migrations/schema/grants/RLS; any one-way door; any PR whose rollback isn't a plain revert; any flag turned on in production; and any PR over 400 changed non-test lines (lockfiles, generated files and fixtures excluded). Full adds a targeted repro of the riskiest path, and mutation checks on auth, money or security code.
- Staging flags: turning a flag on in staging only is Light, but Eval checks the flag is declared in every hosted-settings file and render.yaml and that production stays "false". Turning a flag off anywhere is Light.
- Mismatch rule: if the Merge Danger block understates the blast radius, it goes to Full. Eval can always raise a tier, never lower it.

## TL;DR

## Motivation

## Changes

## Out of scope

## Testing

Attach screenshots, recordings, and PDFs on the pull request, or upload them with actions/upload-artifact. Do not commit them under `docs/reports/` or an evidence folder.

## Risks/Rollback

## Docs affected

## Status
