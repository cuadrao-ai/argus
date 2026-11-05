# S4 chat surfaces: flag-off identity and isolation evidence log

Label: **local disposable stack and in-process fakes; no provider, model or hosted call.**

Code: branch `claude/business-chats`, S4 commits `81f9fbcb2`, `15016e642`,
`621712657` and `7233903fe` on `76273cf2c` (#914), merged with
`origin/claude/business-spaces` at `111542f12`. Database: the disposable stack
`argus-biz-spaces` (DB 57782) with real local Supabase Auth.

## Flag-off /chat journey is byte-identical

`flag_off_chat_journey_probe.py.txt` is the pytest probe. With
`ARGUS_BUSINESS_PILOT_ENABLED` and sharing unset, it signs in two people on
real Auth and Postgres, then seeds three Personal conversations and their
messages the way pre-S4 code wrote them: the insert names no space column, so
`owner_space_id` is null, like the 676 production conversations. It then runs
21 /chat calls: Recents with a cursor, search with ledger groups, History,
messages, pin, two creates, a decision on a missing message, a sharing route,
the second person's reads, one delete, Recently Deleted, delete-all and the
lists after it.

The same file ran against `76273cf2c` (base) and the S4 head. Ids, timestamps,
cursors and the random test emails are replaced by aliases; the rows that
delete-all soft-deletes in one statement are compared as a set, because their
id tie-break follows random ids. The two dumps are identical:
`sha256 fdc77ce1d02625a59e68964b0f8325819bd9e2ea1a60a3fa54cb74039ef618e6`
(`flag-off-chat-journey.json`).

The web client sends the same bytes too:
`web/__tests__/conversation-surface-api.test.ts` asserts the exact create,
list, History, search and delete-all requests with no surface and with
`personal`.

## D1: a Business conversation in Personal reads

Before S4 a conversation row with `owner_space_id` set appeared in Personal
Recents, search, History and delete-all in any flag state. The new tests
inserted such a row by SQL and ran against the base commit:

- `tests/test_conversation_surfaces_postgres.py`: Personal delete-all with the
  flag off reported `deleted_count: 4` (three Personal and the Business row),
  expected 3.
- `tests/test_conversation_surfaces.py`: Personal Recents, search and History
  each listed both chats.

At base: 12 failed and 6 errored of the new backend tests, and the new
Playwright case found the Promising filter on /biz. At head all pass.

## Suites on the merged head

- Python, Linux container with no network (Postgres tests skip): the only
  failures new against the base were two Recents and History gateway-call
  assertions that lacked the Personal scope; fixed in `782048d27` (108 of 108
  pass). The other 57 failures are identical at base.
- Python, macOS against the disposable stack: every `*_postgres` and local
  Supabase test passes except two that fail identically at base (the scipy
  import trap and a guest tool corridor). The S4 Postgres files, History,
  keyset, search and Business isolation: 72 passed.
- `tests/test_interpreter_prompt_freeze.py` passes unchanged. Modularity
  budget: no violations (`ChatInterface.tsx` and `routers/agent.py` did not
  grow). OpenAPI compatibility passes after regenerating `docs/api/openapi.yaml`
  (additive `surface` fields only).
- Web: `bun test` 2311 pass; `tsc` has no errors outside test files and the
  same test-file errors as base; `eslint` 0 errors. Playwright with
  `PLAYWRIGHT_PORT=3671`: `business-pilot-preview`, `business-pilot-walkthrough`
  and `business-search-preview` 37 of 37.

## Review fixes: surface in conversation responses

After the review, every `Conversation` and the messages page carry `surface`,
so the /chat bodies gain `"surface": "personal"`. The journey was rerun against
the base and the new head. The only differences are 15 added `surface` lines
(14 conversations and 1 messages page); with those lines removed the two dumps
are identical. `flag-off-chat-journey.json` is now the head output. No request
changed, and no other byte of any response changed.
