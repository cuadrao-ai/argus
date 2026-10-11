# Resume the Cuadrao Business owner-pilot records

This replaces the original dispatch prompt. Its exact text remains in the
[published October 8 revision](https://github.com/lagarcess/argus/blob/d86a791d0cf0de22ab43b0a7ea1cea2a756f6c48/docs/specs/lanes/cuadrao-business-owner-pilot-handoff.md).
The implementation lane has already run. Do not dispatch it again from an old
planning checklist.

Read the [current scope and decision provenance](cuadrao-business-owner-pilot.md#current-authority-and-landing-boundary),
the [Business handoff](../../handoffs/cuadrao-business-lane.md), and the
[core-flow tracker](https://github.com/lagarcess/argus/issues/942). The handoff is a
dated checkpoint. Later founder continuations in the scope document supersede
its local-work pause, but do not prove that every requested outcome was delivered.

## Current hosted Business assignment

The [October 10 hosted decision](../argus-decision-log.md#october-10-2026-hosted-business-beta-and-build-grant)
and [execution manifest assignment](../argus-execution-board.md#business-hosted-invite-only-build-october-10-2026)
own the later bounded integration and staging work. Read them and the current
Business handoff before acting. #953 has landed; its documentation assignment
below is complete. It does not dispatch new runtime or web work.

## Historical documentation assignment

1. Fetch `origin/codex/private-alpha-next` and record its SHA.
2. Reconcile #900 and #910 with current integration and the recorded continuations.
3. Preserve the existing technical contracts and the original design rationale.
4. Verify that each final PR changes only its two planning documents.
5. Run documentation checks, modularity checks, review, and exact-head CI.
6. Report the final head and remaining evidence gaps to the coordinator.
7. Wait for the serialized merge slot. Do not enable auto-merge.

The owner API, S1–S3 isolation, and non-model-facing S4 separation already landed.
The [implementation checkpoint](../../handoffs/cuadrao-business-lane.md#implemented-and-merged-into-integration-all-default-off)
records their PRs. Do not recreate those changes.

## Preserve separate work

- Keep #925 intact. Its model-facing restrictions, refusal presentation,
  evaluation-budget work, and Business scorecard are outside this landing.
- Keep `codex/cuadrao-business-sandbox` at its preserved checkpoint
  `df208f7ec2379cd84efd55eea0deb685d67c5360`. Do not include its later capture,
  email, WhatsApp, search, or custodian changes in the planning PRs.
- Preserve local audit notes and private configuration. Never add credentials,
  received customer documents, or private message contents to the PR.
- Leave Consumer, Marketing, staging deployment, and shared running services
  under their existing owners.

## Delivery and authority limits

**October 10, 2026 update.** The founder approved the Business agent direction later the same day. The [Business agent execution spec](cuadrao-business-agent-execution-spec.md) now owns the Business build order, the proposed agent contract and the decisions. Where this document says "Business chat stays off" or that the agent audit approves no model-facing implementation, that spec takes priority. Business chat is part of the future agent implementation. This PR changes documents only. It turns on in hosted environments for pilot businesses, through server flags, after J1 passes and the founder approves. Each model-facing change still needs a committed scorecard.

This completed documentation assignment changed no code, schema, flag, UI copy,
provider setup, or model instruction. It includes no paid calls, hosted actions,
phone work, main promotion, or broad UI pass.

The earlier owner-only and email-deferred scope is not the full current product
promise. Later capture and agent requirements remain tracked separately. Do not
claim complete capture, extraction, accounting readiness, real WhatsApp delivery,
or hosted acceptance from the publication of these documents.

After an authorized merge, run the repository integration-landing workflow within
the granted scope. Report implemented, locally verified, provider-verified, and
hosted-enabled status separately. A green documentation PR proves none of those
runtime outcomes by itself.
