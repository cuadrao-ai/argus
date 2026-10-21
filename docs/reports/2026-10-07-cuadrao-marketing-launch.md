# Cuadrao marketing launch record

Status record for [#880](https://github.com/lagarcess/argus/issues/880) and its children. The [launch runbook](../runbooks/cuadrao-marketing-launch.md) owns settings and procedure, the [forms contract](../specs/cuadrao-marketing-forms-contract.md) owns the endpoints and data, and the [evidence folder](evidence/cuadrao-marketing-launch/README.md) holds the proof. This page only says where the launch stands. It authorizes nothing.

## Landing

PR [#895](https://github.com/lagarcess/argus/pull/895) merged into `codex/private-alpha-next` as `fbb6bb447` (squash, PR head `d0447a7da`); integration then stood at `5def72db1` after #899 and #894. The merged diff equals the PR diff, `marketing/` and the signup migration are byte-identical to the PR head, `web/` equals its pre-website state, and #895 shares no file with #899 or #894. Nothing is promoted, deployed, applied or sent; the signup migration is in the repository only. The issue comments on #880 record the landing in full.

PR [#903](https://github.com/lagarcess/argus/pull/903) merged as `1ffb53548` (squash, PR head `32ad2c207`, merged 2026-10-08 19:25 UTC; integration parent `f5a2007cd` after #920). It carries the read-only origin verifier, the claim-then-send availability notices and the launch record. CI was green at the head, the independent review at that head was clean with no blocking finding, and the merged tree equals the PR head on every path it touches (its 10 files; none shared with #920). Nothing is promoted, deployed, applied or sent.

Review findings, none blocking, are settled in [#923](https://github.com/lagarcess/argus/pull/923) (merged, below): the run stops after the first unknown send so an outage cannot claim the whole list; a refusal whose claim cannot be released is named separately; hand-sending an uncertain claim says to check Resend by key first and to run one notice at a time; the verifier checks a redirect's host; and the runbook, storage proof and evidence README are reconciled. No availability notice is run before Personal signups are published.

PR [#923](https://github.com/lagarcess/argus/pull/923) merged as `a9a30b37d` (squash, PR head `37c68ea81`, merged 2026-10-08 20:25 UTC; integration parent `b30ef3bab` after #922). It settles the #903 review notes as a code change: the notice run stops at the first unknown send, a refusal whose claim cannot be released is named separately, the hand-send advice says to check Resend and `notified_at` first, and the origin verifier checks the host of a redirect. An independent review of #923 as code was clean at `5698c7776` with no blocking finding and a second clean pass on its documentation-only delta; all 18 checks were green at the head; the merged tree equals the PR head on its paths and touches only `marketing/` and documents. Nothing is promoted, applied, deployed or sent.

PR [#906](https://github.com/lagarcess/argus/pull/906) carries the privacy rewrite, the chosen mark and the brand artwork. Its own landing is recorded below once it merges.

## Lineage

- Lane base: `93571e593e1677561e1dd38f63b6475574942e2d` (`origin/codex/private-alpha-next`, fetched 2026-10-07).
- Worker branch: `codex/cuadrao-marketing-launch`.
- Candidate, reconciliation and CI state are filled in at READY (see the PR).

## Landed in #895

| Child | State |
| --- | --- |
| #887 independent package | `marketing/` builds from a clean frozen install with Bun 1.3.14 on Node 24.21.0, starts with an empty environment, and renders byte-identical screenshots to the legacy pages in Chromium and WebKit at 1440 and 390 pixels, in both languages. |
| #888 identity and metadata | One route owner drives canonical, hreflang, sitemap, redirects and navigation. The Cuadrao icon ("Lean, calm") replaces the inherited Argus icon. The founder chose it on 2026-10-08. |
| #881 Business inquiries | Implemented and covered by unit and browser tests against a recording mock. The destination is configurable (`CUADRAO_INQUIRY_TO`, no default); the founder chose `hola@cuadrao.ai` on 2026-10-08, and real receipt is checked at hosted acceptance. |
| #882 Personal signups | Implemented. Table contract proven against real Postgres and PostgREST locally. Hosted storage, removal and notice are not yet proven. |
| #889 transactional email | Plan and records procedure written. Nothing read or changed in Resend or Cloudflare yet. |
| #890 promotion and Render | Promotion diff measured and a bounded option prepared. Render settings written. Service not created. |
| #891 domain | Procedure written. Nothing changed. |
| #892 app and news | Deferred. No change. |

## Hosted readback (read-only, 2026-10-07)

Through the Supabase connector, with no row data read:

- Project `Argus` (`us-east-2`, Postgres 17) reported `INACTIVE` at the first read and `ACTIVE_HEALTHY` minutes later. No activation or plan change was requested by this lane.
- The production migration ledger has 81 entries. The latest is `20260914120000_share_plain_answer_receipts`, identical to `main`'s newest migration file. The signup migration (`20260920000000`) therefore sorts after everything production has applied and before the 35 integration migrations production lacks.

## Render, Resend and DNS readback (read-only, 2026-10-07)

Through the connected Render and Resend tools and public DNS lookups. Nothing was changed and no secret or setting value was read.

- **Render.** Three workspaces: `argus-prod`, `payment-ledger`, `rag-lens`. Only `argus-prod` holds Argus: `argus-app` (Node, `web`, Starter, branch `main`, Auto-Deploy off, build `npm install -g bun && bun install --frozen-lockfile && bun run build`, start `bun run start -- -p $PORT`, no health check path) and `argus-api` (Python, Standard, Auto-Deploy off). No `cuadrao-marketing` service exists, so there is no name collision. `argus-app` shows Bun installed during build is usable at start, so either start command would work; the runbook keeps `npm run start`.
- **Resend.** Two domains, both verified with sending enabled and receiving disabled: `cuadrao.ai` (created 2026-09-29) and `get-argus.com`. `notify.cuadrao.ai` is not registered, so nothing about it exists yet. `cuadrao.ai` lists a DKIM TXT at `resend._domainkey` and two CNAMEs, `send` and `rsend`, all marked verified.
- **DNS and the current mail provider (corrected 2026-10-08).** `cuadrao.ai` is registered at Cloudflare (active, expires 2028-09-29) with Cloudflare name servers. Read from three public resolvers and from DNS over HTTPS, which agree: the apex mail is **iCloud Mail** (MX `mx01.mail.icloud.com` and `mx02.mail.icloud.com`, priority 10; TXT `apple-domain=` verification and SPF `v=spf1 include:icloud.com ~all`). There is no apex A record and no DMARC record. Resend's records for `cuadrao.ai` are published: a DKIM TXT at `resend._domainkey` and CNAMEs `send` and `rsend` to Resend's forge hosts. `www`, `api`, `app`, `notify` and `news` have no records. **An earlier version of this record said the apex had no records and no mail route, and that `hola@cuadrao.ai` could not receive mail. That was wrong:** the first lookups returned empty answers through a path that did not hold up, and the corrected reading agrees across resolvers. Whether `hola@cuadrao.ai` exists as an address on the iCloud custom domain cannot be seen in DNS and is for the founder to confirm.

## Supabase preview branch for #895 (read-only, 2026-10-07)

- **What exists.** One branch on project `qzylwjabjfophhipzoev`, name and Git branch `codex/cuadrao-marketing-launch`, PR 895, parent `lgdhvepyrzbnscqssgqq`, `persistent: false`, `with_data: false`, preview project `ACTIVE_HEALTHY`. A second branch record is the production project itself (`main`, status `MIGRATIONS_FAILED`, last updated 2026-06-04).
- **How it was created.** Not by this lane's tools. Its creation time (17:27:22Z) is seven seconds after PR 895 was opened (17:27:15Z), and it carries the Git branch and PR number. That is the Supabase GitHub integration's automatic preview branching, which also produces the `Supabase Preview` check. The check ran schema-only: it replayed the repository's migration chain (it lists this migration at its proper place) and no production data was copied. Earlier PRs show the same check. This lane created no hosted resource.
- **Charges.** Supabase documents no fixed fee for a branch, only usage. The connector quotes `0.01344` USD per hour for a branch (the default Micro compute), about $0.32 a day or $9.68 for a month if it ran continuously, plus egress and disk beyond the plan quota. Branch usage is not covered by the Spend Cap, and Compute Credits do not apply to it. Branching is documented as a Pro Plan feature, yet the organization (`ARGUS QUANTITATIVE`) reports the `free` plan, and the repository notes elsewhere that preview branches have hit plan quota. The connector exposes no invoice, so whether this branch is billed, and how much, is not confirmed. The Supabase usage page shows "Branching Compute Hours" and settles it.
- **Direct API readback (2026-10-07, later).** The Management API (read-only GET with the account token from the integration worktree's local `.env`, never printed) lists exactly two branches: the production `main` record with an empty Git branch and status `MIGRATIONS_FAILED`, and `codex/cuadrao-marketing-launch` (PR 895, `FUNCTIONS_DEPLOYED`). The two integration toggles ("Automatic branching", "Deploy to production") are dashboard-only; the platform API returned 401 for the token, so they still need one look in the dashboard.
- **Lifetime.** A non-persistent branch is removed when its PR is closed or merged, and preview branches auto-pause after inactivity.
- **Outcome.** The branch was removed after #895 merged (a non-persistent branch goes with its PR); no one in this lane deleted it. Automatic previews are not part of the agreed spending plan and no paid upgrade is authorized, but the toggle cannot be changed on Free, so the plan is to watch rather than disable (below). The earlier "disable and delete" steps were withdrawn.

### Supabase GitHub integration (resolved 2026-10-08)

The founder disabled the project's Supabase GitHub integration. Supabase stays on the Free plan and no paid upgrade is authorized.

| Behavior | State | How known |
| --- | --- | --- |
| Deploy to production from `main` | **Off** | Founder, in the dashboard; the production branch record has no Git branch |
| Preview branching | **Gone with the integration** | Behavior, below |

**Verified by behavior** (the API cannot show the connection itself): the branch list holds only the production `main` record; a probe commit pushed to a draft PR at 02:03:02 UTC carried 18 GitHub Actions checks and no Supabase check, where the previous head of the same PR had one; #905 (reopened), #908 and #909 (new PRs that change `supabase/migrations`) produced no preview, no Supabase check and no Supabase comment, read 30 seconds after each opened.

**Historic cost note, still open.** Two preview branches existed while the integration was on: the one for #895 (until it merged) and the one for #905 (about two minutes). Whether either was billed is unconfirmed; the connector quoted `0.01344` USD per branch-hour, and the usage page's "Branching Compute Hours" would settle it. The mismatch (previews created although the dashboard showed a branch limit of 0) is no longer live and was not explained.

**Effect on CI.** `Supabase Preview` was never a required check, and it no longer runs. The repository's `guest-release-gates` job replays every migration on a disposable local Supabase stack on the pinned and latest CLI, and runs every `test_*_postgres.py` proof; that is the coverage the merge decision rests on.

## `notify.cuadrao.ai` and the Cloudflare zone (2026-10-08)

With the founder's approval, `notify.cuadrao.ai` was created in Resend (domain `520a3906-baaf-4e70-bd3e-eff49448a9e8`, region `us-east-1`, sending on, receiving off, open and click tracking off, TLS opportunistic). Resend returned records that differ from the root domain's, so they were copied exactly:

| Type | Name | Content | Priority |
| --- | --- | --- | --- |
| TXT | `resend._domainkey.notify` | DKIM key beginning `p=MIGfMA0GCSqG`, ending `kTSD4EQIDAQAB` | |
| MX | `send.notify` | `feedback-smtp.us-east-1.amazonses.com` | 10 |
| TXT | `send.notify` | `v=spf1 include:amazonses.com ~all` | |
| CNAME | `rsend.notify` | `send.forge.rmta.net` (DNS only) | |

The founder added the DKIM record by hand and, through a zone-scoped, day-long Cloudflare token he created, the other three were added by a script that first ran as a dry run, refused to write unless the DKIM matched Resend's value exactly, and read the zone back. The zone had 9 records before and 12 after; **0 of the 9 existing records changed**. The iCloud mail records (two MX, SPF, the Apple domain TXT, the `sig1._domainkey` CNAME) and Resend's root-domain records are untouched. The token has since been deleted. Resend reports the domain **Verified** with all four records verified. No email has been sent. The sending key is created by the founder, limited to this domain, and never passes through the agent.

## Migration identity (for the approval record)

`supabase/migrations/20260920000000_cuadrao_early_access_signups.sql`: file SHA-256 `ea2a2a010d31f1c05222561d5f90fa024df2fac46a466107c7bdf3138d11aad0`; 5 statements; statement-array SHA-256 (the gate's `_statements_sha256`) `cafee0efce903bcdbdde9f2d1e200254a1f2a2486e26b8413d8d044e7ad4fbca`. The applier's run digest for this single-version run (`versions_digest(["20260920000000"])`) is `090e86fa74fb104a0d3984653624cf72fd65faa8ac7bb2a930ed937c73fb0f8f`; it hashes the version list, not the file. The migration is applied alone and first (C0); the consumer's `20260505000001` repair runs in its own batch and is not part of this release.

## Not yet true

- Nothing is deployed. No Render service exists, no migration was applied, no email was sent, and nothing was promoted to `main`.
- The only hosted changes so far are the `notify.cuadrao.ai` Resend domain and its four DNS records (above), and the founder's disabling of the Supabase GitHub integration.
- The Spanish and English privacy wording was approved by the founder on 2026-10-08 as a draft, which is not permission to publish. The operator wording and the public contact and signup forms stay held until the founder confirms Cuadrao LLC is formed and operates the site. The icon is chosen.
- Hosted acceptance (real inquiry receipt, signup, removal, public domain) has not happened.

## Copy

The privacy page wording (both languages, `marketing/components/privacy-copy.ts`) was approved by the founder on 2026-10-08 as a draft, which is not permission to publish. The approval named the privacy wording only, so the form strings below, shown in the same review, are confirmed with the founder before publication.

Spanish first, English follows. Only strings whose meaning changed with real delivery or storage are new. Everything else is the approved copy, unchanged.

| Where | Spanish | English |
| --- | --- | --- |
| Contact, send button | Enviar mensaje | Send message |
| Contact, while sending | Enviando… | Sending… |
| Contact, sent title | Recibimos tu mensaje. | We received your message. |
| Contact, sent body | Te responderemos al correo que escribiste. | We'll reply to the email address you entered. |
| Contact, failure | No pudimos enviar tu mensaje. Lo que escribiste sigue aquí. Inténtalo de nuevo o escríbenos a hola@cuadrao.ai. | We couldn't send your message. What you wrote is still here. Try again or email us at hola@cuadrao.ai. |
| Contact, too many attempts | Hiciste varios intentos seguidos. Espera unos minutos e inténtalo de nuevo. | You made several attempts in a row. Wait a few minutes and try again. |
| Contact, field problem from the server | Revisa los campos marcados e inténtalo de nuevo. | Check the marked fields and try again. |
| Contact, no JavaScript | Activa JavaScript para enviar este formulario o escríbenos a hola@cuadrao.ai. | Enable JavaScript to send this form or email us at hola@cuadrao.ai. |
| Contact, under the form | Usamos tu nombre, correo y mensaje para responderte. Política de privacidad | We use your name, email and message to reply to you. Privacy policy |
| Personal, under the form | Usaremos tu correo solo para avisarte sobre el acceso anticipado a Cuadrao. Para retirar tu registro, escríbenos a hola@cuadrao.ai. Política de privacidad. | We'll use your email only to tell you about Cuadrao early access. To remove your signup, email hola@cuadrao.ai. Privacy policy. |
| Personal, too many attempts | Hiciste varios intentos seguidos. Espera unos minutos e inténtalo de nuevo. | You made several attempts in a row. Wait a few minutes and try again. |
| Footer link (new) | Privacidad | Privacy |
| Privacy page | [privacy-copy.ts](../../marketing/components/privacy-copy.ts), both languages | same file |

Removed: the "Vista local" notices and "no se envía nada" lines on contact, and "El registro aún no está conectado" on Personal. Each stated that nothing was sent or stored, which stops being true.

The privacy text states facts the founder confirmed: contact messages stay in the mailbox as long as needed to reply, early-access signups stay until removal is requested, Resend, Apple iCloud Mail, Supabase (United States, Ohio) and Cloudflare are the providers, and hosting may record connection data such as the IP address. It names no operator. The operator wording ("Cuadrao LLC", formation pending) is prepared in the runbook and held until the founder confirms the company is formed and operates the site; the public contact and signup forms are held with it. The text also says what the site itself keeps to slow automated submissions: the visitor's address, and the email of someone who writes, held in the server's memory for at most two hours (a timer sweeps expired keys once per window), never in a database. A removed signup keeps its digest, language and dates, as the text says. This wording changed after the founder's draft approval (the contact line no longer says "solo para responderte" because the email also keys that limit), so it is shown to the founder again before #906 merges.

## Founder inputs and approvals needed

The concrete approval request, in deployment order, is posted on #880. It covers the website-only promotion to `main`, applying `20260920000000` alone through the consumer's reviewed applier, creating the Render service and its cost, the first inquiry and signup tests with two founder-supplied addresses, and publication. #903 and #923 are merged into integration with the founder's approval, and #906 merges after the founder approves its revised privacy wording; none of those merges authorizes any of the actions above.
