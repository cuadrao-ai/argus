# Argus mobile design lock — September 28, 2026

**Status:** Founder-approved disposable mobile design baseline, `mobile-2026-09-28`.

The founder requested a full mobile sweep and lock, including the complete ecosystem HTML reports. This closes the agreed template design work. It does not authorize production implementation, provider work, deployment, or a release-readiness claim.

## Portable reference

This September 28 baseline succeeds the earlier September 27 reference in
[PR #714](https://github.com/lagarcess/argus/pull/714). Treat that older snapshot
as historical, not as the current account/space/recording specification. This
publication does not close or alter #714; the release captain must reconcile
their overlapping documentation before merging either publication.

- [Complete source, reports and evidence archive](evidence/mobile-design-lock-2026-09-28/argus-mobile-design-lock-2026-09-28.zip)
- [Archive SHA-256](evidence/mobile-design-lock-2026-09-28/argus-mobile-design-lock-2026-09-28.zip.sha256)
- [Per-file manifest](evidence/mobile-design-lock-2026-09-28/LOCK-MANIFEST.json)
- [Report screenshot](evidence/mobile-design-lock-2026-09-28/report-overview.png)

SHA-256: `c55e565aa142e38eec61b570510af1c4c2cb9629c24f3ce2d01387639f0ea0e6`.

Unzip, serve the `argus-type-preview` directory with a local static server, and open `mobile-design-lock.html`. Start with `MOBILE-DESIGN-LOCK.md` inside the archive. All six current HTML reports derive from one catalog and can be rebuilt with `python3 build-mobile-reports.py`. Historical reports are visibly marked and do not own current design.

## Scope and verification

Locked: Home, Accounts, Argus chat, Plan, Search, Updates, capture/review, financial spaces, Household, settings, sign-in presentation, theme, motion, correction and recovery. The final Settings root is App / Account / Support, without duplicated space controls. Temporary chat uses one context choice and stable header positions. Composer tray/suggestions resize together. Refunds and adjustments follow account-based semantics; financial notes share a 200-character limit.

288 deterministic checks passed. 276 local report/index links and assets checked; 33 JavaScript syntax checks passed. Browser sweep covered primary and supporting surfaces, selected state transitions, Light/System persistence, the projection date regression, and 360px layout. All six reports were checked at mobile and desktop sizes. Earlier deep correction/recovery replays are retained as dated evidence, not misrepresented as wholly repeated in this sweep. The archive passed ZIP CRC and every per-file hash check.

Reference repository head: `57f36d5f45d36c2073e84a98b32cb33cfaad6172`, branch `codex/native-interface-decision`, with existing documentation edits. The actual template bytes are identified by the archive and manifest, not that repository SHA. No production runtime files changed; no live providers, real invitations or hosted mutations were used.

## Implementation boundary

The [MVEE](../specs/argus-minimum-viable-ecosystem-experience.md) owns experience. [DESIGN.md](../../.agent/designs/argus/DESIGN.md) owns presentation. Existing architecture/API/data owners remain in force. Native keyboard/safe-area/gesture/accessibility acceptance, English/es-419 localization, real loading/error/offline behavior, posting/reconciliation/precision, permissions, retention, concurrency, auth, extraction, delivery and persistence still require implementation and verification. Provider-dependent explorations are not automatically launch commitments.

This freeze is not another visual design phase. Reopen a specific decision only through an explicit request or a concrete implementation conflict, then preserve this checkpoint and create a dated successor.
