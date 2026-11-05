# Docs Archive

Historical docs in this directory are preserved for branch archaeology and
review context. They are not active execution sources of truth.

For current product experience and document ownership, use:

- [MVEE](../specs/argus-minimum-viable-ecosystem-experience.md)
- [Documentation authority](../DOCUMENTATION_AUTHORITY.md)
- The explicitly assigned package; [Wave 1](../specs/wave-1/README.md) retains its existing gates for assigned work

Retired strategy narratives:

- [Pivot strategy](2026-09-26-argus-pivot-strategy.md)
- [Answers that stay true](2026-09-26-argus-answers-that-stay-true-roadmap.md)
- [Private Alpha Next decision memo](2026-09-26-private-alpha-next-decision-memo.md)

Their former paths now contain compatibility pointers, not competing product mandates.

For the release gate, canary evidence, and deploy discipline, use:

- `docs/specs/private-alpha-ci-cd-sota.md`
- `docs/PRIVATE_LAUNCH_RUNBOOK.md`
- `docs/release-manifests/TEMPLATE.md`

Archived private-alpha spec/checkpoint files:

- `2026-07-19-adaptive-result-chart-range-design.md`
- `2026-07-19-adaptive-result-chart-range-implementation.md`
- `2026-07-22-capability-truth-executable-boundary-design.md`
- `agent-architecture.md`
- `private-alpha-backtest-execution-capacity.md`
- `private-alpha-controlled-readiness-panel.md`
- `private-alpha-conversation-trust.md`
- `private-alpha-interim-issue-roadmap-2026-07-21.md`
- `private-alpha-performance-readiness-audit.md`
- `private-alpha-readiness-orchestration.md`
- `private-alpha-status-action-parity-audit.md`
- `research-lab-thesis.md`

Added in the 2026-07-07 pass (after the Gate A/B loop, B4 language-gate
retirement, and execution realism shipped):

- `PRODUCTION_READINESS_AUDIT.md` — May 2026 readiness audit; self-declared
  historical, moved out of top-level `docs/`.
- `ARGUS_SYSTEM_STEERING.md` — May 2026 pre-launch steering reference; moved out
  of top-level `docs/`.
- `private-alpha-next-p2.1-capability-audit.md` — completed P2.1 audit (Slice D).
- `private-alpha-next-p2.1a-capability-registry-impl.md` — completed P2.1.a
  capability registry consolidation spec (shipped in #129).

Added in the 2026-07-23 interim-slate reconciliation:

- `2026-07-19-adaptive-result-chart-range-design.md` — completed issue #250 /
  PR #264 design.
- `2026-07-19-adaptive-result-chart-range-implementation.md` — completed issue
  #250 / PR #264 implementation plan.
- `2026-07-22-capability-truth-executable-boundary-design.md` — completed issue
  #241 / PR #266 design and acceptance contract.
- `private-alpha-interim-issue-roadmap-2026-07-21.md` — retired issue/wave
  dependency plan; founder outcomes now own sequencing.

Added in the 2026-10-04 Cuadrao docs cleanup (Argus-era specs both halves of
the Cuadrao master plan list for archiving):

- `private-alpha-next-conversational-edit-contract.md` — Argus web chat
  conversational edit contract, built and landed in `0fb32c1`; web chat frozen.
- `graded-interpretation-routing.md` — Argus chat interpreter routing lane.
- `evidence-aware-idea-loop.md` — Argus research-lab source thesis behind the
  archived decision memo.

Compatibility pointers remain at the former spec/plan paths where existing
issues, PRs, or historical plans link to them.

## Active regression contracts retained outside this archive

The completed Always Progresses design and implementation plan remain under
`docs/superpowers/` because guest mode and later conversational slices still use
their typed lifecycle, recovery, retry, and reload requirements as a standing
quality bar. Their status headers mark the implementation complete and forbid
wholesale redispatch. Move them here only after no active or planned product
surface consumes that regression contract.
