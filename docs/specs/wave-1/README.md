# Argus wave 1 specs

> **September 26, 2026 reconciliation:** Read
> [documentation authority](../../DOCUMENTATION_AUTHORITY.md) and the approved
> [MVEE](../argus-minimum-viable-ecosystem-experience.md) before using this spec.
> These Wave 1 package bodies and existing stage/review gates remain preserved
> for assigned work. Conflicting experience requirements need explicit package
> reconciliation; they are not permanent limits on the pivot. This notice does
> not cancel work, unlock stages, change technical contracts, or authorize
> exposing unfinished features. The original product/source text below remains
> a dated specification, not the final definition of the whole ecosystem.

Integration branch: `codex/private-alpha-next`. Every file was checked
against integration tip `5fb0f079b92ed5391da770cb9a7b89c1c4807684`.

## Files

| File | What it is |
| --- | --- |
| `00-shared-rules.md` | Rules for every stage. Part 1 is Iris's product rules R1 to R7 (verbatim). Part 2 is the engineering rules E1 to E7: worktrees, the stage unlock rule, PR rules, contractor access, the review gate, and copy rules. Part 3 is the reuse map RM-1 to RM-19: what already exists in the code and must be reused. |
| `01-stage-0-safety-and-analytics.md` | SPEC 0, stage 0. Iris's product half (verbatim, with her round 2 and round 3 answers), then the engineering half: the safety fixes (#681, #692, #693), the 10 analytics events, the invite cohort code (the one planned migration), work packages 0A to 0C, merge order, acceptance checks A1 to A9, and clashes resolved. |
| `02-stage-1-layout-ai-landing-card-payoff.md` | SPEC 1, stage 1. Iris's product half (verbatim, with her round 2 and round 3 answers), then the engineering half: navigation, the AI landing and its six chips, the card payoff calculator with its exact math and reference values, "Before taxes" on every result, work packages 1A to 1F, merge order, acceptance checks B1 to B9, and clashes resolved. |
| `iris-product-halves.md` | Iris's source document. Not edited. The spec files quote it word for word. |

## Reading order

1. `AGENTS.md` at the repo root. It wins over these files on anything it
   covers (E1).
2. `00-shared-rules.md`, all of it.
3. The spec for the stage you are working on: `01-...` for stage 0,
   `02-...` for stage 1. Read the product half first, then the engineering
   half. Where Iris's later answers (round 2, round 3) change something in
   her earlier text, the later answer wins; the engineering half already
   follows the latest answer.
4. Your work package: its Outcome, Files, Tests, Depends on, Gate, and any
   Done when lines. Each spec's work packages section states the Done when
   rule that applies to every package.

## Stage unlock rule

A stage starts only after every work package of the previous stage is
merged into `codex/private-alpha-next` and has passed its review gate.
Opened, approved, or green but unmerged does not count. Yelena confirms the
unlock in writing before any work on the next stage starts (E3).

Inside a stage, packages may be built in parallel in separate worktrees,
but they merge one at a time, in the merge order written in the spec.

## Review gates (E6)

Every PR:

1. CI green on the PR head.
2. Codex review completed on the head.
3. Every review thread answered in writing (`Fixed in <sha>`,
   `Won't fix: <reason>`, or `Deferred to #<issue>`), then resolved.

The PR also needs Priya's written eval verdict and a Codex re-review on the
final head if it touches any of these:

- money math (calculations, rounding, currency, presenters that print
  amounts);
- security (auth, identity, rate limits, usage claims, request logging);
- a database migration;
- anything that sends a message to a user, including limit or money copy;
- user data or consent (analytics, attribution, profile fields, saved
  cards, sharing);
- model-facing text (AGENTS.md Standard 12). This also needs a live
  measurement eval and a regenerated prompt fingerprint, run by the
  internal team.

Each package names its gate. Packages marked "internal" are done by the
Argus team, not contractors.

## Contractor boundaries (E5)

No production or Supabase secrets, no dashboards, no deploys, and no hosted
migration runs. Work runs on mock auth, the in-memory store, and local
Supabase. Tests that need a real provider (OpenRouter, Perplexity, PostHog,
Resend) are run by the internal team.
