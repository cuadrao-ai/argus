# Pending-write identity isolation review delta

This closes the native acceptance gap in
[PR #747 review finding](https://github.com/lagarcess/argus/pull/747#discussion_r4134599936).
The original reconciliation case asserted absence before proving user B’s data
had loaded, and no user A command was pending. Its native identity-isolation
claims are **superseded** by this dedicated connected case. Its previously
observed reconciliation, currency and Spanish results retain their original
provenance. The 2:55 recording is unchanged.

## Observed result

`testPendingMoneyWriteRemainsIsolatedAcrossIdentities` passed **1/1 in 232.846s**.
The full Xcode command returned **0** and finalized its result bundle.

1. Signed in as synthetic B, created `Isolated B 6D519` with DOP 321 and captured
   B’s own Home total.
2. Signed in as A, created `Pending A 6D519` with DOP 100 and recorded income 25.
   The loopback proxy dropped exactly one response **after server commit**.
   Reopening showed [A’s pending command](isolation-a-pending-before-switch.png).
3. Signed in as B. The test waited for B’s exact persisted account row before
   checking that A’s account and pending action were absent. It then opened
   [B’s account and checked DOP 321](isolation-b-own-account-loaded.png), and
   verified [B’s Home was unchanged with no A pending action](isolation-b-home-without-a-pending.png).
   An empty or loading account list cannot satisfy this barrier.
4. Signed back in as A. The [same pending command returned](isolation-a-pending-restored.png).
   Recovery produced balance 125 and one income record. After another relaunch,
   [the same record ID remained and the count was still one](isolation-a-recovered-once-after-reopen.png).
5. Independent [canonical readback](readback.json) confirms A’s balance 125/one
   income, B’s balance 321/no activity, and the opposite account’s absence from
   each owner’s account list.

No product defect was observed. The change fixes acceptance arrangement and
assertions; application/API/database behavior is unchanged.

## Provenance and reproduction

- Original published base and running API: `5a982bc2b9df93c5015f20cc79b470d095d5b40f`.
- Native build and test source: `3106f2f6e1d91570f98239beb7ff2cafe31e7fd5`.
- Xcode 27.0 (27A266a), iOS 27, iPhone 17e simulator
  `DD9EF306-EFED-41F1-9A8E-B42EBCEE07DA`.
- Real retained local API/Supabase/Postgres, synthetic users only. Proxy 58512
  forwarded API 58500 throughout uncertainty and identity changes.
- [Sanitized terminal evidence](terminal-cases.txt); raw auth logs and result
  bundles remain ignored. Both focused commands finalized and exited normally.

For a deliberate rerun, start the checked-in local proxy:

```sh
/Users/garces/.codex/worktrees/5a42/private-alpha-next/.venv/bin/python \
  scripts/qa/financial_response_fault.py --listen-port 58512 --upstream-port 58500
```

Set only the ignored local app API setting to loopback port 58512, then run:

```sh
python3 ios/scripts/auth/run-ui.py DD9EF306-EFED-41F1-9A8E-B42EBCEE07DA \
  --accounts --port-base 58500 --response-loss-proxy \
  --only ArgusFoundationUITests/FinancialLoopUITests/testPendingMoneyWriteRemainsIsolatedAcrossIdentities
```

Restore the app API setting to 58500, run the parent README’s read-only Home
smoke command, and stop only the owned temporary proxy. Do not reset or reseed.

## Final state and limits

The direct-API Home/reopening smoke passed **1/1 in 15.469s**, full exit 0. The
installed app is back on 58500, signed in as A on Home. The temporary proxy is
stopped; the API, CAPTCHA bridge, database, retained records and previous 584xx
demo remain untouched. This is local simulator acceptance, with physical iPhone,
real founder identity/data, signing and deployment still pending.
