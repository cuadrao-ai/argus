# Jules Branch CI and Intake Audit

## 1. Branch Flow Execution
The documentation states that Jules acts downstream to Alpha-Next in an "intake" lane.
The expected branch flow is:
`codex/private-alpha-next` -> `codex/private-alpha-next-jules-intake` -> `jules/<focused-scope>`.
This hierarchy ensures isolated scopes without introducing risks directly to the primary integration branch or the deployment `main` branch.

## 2. CI Triggers
Based on `.github/workflows/ci.yml`:
- Pushes to branches starting with `jules/**` trigger CI.
- Pull Requests targeting `codex/private-alpha-next-jules-intake` trigger CI.

## 3. Jules PR Targeting Rules
- The retired intake instructions (since removed) required these PRs to target **only** `codex/private-alpha-next-jules-intake`.
- Targeting `main` or `codex/private-alpha-next` is prohibited. Rebase and pushes against `main` are entirely restricted.

## 4. Ownership Enforcement Policy
- **Analysis:** Looking at `.agent/ownership/branch_ownership.json`, branches under `jules/**` do not have an explicit mapping.
- **Enforcement Code:** `.agent/scripts/ownership/verify_branch_ownership.py` handles ownership checks. If a branch is not explicitly listed in `.agent/ownership/branch_ownership.json`, the script skips enforcement by exiting early with status 0: `Branch '{branch_name}' has no ownership policy. Skipping enforcement.`
- **Risk:** Jules branches (`jules/**`) currently bypass the directory restriction checks because they are unmapped in the branch ownership JSON. This is a risk as the intended read-only and limited write operations boundaries enforced via prompt directives do not have programmatic backup via Git PR gates for accidental over-scoping.
- **Recommendation:** Add a `jules/**` wildcard match (if supported by verification script logic) or a generic Jules role rule to `.agent/ownership/branch_ownership.json` limiting changes strictly to areas like `docs/`, `tests/`, and specified `web/` elements, and explicitly denying `main.py`, backend routing, engine execution logic, deployments, migrations, and model parameters. Update the Python ownership script to support wildcards for matching ephemeral `jules/*` branch names.
