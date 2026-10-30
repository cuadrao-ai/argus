# Home country per user

Board item "Home country per user" in
`docs/specs/argus-grounded-finance-roadmap.md`. Lane branch
`claude/home-country-per-user-527b31`, integration base `a993bfb2`, merged
with integration `afdd8a86` as `523b17d5`.

## What changed

- A registered user picks a country in Settings, in English or Spanish. The
  API derives the currency it implies (the first CLDR lists in tender there)
  and the user can override it. The profile stores nullable
  `profiles.country` and `profiles.currency_override`; the resolved
  `currency` is derived, never stored.
- Research sends the asking user's country as the web search's
  `user_location`, on the inline path and on the thorough job, whose typed
  request carries the country. A user with no country sends no location.
- `[removed obsolete setting]`, `home_location()`, `LOCAL_SOURCE_DOMAINS` and
  the `local_sources` parameter are removed, not kept as a fallback.

## Browser proof (`browser/`)

Re-captured at `eb28dfbc` (after Codex round 1 made the search boxes 16px) by
`drivers/settings_proof.mjs` against the real local
API (dev memory persistence, mock auth, provider keys blank) and the web dev
server, at 1280 px. `report.json` records what `GET /me` held after every
step, the status of the refused save and the alert the panel showed. Neither
language raised a page error.

| Screenshot | What it shows |
| :--- | :--- |
| `en-1-opened-with-suggestion.png`, `es-419-1-...` | The panel suggests the country the browser's language tag names (`en-US`, `es-MX`). Nothing is saved: the account's country is still null. |
| `en-2-mexico-implies-mxn.png`, `es-419-2-...` | Mexico picked. The currency shown, MXN, is the API's derivation. |
| `en-3-currency-overridden-usd.png`, `es-419-3-...` | The currency overridden with USD. |
| `en-4-after-reload.png`, `es-419-4-...` | After a reload the account and the panel still hold Mexico and USD. |
| `en-5-refused-save-put-back.png`, `es-419-5-...` | The picker sent the Dominican Republic and the request was rewritten to `EU`, so the refusal is the API's own 422. The panel shows "Could not update your country yet." / "No pudimos actualizar tu país todavía." and Mexico stays. |

The mocked-API spec `web/e2e/profile-home-country-save.spec.ts` covers the
same save, override, reload and refusal in both languages for CI-style runs.

## Review evidence (`review/`)

`drivers/row_heights.mjs` measures the Preferences rows with a mocked account.
At 390 px with touch, where the menu is a drawer, Appearance, Language and
Country and currency all render 44 px tall. At 1280 px, the rail popover for a
pointer, all three render 38 px. The drawer and sheet containers give every
submenu button a 44 px minimum, and the new row inherits it like its siblings.

## Live measurement

The first full run, on `9af12545`, finished its cases but `write_scorecard`
refused to write: its provenance check re-reads the head at write time, and a
commit landed in this worktree during the run.

By founder direction the re-measurement ran only the cases that reach
research, because the measured users have no country and the baseline never
sent one. Those are the 13 cases whose decision-10 baseline records a research
outcome: 4 grounded (3 balanced, 1 fast) and 9 discovery `find`.
`drivers/research_cases.py` ran them live on `03d9a089` with both provider
modes assigned `live_provider`, the head unchanged and the tracked tree clean
from start to end, and compared each against
`docs/reports/evidence/decision-10/live-measurement.json`. The record is
`live-research-cases.json`.

- Every research request sent no location (`locations_sent: [None]`), as in
  the baseline, because no measured user has a country.
- 9 unchanged, 2 fixed, 2 regressed. No case failed in both runs.
- Fixed: `asset_discovery_category_spanish_issue_244` and
  `asset_discovery_old_pharma_escalation_exact_issue_344` failed in the
  baseline and pass here. The discovery path builds no research spec and
  sends no location, so this PR does not explain the change.
- Regressed: `capability_honesty_future_performance_btc_regression`: the
  research provider returned an HTTP error (`research_unavailable_http_error`),
  so nothing was published and the judge failed scenario framing; the request
  carried no location, as in the baseline.
  `ordinary_conversation_price_question_en`: the answer published with its
  cited row, as in the baseline, and the prose judge failed without naming a
  criterion.
- Not rerun. This run's measured spend is $0.72 ($0.21 routed model calls,
  $0.51 research provider; the errored research call reported no cost). The
  lost full run is estimated at about $2.2 (about $1.50 routed model calls from
  two comparable full runs, plus about $0.70 research provider for the same
  cases), so the lane stands near $2.9, and one rerun of each regression would
  pass the founder's $3 cap.
