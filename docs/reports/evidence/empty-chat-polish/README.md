# Empty chat polish evidence

Lane: `claude/empty-chat-polish-6330b8`, off `codex/private-alpha-next`. Spec:
`docs/specs/argus-active-roadmap.md`, section "Empty chat polish". Closes #403.

Captured 2026-08-09 against a real backend, not a fixture. Twelve frames, both
languages, mobile 390 and desktop 1280. Every frame carries its rendered text
alongside the image, because the text is what proves the sentence and the image
is what proves the layout absorbed it.

## Setup

Backend on port 8010 from this worktree with `CUADRAO_MOCK_AUTH=true`,
`CUADRAO_PERSISTENCE_MODE=memory`, and **`ARGUS_MARKET_DATA_PROVIDER_MODE=live_provider`**
with the real Alpaca credentials. The provider mode matters: the hermetic
`synthetic_unit_fixture` mode reports no session at all by design, so a fixture
run could not have produced the closure frames.

Frontend on port 3010 with `NEXT_PUBLIC_RESEARCH_RAIL_ENABLED=true`, since the
signed-in greeting surface is behind that flag. No `.env` or `web/.env.local`
file was written.

Playwright drove the capture. Language is set through `PATCH /me`, the way the
settings picker sets it, because language is a profile preference and the
browser store is only a pre-auth hint. The local clock is shifted by a wall-clock
shim on `Date` so the time-of-day slot can be reached without waiting for it;
timers stay real, so the typewriter still runs and each frame is captured only
after the caret clears.

## Live market session

2026-08-09 was a Sunday. The endpoint answered from the real Alpaca trading
calendar:

```json
{
  "session": {
    "phase": "closed_weekend",
    "is_market_day": false,
    "as_of": "2026-08-09T17:43:05.824047-04:00"
  }
}
```

The `-04:00` offset is Eastern daylight time, resolved server side. The frontend
never computes it.

## Frames (`browser/`)

Console errors: **zero on all twelve**. `report.json` and `settings-report.json`
carry the machine-readable assertions behind the table.

| Frame | Language | Viewport | Local time | Name | Greeting |
| --- | --- | --- | --- | --- | --- |
| `01-empty-chat-en-desktop` | en | 1280x900 | 12:00 | none | What is worth a look today? |
| `02-empty-chat-en-mobile` | en | 390x844 | 12:00 | none | What is worth a look today? |
| `03-empty-chat-es-desktop` | es-419 | 1280x900 | 12:00 | none | ¿Qué vale la pena revisar hoy? |
| `04-empty-chat-es-mobile` | es-419 | 390x844 | 12:00 | none | ¿Qué vale la pena revisar hoy? |
| `05-closed-market-en-desktop` | en | 1280x900 | 19:00 | none | Stocks are closed for the weekend. Crypto never stops, so there is still plenty to test. |
| `06-closed-market-es-mobile` | es-419 | 390x844 | 19:00 | none | La bolsa está cerrada por el fin de semana. Las criptos no paran, así que hay mucho por probar. |
| `07-named-en-desktop` | en | 1280x900 | 23:30 | Lucas | Still up, Lucas. What are you curious about? |
| `08-named-es-mobile` | es-419 | 390x844 | 23:30 | Lucas | Todavía por aquí, Lucas. ¿Qué te da curiosidad? |
| `09-settings-field-en-desktop` | en | 1280x900 | live | unset then Lucas | settings field |
| `10-settings-field-en-mobile` | en | 390x844 | live | unset then Lucas | settings field |
| `11-settings-field-es-desktop` | es-419 | 1280x900 | live | unset then Lucas | settings field |
| `12-settings-field-es-mobile` | es-419 | 390x844 | live | unset then Lucas | settings field |

The four settings frames come in pairs: the base frame shows the field unset,
and `-saved` shows it after typing a name and pressing Enter, with the value
read back from `GET /me` to prove it persisted rather than only rendered.

## Review round 1: the saved name reaches the greeting without a reload

Frames 01 through 12 were captured at `2d97df3a`. Two review findings landed on
that commit, and `1c45ab65` fixed them. Frames 07, 08, 13 and 14 are re-captured
at the fixed head; the rest are unaffected by those fixes and stand.

A third finding then landed on `2bb53f5d` and `190eeac5` fixed it: the browser
counted a name in UTF-16 code units while the API and the database count code
points, so a name of 21 emoji measured 42 and was refused despite both of them
accepting it. A fourth landed on `5b23d63c` and `21535fa9` fixed it: a save
already on the wire could complete after the dialog closed and write state
belonging to an edit that no longer existed.

**Frames 07, 08, 13 and 14 were re-run at `21535fa9`**, the final code commit,
rather than assumed unaffected by either fix. Rendered text is byte-identical to
the captures above and the document still never reloads across the save. Only
`13-…-saved-dialog.png` differs, by a caret blink.

Two cases have no frame, because a request the browser used to refuse has
nothing to screenshot. Both are proven over the wire at `21535fa9` instead:
`PATCH /api/v1/me` returns `200` for 21 emoji, storing 21 code points, and `200`
for one leading space in front of a forty-character name, storing the trimmed
forty. Both were refusals before.

A fifth and sixth finding landed on `c0964d78` and `746185f2` fixed them:
profile responses now apply in the order they were issued, and the closure copy
stopped claiming that currencies keep trading or that the market reopens on a
Monday. **Frames 05, 06, 07, 08, 13 and 14 were re-run at `746185f2`** and the
rendered text is unchanged.

A seventh, eighth and ninth finding landed on `73a0d2d9` and `48fb2bc4` fixed
them: profile reads and writes are serialized rather than reconciled, and the
pre-market and after-hours lines stopped calling the market shut during windows
it is trading in. **Frames 05 to 08, 13 and 14 were re-run at `48fb2bc4`** and
the rendered text is unchanged.

**What the frames do not prove, and what does.** Today's rotation selects
`session_closed_weekend_a`, which was already true and never changed. Every
session string the copy fixes actually rewrote, `session_closed_weekend_b`,
`session_closed_holiday_a`, `session_pre_market_a` and `session_after_hours_a`,
fires in a phase a capture on this date cannot reach. Tests cover them instead,
and they guard the class rather than the lines that were wrong:

- No `session_*` string in either locale may match currency, divisa, forex, fx,
  Monday, or lunes. The endpoint resolves the US equity calendar and nothing
  else.
- Neither `session_pre_market_a` nor `session_after_hours_a` may match closed,
  shut, cerrad, or no opera. Both phases are trading windows.

`13` and `14` are the propagation proof, and they are three frames each: the
greeting before the save, the dialog with the name saved, and the greeting
after, all in one page session.

| Frame | Language | Greeting before the save | Greeting after the save | Document reloaded |
| --- | --- | --- | --- | --- |
| `13-named-no-reload-en-desktop` | en | Stocks are closed for the weekend. Crypto never stops, so there is still plenty to test. | Still up, Lucas. What are you curious about? | **no** |
| `14-named-no-reload-es-mobile` | es-419 | La bolsa está cerrada por el fin de semana. Las criptos no paran, así que hay mucho por probar. | Todavía por aquí, Lucas. ¿Qué te da curiosidad? | **no** |

The profile starts with no name, so the greeting has to change for the run to
prove anything. The name is then typed into the real settings field and saved
through the real dialog, which is closed with Escape. Nothing reloads.

"Document reloaded: no" is measured rather than asserted. A Playwright
`addInitScript` runs once per document, so it increments a counter on `window`;
the counter reads 1 before the save and 1 after, recorded per frame in
`propagation-report.json` as `documentLoadsAtRead` and `documentLoadsAtEnd`.
Counting navigation events instead would have been misleading: the shell does
several soft `history.replaceState` routes that are not reloads.

The backend half of the second finding is proven over the wire rather than in a
frame, since a rejected request has no screenshot. At the fixed head,
`PATCH /api/v1/me` with one leading space in front of a forty-character name
returns `200` and stores the trimmed forty characters. It returned `422` before.

### What each set proves

**No toggle anywhere.** Every one of the twelve rendered-text files was checked
for "Show suggestions", "Hide suggestions", "Mostrar sugerencias", and "Ocultar
sugerencias". None appears. The suggestion chips render in all twelve without a
control gating them, which is the point: they stop when the empty chat stops.
Compare `docs/reports/evidence/377/browser/01-empty-chat-en.txt`, which still
carries "Hide suggestions" on line 17.

**The greeting is not one sentence per slot.** Frames 01 and 05 are the same
day, the same language, and the same viewport, and differ only in the local
hour. They produce different lines, because the day-stable pick is per pool and
the pool widens when a session is active.

**Closure is true for every asset class.** Both closure frames name stocks and
crypto in the same sentence. A bare "markets are closed" would be false for the
crypto and currency-pair users Argus supports.

**The long sentence survives 390.** `06-closed-market-es-mobile.png` is the
worst case: the longest string in the pool, in the longer language, at the
narrowest width. It wraps to four balanced lines with no overflow, the chips
still scroll above the composer, and the disclaimer still sits at the bottom.

**The name appears only where it was written in.** Frames 07 and 08 carry
"Lucas". Frames 01 through 06 have a profile with no name and use none.

**`preferred_name` is not `display_name`.** The settings frames show both at
once: "Mock Developer" in the identity block, "What should Argus call you?" as
its own labelled field below a rule, reading "Not set" or "Sin definir" until
the user fills it.

### A note on the duplicated greeting line

Every empty-chat text capture shows the greeting twice. That is expected and
documented in `web/__tests__/empty-chat-greeting-aria.test.ts`: `innerText`
includes both the `aria-hidden` typewriter paragraph and the `sr-only` polite
status region. The accessibility tree contains the sentence once.
