# Canary fixture close regression

Issue [#861](https://github.com/lagarcess/argus/issues/861) repairs the synthetic
Supabase server used by the canary session tests. The fixture responds as
HTTP/1.0 and closes each connection. An explicit `Connection: close` response
header tells Bun to open a new connection for the next request.

## Scope and evidence

Original integration base and fetched integration at implementation were both
`f5c83cd88a0af56dc8154a89c6ea4f75d9c518ce`. The failing regression is committed as
`7f36e7620`. Production canary code, authentication behavior, dependencies, and
configuration are unchanged.

The existing mint and revoke test now runs with immediate closure and a 50ms
pause in the fake handler's `finish()` method. The delayed case makes the old
fixture's socket reuse race observable after its body arrives and before the
server closes. Both cases keep the existing identity, credential secrecy,
private file mode `0600`, request authentication, and revocation assertions.
This is a bounded timing perturbation, not a proof under every scheduler.

Local checks used Bun 1.3.14, Supabase JS/auth 2.104.1, Python 3.11.15, and
pytest 8.4.2 on macOS arm64. CI uses Linux and Python 3.10. Dependencies were
read from the existing installed tree without package or lockfile changes.
An explicit `env -i` synthetic environment excluded provider credentials.
All HTTP servers bound ephemeral ports on `127.0.0.1`. No hosted services,
provider calls, PostgreSQL, browser journeys, or root environment files were used.

| Check | Passed | Failed | Skipped |
| --- | ---: | ---: | ---: |
| Delayed close before the response header fix | 0 | 1 | 0 |
| Full canary fixture file plus required mocked evaluation checks after fix | 295 | 0 | 0 |

The failing result was the intended transport failure, not an assertion on a
header string. Sanitized excerpt:

```text
path: http://127.0.0.1:<port>/auth/v1/admin/generate_link
code: ECONNRESET
canary_session_state=failed reason=canary_session_link_failed
1 failed in 1.69s
```

Passing result:

```text
295 passed in 17.02s
```

The checked test file SHA-256 is `c6f978ca2d3881e9a509f97191d508ae1a036deded1943348c99783bb5e032dc`.
Ruff and `git diff --check` also passed.

## Reproduction

Use the repository's locked Python environment and Bun 1.3.14. The focused
command selects both connection timings:

```sh
PYTHONPATH=web:src:. python -m pytest \
  tests/test_private_alpha_canary_split.py::test_session_tool_mints_private_storage_state_and_revokes_it \
  -q --no-cov
```

The passing combined run included the full `tests/test_private_alpha_canary_split.py`
file and all ten mocked harness files listed under `Mocked Run` in
`tests/evals/README.md`. No retry plugin or repeated-until-green execution was used.

## Review and limits

An independent GPT-6 Astra review inspected the complete 12-line test diff and
surrounding code. It found no actionable correctness or scope issues. Its
no-comments review reported zero added comments and zero findings. The review
agent was stopped after its report. Test subprocesses exited and the fixture
closed its servers through its existing cleanup.

The earlier investigation in issue #861 demonstrated the same mechanism with
controlled timing. The original CI failure had no socket trace, so attribution
of that historical failure remains an inference. Local synthetic verification
does not establish hosted canary or release readiness. Exact PR head, current
integration, and terminal CI results belong in the PR acceptance comment.
