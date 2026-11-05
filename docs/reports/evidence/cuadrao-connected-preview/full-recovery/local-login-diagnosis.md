# Local phone sign-in diagnosis

Diagnosis completed 2026-10-06, approximately 01:08 UTC. Read-only investigation of the isolated API at 59650 and Supabase at 59651. No login requests were issued during this investigation. No source, service, config, credential, database, or app changes were made. Only this report was written.

## Conclusion

The current blocker is confirmed Docker VM memory exhaustion and service starvation. Supabase Auth no longer answers even its health endpoint. The API process remains responsive. This is a shared Docker failure, not evidence of a wrong password or malformed CAPTCHA field.

The API presents all exceptions from the gateway login call as the same 401. This explains why an unavailable Auth dependency can appear as a sign-in rejection. The exact upstream response behind the earlier reported 401 was not captured, because the Docker daemon and Auth/Kong log endpoints were already unresponsive. Its precise HTTP status/error code remains unknown.

## Direct runtime evidence

With local network access allowed:

| Read-only check | Result |
| --- | --- |
| API 59650 `/health`, urllib | 200, 0.009 seconds |
| API 59650 `/health`, HTTPX | 200, 0.060 seconds |
| Supabase 59651 `/auth/v1/health`, urllib with anon header | Timeout at 8.006 seconds |
| Supabase 59651 `/auth/v1/health`, HTTPX with anon header | ReadTimeout at 8.060 seconds |
| Docker Unix socket `/_ping` | No response bytes within 6.006 seconds |
| Auth container log read | Timed out at 12.012 seconds |
| Kong container log read | Timed out at 12.006 seconds |

Docker still owned TCP 59651; the local Python API still owned TCP 59650. A read-only `docker ps` hung and was canceled. Initial sandbox-denied HTTP attempts were excluded from the service evidence above.

The parent independently observed Supabase 59851 timing out while API 59850 returned 200, corroborating failure across both local stacks. This report did not probe that second stack.

## Exact Docker VM evidence

Source: `/Users/garces/Library/Containers/com.docker.docker/Data/log/vm/init.log` and its existing `init.log.20261005-*` rotations. These are local Docker host log files, so their contents remain readable while the daemon is stalled.

Selected `kmsg` records:

```text
2026-10-06T00:49:34.701959726Z  Free swap  = 164kB
2026-10-06T00:49:34.701969601Z  Total swap = 1048572kB
2026-10-06T00:49:34.701979559Z  2097152 pages RAM
2026-10-06T00:49:35.485696143Z  Out of memory: Killed process 28303 (python) total-vm:1143676kB, anon-rss:83912kB, file-rss:4kB, shmem-rss:4kB, UID:1002 pgtables:460kB oom_score_adj:1000
2026-10-06T01:04:47.658585091Z  oom-kill:constraint=CONSTRAINT_NONE,...,global_oom,...,task=python,pid=36659,uid=1002
2026-10-06T01:04:47.658603841Z  Out of memory: Killed process 36659 (python) total-vm:1362200kB, anon-rss:89392kB, file-rss:36kB, shmem-rss:4kB, UID:1002 pgtables:516kB oom_score_adj:1000
2026-10-06T01:05:15.516500794Z  Out of memory: Killed process 36772 (python) total-vm:1362212kB, anon-rss:89440kB, file-rss:124kB, shmem-rss:4kB, UID:1002 pgtables:516kB oom_score_adj:1000
```

The global-OOM excerpt omits only the container cgroup identifier. At 01:04:20.468225815Z, the `command` component also reports `Health check for container [identifier omitted] error: timed out starting health check for container [identifier omitted]`.

The available log snapshot, filtered from 00:30 UTC through the latest observed OOM at 01:05:15 UTC, contains **43 OOM-killed Python processes**, **849 health-check start timeouts**, and **78 distinct container identifiers** with those timeouts. The 78 figure is affected containers, not a verified count of stacks or currently running containers. Docker could not answer the inventory request.

Observed RAM is 2,097,152 pages and swap is approximately 1 GiB, almost fully consumed at the first quoted OOM. At 4 KiB per page this RAM count is 8 GiB; page size and a configured memory setting were not independently confirmed. No memory allocation was changed.

## Request-shape and code evidence

Installed packages: `supabase-auth` 2.28.3, `supabase` 2.28.3, HTTPX 0.28.1. The installed `sign_in_with_password` method correctly translates `options.captcha_token` into `gotrue_meta_security.captcha_token`. No proxy variables were present in the diagnostic shell. These checks did not authenticate a user.

In `/Users/garces/.codex/worktrees/cuadrao-connected-preview/private-alpha-next`:

- `src/argus/domain/supabase_gateway.py:144-169` creates the HTTP/1.1 Auth client with a 120-second timeout.
- `src/argus/domain/supabase_gateway.py:494-512` passes the supplied CAPTCHA field and wraps any provider exception.
- `src/argus/api/routers/auth.py:853-860` catches every gateway login exception and returns the common login problem. Therefore a 401 alone cannot distinguish invalid credentials from an upstream failure.

The parent's earlier direct Supabase login and authenticated `/me` success were reported context, not repeated here. No credentials, tokens, or whole configs are included in this report.

## Smallest nondestructive recovery

Coordinate the shared Docker owner before recovery. Restore Docker VM responsiveness and available memory; the parent is coordinating a Docker Desktop restart. Preserve all named volumes, databases, credentials, and lane configuration. Do not reset or prune, change global settings, weaken auth/CAPTCHA, rotate credentials, or change the TLS bridge.

A restart may restore service, but memory pressure can recur if the same workload resumes. Once the daemon responds, identify workload ownership and stop only explicitly approved unneeded workloads if capacity is still exhausted.

Before any new sign-in attempt, confirm Docker `/_ping` and both owned Supabase Auth health endpoints respond. Then run one synthetic API sign-in and authenticated `/me` read. The original phone recovery is not verified until these pass. No further auth requests or recovery actions were performed by this investigator.
