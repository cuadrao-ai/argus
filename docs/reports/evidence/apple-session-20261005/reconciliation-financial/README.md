# Analytics and financial integration reconciliation

Original lane integration base remains
`f5c83cd88a0af56dc8154a89c6ea4f75d9c518ce`. Previous published PR #864 head was
`a24a6c60627460ddfd6042b3f42b342c5eff11f0`. Fetched current integration was
`7d037b07d4b98b34c6c0ad3026811c7d2f28ae47`. The normal reconciliation merge is
`18d1b783c27cd6119d90497dec8c5a911af6e448`. No conflict or rebase occurred.

## Semantic overlap

PR #847 adds analytics deletion submission/status evidence to the existing
deletion service. The change affects its analytics step, not the Apple identity
reader, profile mutations, grant journal or name command. It preserves pending
and failed deletion states. This session slice does not interpret those analytics
states or claim provider deletion proof. Activation and hosted proof stay open.

PR #854 adds paired transfers and currency-specific financial contributions,
plus release configuration membership. It adds destination_amount to the generated
OpenAPI artifact. This combines with the profile identity and name schemas without
textual conflict. Structural OpenAPI tests passed, so no regeneration was needed.
This reconciliation changes no generated-schema annotation or financial rule.

The existing ProfileAuthModel and SessionController continue to own authentication
and primary currency. Financial commands still use their validated authenticated
transport. Native source and profile/name/identity persistence owners are exactly
unchanged from the previous published head. [owners.json](owners.json) records
matching Git object hashes for all native source, both profile routers, Apple
identity/name domain, Supabase gateway and three affected local persistence tests.

## Current proof

Focused profile, identity, name, schema, deletion API, analytics adapter and release
configuration context checks passed **200 tests**, with **69 deselected**, **zero
failures** and **zero skips**, in 8.48 seconds. The free ten-file mocked eval harness
passed **272 tests**, with **zero failures** and **zero skips**, in 9.14 seconds.
Combined modularity reported **zero violations**. Whitespace checks passed.

Python used the existing isolated 3.11 environment and PYTHONPATH=web:src:.
No PostgreSQL lease, Auth service, provider, root .env, hosted environment or real
user data was used. Earlier eight real local profile/identity/name tests remain
scoped evidence. Their owners and tests are unchanged; the changed deletion
analytics step is not called by those assertions. No new PostgreSQL pass is claimed.

## Remaining gate

Native code is unchanged in this merge. Combined native acceptance was already
pending from the earlier actual currency/session merge. Earlier native evidence
still covers only its recorded source; this source comparison does not close that
gate. Counsel owns the Mac and simulator, and this worker ran no Swift builds or
simulator operations. Before PR #864 merges, the captain must obtain the combined
session package/model tests and affected Apple recovery and currency EN/ES journeys,
including denied currency dispatch while Apple validation is held or unknown mixed
sessions need reauthentication. Independent review and exact-head CI remain required.
The phone, provider authorization, hosted acceptance and activation gates stay open.

No native layouts, name journal, provider policies or separate consent owners were
changed. The branch and evidence are left for the captain's single merge queue.
No services or background processes were created. All tests exited before publication.
