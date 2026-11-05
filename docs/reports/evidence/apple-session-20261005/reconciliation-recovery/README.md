# Recovery and invite context reconciliation

The original lane base remains `f5c83cd88a0af56dc8154a89c6ea4f75d9c518ce`.
Previous published PR #864 head was `7f920b1c14eac6d3642b195b1ec4d127431b450b`.
Fetched integration was `c0d44d399b8fbf2edcdd0a8fd3ad4759a0e9c548`.
The normal merge is `2018a19c1dcc833d9da17cf7093c4ff0c6dbfe24`.
There were no conflicts, rebases or reconciliation source fixes.

## Actual overlap

PR #845 lands privacy evidence with its stated source and external gates.
It changes no session SDK, profile projection, deletion runtime or provider policy.
PR #865 makes recovery requests use the API's canonical trusted-client header.
Its web release-profile key and YAML alias derive from that existing owner.
The environment loader now derives validated web key membership. PR #871 adds
explicit default-off invite flags to the API release configuration and records
local invite evidence. Its production invite-code change corrects a misleading
comment about generated secret entropy; it changes no runtime guard.

These changes touch configuration owners used by release checks, not the successful
grant journal or native session adoption. Apple/Google release force-off and the
existing session owner remain intact. Whole native source is unchanged. All fifteen
relevant source, SQL, schema and local persistence-test objects match the prior
head. [owners.json](owners.json) records both hashes for the native tree, profile
and name routers, API dependencies, deletion auth/domain, Apple domain, gateway,
schemas, OpenAPI projection, migrations and three PostgreSQL test files.

## Verification

The affected environment-loader, release-profile, web environment, OpenAPI,
profile identity and Apple-name checks passed **128 tests**, with **zero failures**
and **zero skips**, in 26.29 seconds. The exact selected modules and results are
in [focused.txt](focused.txt). Combined modularity reported **zero violations**.
Whitespace checks passed. Python used the existing isolated 3.11 environment and
PYTHONPATH=web:src:.

The prior eight real local profile/name/identity tests remain scoped proof at their
recorded source. Their production owners, SQL and test objects are unchanged,
so no duplicate database run was justified. No new PostgreSQL or mocked-harness
pass is claimed. No database lease, Swift build, simulator operation, provider call,
root .env, hosted environment, real user data or paid call was used.

Combined native acceptance remains open from the earlier actual currency/session
merge. Historical package/model/UI evidence does not verify that combined source.
Counsel still owns the Mac. The captain must schedule the combined package/model
and Apple recovery/currency EN/ES journeys, including denied currency dispatch
while validation is held or unknown linked sessions require reauthentication.
Independent latest-context review and terminal exact-head CI are still required
before merge. Phone, provider, hosted and activation gates remain open.

The worker created no services or background children. Test processes exited.
The published branch and committed evidence are handed back to the captain's one
integration merge queue. The worker stops writes after publication.
