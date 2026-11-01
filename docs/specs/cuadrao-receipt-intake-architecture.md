# Cuadrao receipt intake architecture

**Status:** approved for the pilot, November 1, 2026. The founder picked Option B. Step 1 of the order of work is built and default off, and no hosted service runs it.
**Evidence:** measured at `3be901133` on a local copy of the staging shape (0.5 CPU, 512 MiB, real Postgres, Auth and Storage, fake 30 second read). These are not hosted numbers.

## The rule

The API stays lean. A request saves the file and answers. Reading runs apart from the API. Upload, email and WhatsApp use one path to reading.

## What we measured

- With the limit lifted, 70 uploads of 5 MB photos in one minute killed the API at 24 seconds, and all 26 reads in flight were lost. The cause is memory. Each read in flight holds about 7 to 9 MiB.
- At today's limit of 5 uploads per minute the web path is safe. The API peaked at 357 MiB.
- WhatsApp and email skip that limit. WhatsApp has no cap. That risk comes from reading the code, not a run.
- Turning on `CUADRAO_DOCUMENT_JOBS_ENABLED` alone does not help. Reads stay in the API.
- A prototype worker ran the existing job code unchanged. The API stayed at 334 MiB for a 70 photo run.
- An unpaced burst still crashed the API until a gate of 3 uploads in flight went in front of the body read.
- One Bandeja list of 70 rows runs about 530 statements. The worker does not fix this.

## Today's limits

- 5 uploads per minute and 30 per day, per person, across every Business. Retries and turning reading on share the day count.
- The counters live in API memory, so a restart clears them.
- The web queue waits and resends after a 429. File 31 of the day waits up to 24 hours with no message.

## What the owner sees with the worker

1. The owner drops 70 photos. The browser sends them, and the server takes 3 file bodies at a time. The rest wait seconds in the browser. Every file saves.
2. Each receipt appears in Bandeja at once as Leyendo.
3. The worker reads 3 at a time, oldest first. 70 photos take about 13 minutes by arithmetic, at 33 seconds each. The owner can keep working.
4. A failed read shows a reason, a `Ref.`, and a retry. A stopped worker leaves receipts waiting, and nothing is lost.

So there are two separate 3s: uploads in flight protect API memory, and reads at once protect the provider and the budget.

## Options

| | A. Cap in the API | B. Plain worker | C. Render Workflow tasks |
|---|---|---|---|
| Reading runs | In the API | Separate service, cap 3 | One Render run per read |
| Crash loses reads | Yes | No | No |
| Concurrency cap | Semaphore | In the pull loop | Needs a gate in the API |
| Staging needs | One flag | One new service | New Workflow service and a Render key |
| Size, estimated | About 100 lines | About 400 lines and tests | About 250 lines and tests |
| Monthly cost | $0 | About $7, unconfirmed | About $0.35 per 70 reads, by arithmetic |

## Proposed pilot limits

Each limit guards one thing. The numbers are proposals, and the pilot will teach us what to limit and charge for.

| Guard | Protects | Key | Value |
|---|---|---|---|
| Uploads in flight | API memory | Process | 3 |
| Upload rate | API | Person | 120 per minute |
| Daily uploads | Abuse | Person | 1,000 |
| Reads at once | Provider and worker memory | All workers | 3 |
| Reads per day | Spend | Business | 300, about $7.50 |
| Reads per month | Spend | Business | 2,000, about $50 |

Over a Business budget the file is still saved, unread, with a reason. No capture is refused for budget.

## Order of work

1. Queue semantics: a queued read is waiting, not dead. Worker entry, cap, drain, and the sweep moves to the worker.
2. Lean upload: gate before the body, lighter checks in the request.
3. Limits: split the counters, add the Business read budget.
4. Provider refusals: a 429 or 503 requeues the receipt and pauses pulls.
5. WhatsApp: cap its background work, and keep the locked follow-up.
6. Bandeja: one counts query, and fix the 530 statement list.
7. Hosted milestone: new service, same SHA, then a 70 photo rehearsal with synthetic files.
8. Speed: a separate lane with a scorecard for any model-facing change.

Bridge until then: raise the upload day limit to 150, and keep 5 per minute.

## Not proven

- Hosted CPU, memory and latency.
- Provider rate limits, and latency with 3 reads at once.
- That 3 is the right number.
- WhatsApp and email under load.
- Real phone photos.
- Render plan and worker price.

`docs/ARCHITECTURE.md` records why receipt reads use the plain worker and not Render Workflows: the need is a concurrency cap.
