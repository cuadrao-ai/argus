# Argus Claude Review Contract

@AGENTS.md

Read `AGENTS.md` first. Use [documentation authority](docs/DOCUMENTATION_AUTHORITY.md)
to identify the approved experience and assigned scope. Review the ecosystem
against the MVEE and implementation changes against their technical contracts;
preserve runtime safeguards.

For any code review, also use:

- `docs/PRODUCT.md`
- `docs/ARCHITECTURE.md`
- `docs/API_CONTRACT.md`
- `docs/DATA_MODEL.md`
- `.agent/designs/argus/DESIGN.md`
- the explicitly assigned package/spec and applicable release document

Review against the named parent branch. Do not assume `main` is the correct
comparison base for stacked or lane work.

Focus review on:

- user-visible regressions;
- Argus language-agnostic runtime spine;
- no regex, hardcoded language gates, or shortcut routing before LLM
  interpretation;
- changes to model-facing text, the interpreter's prompt and the response
  schema's field descriptions, which move behavior on every turn and require a
  committed scorecard showing no regression (AGENTS.md Never-Violate 12);
- deterministic layers that compensate for an unreliable model read without
  recording when they fire;
- backend canonical truth and Supabase persistence ownership;
- frontend rendering backend-provided state instead of inventing state;
- API contract and OpenAPI/doc consistency;
- modularity, large-file drift, and mixed concerns;
- focused tests, browser QA, and release-gate evidence gaps;
- Render/workflow/canary promotion discipline.

Do not suggest broad rewrites, future-slice work, or new product surfaces unless
they block the active lane. Prefer concrete findings with file and line
references, severity, impact, and the smallest safe fix.

For development reviews, use local on-demand Claude Code review commands on a
bounded diff. For promotion candidates, use a manual or label/comment-triggered
GitHub review gate. Do not run Claude review automatically on every push.
