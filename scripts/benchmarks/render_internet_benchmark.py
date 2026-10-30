#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from math import isfinite
from pathlib import Path
from typing import Any, NamedTuple

import httpx
from dotenv import load_dotenv

DEFAULT_APP_URL = "https://argus-app-suz5.onrender.com"
DEFAULT_PROMPT = (
    "Test an equal-weight AAPL and MSFT buy-and-hold strategy from January 1, "
    "2025 through June 5, 2026 with 10,000 dollars"
)
TERMINAL_JOB_STATUSES = {"succeeded", "failed", "canceled", "expired"}


class RunReference(NamedTuple):
    kind: str
    id: str


class ParsedSseEvents(NamedTuple):
    events: list[dict[str, Any]]
    done: bool


class TimedResponse(NamedTuple):
    elapsed_ms: float
    status_code: int
    body: Any | None = None


def default_output_dir(repo_root: Path) -> Path:
    return repo_root / "temp" / "benchmarks" / "render-internet"


def parse_sse_events(stream_text: str) -> ParsedSseEvents:
    events: list[dict[str, Any]] = []
    done = False
    for part in stream_text.split("\n\n"):
        data_lines: list[str] = []
        for line in part.splitlines():
            if line.startswith("data:"):
                data_lines.append(line.removeprefix("data:").strip())
        if not data_lines:
            continue
        raw = "\n".join(data_lines).strip()
        if not raw:
            continue
        if raw == "[DONE]":
            done = True
            continue
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            events.append(parsed)
    return ParsedSseEvents(events=events, done=done)


def extract_confirmation_run_action(events: list[dict[str, Any]]) -> dict[str, Any]:
    for confirmation in _confirmation_cards(events):
        actions = confirmation.get("actions")
        if not isinstance(actions, list):
            continue
        for action in actions:
            if isinstance(action, dict) and action.get("type") == "run_backtest":
                return dict(action)
    raise RuntimeError("confirmation stream did not include a run_backtest action")


def _run_action_headers(action: dict[str, Any]) -> dict[str, str]:
    payload = action.get("payload")
    confirmation_id = (
        str(payload.get("confirmation_id") or "").strip()
        if isinstance(payload, dict)
        else ""
    )
    if not confirmation_id:
        raise RuntimeError("run_backtest action did not include confirmation_id")
    return {"Idempotency-Key": confirmation_id}


def extract_run_reference(events: list[dict[str, Any]]) -> RunReference:
    finals = [event.get("payload", {}) for event in events if event.get("type") == "final"]
    for payload in finals:
        if not isinstance(payload, dict):
            continue
        job = payload.get("backtest_job")
        if isinstance(job, dict) and job.get("id"):
            return RunReference(kind="job", id=str(job["id"]))
        final_response_payload = payload.get("final_response_payload")
        if isinstance(final_response_payload, dict):
            job = final_response_payload.get("backtest_job")
            if isinstance(job, dict) and job.get("id"):
                return RunReference(kind="job", id=str(job["id"]))
    for payload in finals:
        if not isinstance(payload, dict):
            continue
        run = payload.get("run")
        if isinstance(run, dict) and run.get("id"):
            return RunReference(kind="run", id=str(run["id"]))
        final_response_payload = payload.get("final_response_payload")
        if isinstance(final_response_payload, dict):
            run = final_response_payload.get("run")
            if isinstance(run, dict) and run.get("id"):
                return RunReference(kind="run", id=str(run["id"]))
    raise RuntimeError("run stream returned neither backtest_job nor backtest_run")


def render_markdown_summary(report: dict[str, Any]) -> str:
    lines = [
        "# Argus Render Internet Benchmark",
        "",
        f"- Generated: {report['generated_at']}",
        f"- API URL: `{report['api_url']}`",
        f"- App URL: `{report['app_url']}`",
        "",
        "## Runs",
        "",
        "| Case | Iteration | Status | Total | Warmup | Post Warmup | Confirmation | Run Stream | Job Poll | Render Task | Voice |",
        "| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for run in report.get("runs", []):
        timings = run.get("timings_ms", {})
        voice = run.get("voice", {})
        fallback = voice.get("result_readout_fallback_used")
        voice_label = (
            f"{voice.get('result_readout_source') or 'unknown'}"
            f" / fallback={fallback}"
        )
        lines.append(
            "| "
            + " | ".join(
                [
                    str(run.get("case_id") or ""),
                    str(run.get("iteration") or ""),
                    str(run.get("status") or ""),
                    _format_seconds(timings.get("total")),
                    _format_seconds(timings.get("warmup_total")),
                    _format_seconds(_post_warmup_ms(timings)),
                    _format_seconds(timings.get("confirmation_stream")),
                    _format_seconds(timings.get("run_stream")),
                    _format_seconds(timings.get("job_poll_until_terminal")),
                    _format_seconds(timings.get("render_task_duration")),
                    voice_label,
                ]
            )
            + " |"
        )
    stream_timing_rows = _stream_timing_rows(report)
    if stream_timing_rows:
        lines.extend(
            [
                "",
                "## Stream Phase Timings",
                "",
                "| Case | Iteration | Stream | Response Headers | First Byte | First SSE | First Token | Total |",
                "| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for run, stream_name, stream_timings in stream_timing_rows:
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(run.get("case_id") or ""),
                        str(run.get("iteration") or ""),
                        stream_name,
                        _format_seconds(stream_timings.get("response_headers")),
                        _format_seconds(stream_timings.get("first_byte")),
                        _format_seconds(stream_timings.get("first_sse_event")),
                        _format_seconds(stream_timings.get("first_token")),
                        _format_seconds(stream_timings.get("total")),
                    ]
                )
                + " |"
            )
    workflow_timing_rows = _workflow_timing_rows(report)
    if workflow_timing_rows:
        lines.extend(
            [
                "",
                "## Workflow Internal Timings",
                "",
                "| Case | Iteration | Task Total | Dependency/Tool | Provider Fetch | Engine Compute | Chart/Result | Result Readout | Run Persist | Link Result |",
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for run, workflow_timings in workflow_timing_rows:
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(run.get("case_id") or ""),
                        str(run.get("iteration") or ""),
                        _format_seconds(workflow_timings.get("workflow_task_total")),
                        _format_seconds(
                            workflow_timings.get("dependency_or_tool_load")
                        ),
                        _format_seconds(workflow_timings.get("provider_fetch_total")),
                        _format_seconds(workflow_timings.get("engine_compute_total")),
                        _format_seconds(
                            workflow_timings.get("chart_result_build_total")
                        ),
                        _format_seconds(workflow_timings.get("result_readout_total")),
                        _format_seconds(workflow_timings.get("backtest_run_persist")),
                        _format_seconds(workflow_timings.get("link_result")),
                    ]
                )
                + " |"
            )
    unavailable = report.get("metrics_unavailable") or []
    if unavailable:
        lines.extend(
            [
                "",
                "## Unavailable Metrics",
                "",
                "These were not collected by this live benchmark run:",
                "",
                *[f"- `{name}`" for name in unavailable],
            ]
        )
    caveats = report.get("caveats") or []
    if caveats:
        lines.extend(["", "## Caveats", "", *[f"- {item}" for item in caveats]])
    return "\n".join(lines) + "\n"


def run_benchmark(
    *,
    repo_root: Path,
    output_dir: Path,
    api_url: str,
    app_url: str,
    email: str,
    password: str,
    supabase_url: str | None,
    supabase_service_role_key: str | None,
    ops_token: str | None,
    prompt: str,
    repeat: int,
    timeout_seconds: float,
    poll_sleep_seconds: float,
    require_async_job: bool,
    render_api_key: str | None,
) -> dict[str, Any]:
    api_url = api_url.rstrip("/")
    app_url = app_url.rstrip("/")
    started_at = datetime.now(timezone.utc)
    runs: list[dict[str, Any]] = []
    for iteration in range(1, repeat + 1):
        runs.append(
            _run_live_case(
                api_url=api_url,
                app_url=app_url,
                email=email,
                password=password,
                supabase_url=supabase_url,
                supabase_service_role_key=supabase_service_role_key,
                ops_token=ops_token,
                prompt=prompt,
                iteration=iteration,
                timeout_seconds=timeout_seconds,
                poll_sleep_seconds=poll_sleep_seconds,
                require_async_job=require_async_job,
                render_api_key=render_api_key,
            )
        )

    report: dict[str, Any] = {
        "schema_version": "argus_render_internet_benchmark/v1",
        "generated_at": started_at.isoformat(),
        "repo_root": str(repo_root),
        "api_url": api_url,
        "app_url": app_url,
        "case": {
            "case_id": "golden_path_aapl_msft",
            "prompt": prompt,
            "repeat": repeat,
            "sequential": True,
        },
        "runs": runs,
        "metrics_unavailable": [
            "api_rss_mb",
            "api_cpu",
            "workflow_peak_rss_mb",
            "workflow_cpu",
        ],
        "caveats": [
            "This benchmark measures the deployed internet path end to end, not local process RSS.",
            "Runs are sequential by default to avoid load-testing the private-alpha free-tier API.",
            "Render service/workflow memory metrics require a separate metrics integration before tier sizing decisions.",
        ],
        "output": {},
    }
    paths = write_outputs(report=report, output_dir=output_dir)
    report["output"] = {key: str(value) for key, value in paths.items()}
    return report


def write_outputs(*, report: dict[str, Any], output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = (
        str(report["generated_at"]).replace(":", "-").replace("+", "-").replace(".", "-")
    )
    json_path = output_dir / f"render-internet-{stamp}.json"
    markdown_path = output_dir / f"render-internet-{stamp}.md"
    latest_json = output_dir / "latest.json"
    latest_markdown = output_dir / "latest.md"

    serialized = json.dumps(report, indent=2, sort_keys=True)
    json_path.write_text(serialized + "\n", encoding="utf-8")
    latest_json.write_text(serialized + "\n", encoding="utf-8")

    markdown = render_markdown_summary(report)
    markdown_path.write_text(markdown, encoding="utf-8")
    latest_markdown.write_text(markdown, encoding="utf-8")
    return {
        "json": json_path,
        "markdown": markdown_path,
        "latest_json": latest_json,
        "latest_markdown": latest_markdown,
    }


def _run_live_case(
    *,
    api_url: str,
    app_url: str,
    email: str,
    password: str,
    supabase_url: str | None,
    supabase_service_role_key: str | None,
    ops_token: str | None,
    prompt: str,
    iteration: int,
    timeout_seconds: float,
    poll_sleep_seconds: float,
    require_async_job: bool,
    render_api_key: str | None,
) -> dict[str, Any]:
    case_started = time.perf_counter()
    timings: dict[str, float] = {}
    status_checks: dict[str, Any] = {}
    with httpx.Client(
        follow_redirects=True,
        timeout=httpx.Timeout(timeout_seconds, connect=20.0),
    ) as client:
        warmup = _warmup(
            client=client,
            api_url=api_url,
            app_url=app_url,
            ops_token=ops_token,
        )
        timings["warmup_total"] = warmup["elapsed_ms"]
        status_checks["warmup"] = warmup

        login = _timed_json_request(
            client,
            "POST",
            f"{api_url}/api/v1/auth/login",
            json_body={"email": email, "password": password},
        )
        timings["login"] = login.elapsed_ms
        status_checks["login_status_code"] = login.status_code

        conversation = _timed_json_request(
            client,
            "POST",
            f"{api_url}/api/v1/conversations",
            json_body={},
        )
        timings["conversation_create"] = conversation.elapsed_ms
        conversation_id = _conversation_id(conversation.body)

        confirmation_body = {
            "conversation_id": conversation_id,
            "message": prompt,
            "language": "en",
        }
        confirmation_stream = _stream_chat(
            client=client,
            url=f"{api_url}/api/v1/chat/stream",
            body=confirmation_body,
            timeout_seconds=timeout_seconds,
        )
        timings["confirmation_stream"] = confirmation_stream["elapsed_ms"]
        confirmation_events = parse_sse_events(confirmation_stream["text"])
        _assert_stream_ok(confirmation_events, label="confirmation")
        action = extract_confirmation_run_action(confirmation_events.events)

        run_stream = _stream_chat(
            client=client,
            url=f"{api_url}/api/v1/chat/stream",
            body={
                "conversation_id": conversation_id,
                "action": action,
                "language": "en",
            },
            timeout_seconds=timeout_seconds,
            headers=_run_action_headers(action),
        )
        timings["run_stream"] = run_stream["elapsed_ms"]
        run_events = parse_sse_events(run_stream["text"])
        _assert_stream_ok(run_events, label="run")
        reference = extract_run_reference(run_events.events)
        if reference.kind != "job" and require_async_job:
            raise RuntimeError(
                f"expected async backtest_job reference, got {reference.kind}:{reference.id}"
            )

        job_result: dict[str, Any] | None = None
        job_id: str | None = None
        run_id: str | None = None
        task_run_id: str | None = None
        if reference.kind == "job":
            job_id = reference.id
            job_result = _poll_backtest_job(
                client=client,
                api_url=api_url,
                job_id=job_id,
                timeout_seconds=timeout_seconds,
                poll_sleep_seconds=poll_sleep_seconds,
            )
            timings["job_poll_until_terminal"] = job_result["elapsed_ms"]
            job_id = job_result["job_id"]
            run_id = job_result["run_id"]
        else:
            run_id = reference.id
            timings["job_poll_until_terminal"] = 0.0

        messages = _timed_json_request(
            client,
            "GET",
            f"{api_url}/api/v1/conversations/{conversation_id}/messages",
        )
        timings["messages_fetch"] = messages.elapsed_ms
        _assert_messages_persisted(messages.body, job_id=job_id)

        supabase_verification = _verify_supabase_rows(
            supabase_url=supabase_url,
            supabase_service_role_key=supabase_service_role_key,
            conversation_id=conversation_id,
            job_id=job_id,
        )
        workflow_timings_ms = _workflow_timings_from_verification(
            supabase_verification
        )
        task_run_id = _task_run_id_from_supabase(supabase_verification)
        task_run = _fetch_render_task_run(
            task_run_id=task_run_id,
            render_api_key=render_api_key,
        )
        render_task_duration = _render_task_duration_ms(task_run)
        if render_task_duration is not None:
            timings["render_task_duration"] = render_task_duration

        timings["total"] = (time.perf_counter() - case_started) * 1000.0
        voice = (job_result or {}).get("voice") or {}
        return {
            "case_id": "golden_path_aapl_msft",
            "iteration": iteration,
            "status": "succeeded",
            "conversation_id": conversation_id,
            "job_id": job_id,
            "run_id": run_id,
            "task_run_id": task_run_id,
            "timings_ms": _rounded_timings(timings),
            "stream_timings_ms": {
                "confirmation": confirmation_stream["timings_ms"],
                "run": run_stream["timings_ms"],
            },
            "workflow_timings_ms": workflow_timings_ms,
            "stream_event_counts": {
                "confirmation": len(confirmation_events.events),
                "run": len(run_events.events),
            },
            "status_checks": status_checks,
            "voice": voice,
            "supabase_verification": supabase_verification,
            "render_task_run": _redacted_render_task_run(task_run),
        }


def _warmup(
    *,
    client: httpx.Client,
    api_url: str,
    app_url: str,
    ops_token: str | None,
) -> dict[str, Any]:
    started = time.perf_counter()
    checks: dict[str, Any] = {}
    health = _timed_json_request(client, "GET", f"{api_url}/health")
    checks["health"] = {"status_code": health.status_code, "elapsed_ms": health.elapsed_ms}
    if ops_token:
        readiness = _timed_json_request(
            client,
            "GET",
            f"{api_url}/internal/readiness?force=true",
            headers={"Authorization": f"Bearer {ops_token}"},
        )
        checks["readiness"] = {
            "status_code": readiness.status_code,
            "elapsed_ms": readiness.elapsed_ms,
        }
    else:
        checks["readiness"] = {"status": "skipped_missing_CUADRAO_OPS_TOKEN"}

    frontend_started = time.perf_counter()
    response = client.get(app_url)
    response.raise_for_status()
    checks["frontend"] = {
        "status_code": response.status_code,
        "elapsed_ms": _elapsed_ms(frontend_started),
    }
    return {"elapsed_ms": _elapsed_ms(started), "checks": checks}


def _timed_json_request(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    json_body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> TimedResponse:
    started = time.perf_counter()
    response = client.request(method, url, json=json_body, headers=headers)
    response.raise_for_status()
    body: Any | None = None
    if response.content:
        body = response.json()
    return TimedResponse(
        elapsed_ms=_elapsed_ms(started),
        status_code=response.status_code,
        body=body,
    )


def _stream_chat(
    *,
    client: httpx.Client,
    url: str,
    body: dict[str, Any],
    timeout_seconds: float,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    chunks: list[str] = []
    timed_chunks: list[tuple[float, str]] = []
    timeout = httpx.Timeout(timeout_seconds, connect=20.0, read=timeout_seconds)
    with client.stream(
        "POST",
        url,
        json=body,
        headers=headers,
        timeout=timeout,
    ) as response:
        response_headers_ms = _elapsed_ms(started)
        response.raise_for_status()
        for chunk in response.iter_text():
            chunks.append(chunk)
            timed_chunks.append((_elapsed_ms(started), chunk))
    elapsed_ms = _elapsed_ms(started)
    return {
        "elapsed_ms": elapsed_ms,
        "text": "".join(chunks),
        "timings_ms": _stream_phase_timings_from_chunks(
            response_headers_ms=response_headers_ms,
            chunks=timed_chunks,
            total_ms=elapsed_ms,
        ),
    }


def _stream_phase_timings_from_chunks(
    *,
    response_headers_ms: float,
    chunks: list[tuple[float, str]],
    total_ms: float,
) -> dict[str, float]:
    timings: dict[str, float] = {"response_headers": response_headers_ms}
    buffer = ""
    first_sse_event_seen = False
    first_token_seen = False
    for elapsed_ms, chunk in chunks:
        if chunk and "first_byte" not in timings:
            timings["first_byte"] = elapsed_ms
        buffer += chunk
        while "\n\n" in buffer:
            raw_frame, buffer = buffer.split("\n\n", 1)
            data_lines = [
                line.removeprefix("data:").strip()
                for line in raw_frame.splitlines()
                if line.startswith("data:")
            ]
            if not data_lines:
                continue
            raw = "\n".join(data_lines).strip()
            if not raw:
                continue
            if not first_sse_event_seen:
                timings["first_sse_event"] = elapsed_ms
                first_sse_event_seen = True
            if first_token_seen or raw == "[DONE]":
                continue
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            event_type = payload.get("type") or payload.get("event")
            if event_type == "token":
                timings["first_token"] = elapsed_ms
                first_token_seen = True
    timings["total"] = total_ms
    return _rounded_timings(timings)


def _poll_backtest_job(
    *,
    client: httpx.Client,
    api_url: str,
    job_id: str,
    timeout_seconds: float,
    poll_sleep_seconds: float,
    require_llm_result_voice: bool = True,
) -> dict[str, Any]:
    started = time.perf_counter()
    deadline = time.perf_counter() + timeout_seconds
    transitions: list[dict[str, Any]] = []
    last_status: str | None = None
    while True:
        response = _timed_json_request(
            client,
            "GET",
            f"{api_url}/api/v1/backtest-jobs/{job_id}",
        )
        payload = response.body
        if not isinstance(payload, dict):
            raise RuntimeError("job status response was not a JSON object")
        job = payload.get("job")
        if not isinstance(job, dict):
            raise RuntimeError("job status response did not include job")
        status = str(job.get("status") or "").strip().lower()
        if status != last_status:
            transitions.append(
                {
                    "status": status,
                    "elapsed_ms": round(_elapsed_ms(started), 3),
                }
            )
            last_status = status
        if status == "succeeded":
            run = payload.get("run")
            if not isinstance(run, dict) or not run.get("id"):
                raise RuntimeError("backtest job succeeded without linked run")
            source = payload.get("result_readout_source")
            fallback_used = payload.get("result_readout_fallback_used")
            if require_llm_result_voice and (
                source != "llm_explain_stage" or fallback_used is not False
            ):
                raise RuntimeError(
                    "backtest job did not preserve LLM result readout voice: "
                    f"source={source!r} fallback_used={fallback_used!r}"
                )
            return {
                "job_id": job_id,
                "run_id": str(run["id"]),
                "elapsed_ms": _elapsed_ms(started),
                "transitions": transitions,
                "voice": {
                    "result_readout_source": source,
                    "result_readout_fallback_used": fallback_used,
                    "result_readout_failure_mode": payload.get(
                        "result_readout_failure_mode"
                    ),
                },
            }
        if status in TERMINAL_JOB_STATUSES:
            raise RuntimeError(
                "backtest job ended unsuccessfully: "
                f"status={status!r} code={job.get('failure_code')!r} "
                f"detail={job.get('failure_detail')!r}"
            )
        if time.perf_counter() >= deadline:
            raise RuntimeError(
                f"backtest job {job_id} did not complete within {timeout_seconds:.1f}s"
            )
        time.sleep(poll_sleep_seconds)


def _verify_supabase_rows(
    *,
    supabase_url: str | None,
    supabase_service_role_key: str | None,
    conversation_id: str,
    job_id: str | None,
) -> dict[str, Any]:
    if not supabase_url or not supabase_service_role_key:
        return {"status": "skipped_missing_supabase_service_role"}
    base_url = supabase_url.rstrip("/")
    headers = {
        "apikey": supabase_service_role_key,
        "Authorization": f"Bearer {supabase_service_role_key}",
    }
    with httpx.Client(timeout=30.0) as client:
        backtest_rows = _supabase_get(
            client,
            base_url,
            headers,
            f"/rest/v1/backtest_runs?select=id&conversation_id=eq.{conversation_id}&limit=1",
        )
        receipt_rows = _supabase_get(
            client,
            base_url,
            headers,
            f"/rest/v1/route_receipts?select=id&conversation_id=eq.{conversation_id}&limit=1",
        )
        job_rows: list[dict[str, Any]] = []
        if job_id:
            job_rows = _supabase_get(
                client,
                base_url,
                headers,
                "/rest/v1/backtest_jobs?"
                "select=id,status,result_run_id,queued_at,started_at,finished_at,execution_metadata"
                f"&id=eq.{job_id}&limit=1",
            )
    if not backtest_rows:
        raise RuntimeError("Supabase verifier did not find backtest_run")
    if not receipt_rows:
        raise RuntimeError("Supabase verifier did not find route_receipts")
    if job_id and not job_rows:
        raise RuntimeError("Supabase verifier did not find backtest_job")
    if job_rows:
        job = job_rows[0]
        if not job.get("result_run_id"):
            raise RuntimeError("Supabase verifier found job without result_run_id")
        metadata = job.get("execution_metadata")
        if not isinstance(metadata, dict):
            raise RuntimeError("Supabase verifier found job without execution_metadata")
        workflow_metadata = metadata.get("workflow_backtest")
        if not isinstance(workflow_metadata, dict):
            raise RuntimeError("Supabase verifier found job without workflow_backtest")
        source = workflow_metadata.get("result_readout_source")
        fallback_used = workflow_metadata.get("result_readout_fallback_used")
        if source != "llm_explain_stage" or fallback_used is not False:
            raise RuntimeError(
                "Supabase verifier found non-LLM result readout voice: "
                f"source={source!r} fallback_used={fallback_used!r}"
            )
    return {
        "status": "verified",
        "backtest_runs_count": len(backtest_rows),
        "route_receipts_count": len(receipt_rows),
        "backtest_jobs_count": len(job_rows),
        "backtest_job": safe_job_summary(job_rows[0]) if job_rows else None,
    }


def _supabase_get(
    client: httpx.Client,
    base_url: str,
    headers: dict[str, str],
    path: str,
) -> list[dict[str, Any]]:
    response = client.get(base_url + path, headers=headers)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise RuntimeError(f"Supabase REST response was not a list for {path}")
    return [row for row in payload if isinstance(row, dict)]


def _fetch_render_task_run(
    *,
    task_run_id: str | None,
    render_api_key: str | None,
) -> dict[str, Any] | None:
    if not task_run_id or not render_api_key:
        return None
    response = httpx.get(
        f"https://api.render.com/v1/task-runs/{task_run_id}",
        headers={
            "Authorization": f"Bearer {render_api_key}",
            "Accept": "application/json",
        },
        timeout=15.0,
    )
    response.raise_for_status()
    payload = response.json()
    return dict(payload) if isinstance(payload, dict) else {"response": payload}


def _confirmation_cards(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    confirmations: list[dict[str, Any]] = []
    for event in events:
        if event.get("type") != "final":
            continue
        payload = event.get("payload", {})
        if not isinstance(payload, dict):
            continue
        for key in ("confirmation", "confirmation_card"):
            value = payload.get(key)
            if isinstance(value, dict):
                confirmations.append(value)
        final_response_payload = payload.get("final_response_payload")
        if isinstance(final_response_payload, dict):
            for key in ("confirmation", "confirmation_card"):
                value = final_response_payload.get(key)
                if isinstance(value, dict):
                    confirmations.append(value)
    return confirmations


def _assert_stream_ok(parsed: ParsedSseEvents, *, label: str) -> None:
    if not parsed.done:
        raise RuntimeError(f"{label} stream did not finish with [DONE]")
    error_events = [event for event in parsed.events if event.get("type") == "error"]
    if error_events:
        raise RuntimeError(f"{label} stream returned error: {error_events[-1]}")
    if not any(event.get("type") == "final" for event in parsed.events):
        raise RuntimeError(f"{label} stream did not include final event")


def _conversation_id(body: Any) -> str:
    if not isinstance(body, dict):
        raise RuntimeError("conversation create response was not an object")
    conversation = body.get("conversation")
    if not isinstance(conversation, dict) or not conversation.get("id"):
        raise RuntimeError("conversation create response did not include conversation.id")
    return str(conversation["id"])


def _assert_messages_persisted(body: Any, *, job_id: str | None) -> None:
    if not isinstance(body, dict):
        raise RuntimeError("messages response was not an object")
    items = body.get("items")
    if not isinstance(items, list):
        raise RuntimeError("messages response did not include items")
    roles = [item.get("role") for item in items if isinstance(item, dict)]
    if roles.count("user") < 1 or roles.count("assistant") < 2:
        raise RuntimeError("conversation did not persist expected user/assistant messages")
    if not job_id:
        return
    for item in items:
        if not isinstance(item, dict):
            continue
        metadata = item.get("metadata") or {}
        if not isinstance(metadata, dict):
            continue
        job = metadata.get("backtest_job")
        if isinstance(job, dict) and job.get("id") == job_id:
            return
    raise RuntimeError("conversation did not persist async backtest_job metadata")


def _task_run_id_from_supabase(verification: dict[str, Any]) -> str | None:
    job = verification.get("backtest_job")
    if not isinstance(job, dict):
        return None
    raw = job.get("task_run_id")
    return str(raw) if raw else None


def safe_job_summary(job: dict[str, Any]) -> dict[str, Any]:
    metadata = job.get("execution_metadata")
    task_run_id = None
    workflow_status = None
    result_source = None
    fallback_used = None
    workflow_timings_ms: dict[str, float] = {}
    if isinstance(metadata, dict):
        workflow_dispatch = metadata.get("workflow_dispatch")
        if isinstance(workflow_dispatch, dict):
            task_run_id = workflow_dispatch.get("task_run_id")
            workflow_status = workflow_dispatch.get("status")
        workflow_backtest = metadata.get("workflow_backtest")
        if isinstance(workflow_backtest, dict):
            task_run_id = task_run_id or workflow_backtest.get("workflow_run_id")
            result_source = workflow_backtest.get("result_readout_source")
            fallback_used = workflow_backtest.get("result_readout_fallback_used")
            workflow_timings_ms = _workflow_timings_ms(workflow_backtest)
    return {
        "id": job.get("id"),
        "status": job.get("status"),
        "result_run_id": job.get("result_run_id"),
        "queued_at": job.get("queued_at"),
        "started_at": job.get("started_at"),
        "finished_at": job.get("finished_at"),
        "task_run_id": task_run_id,
        "workflow_dispatch_status": workflow_status,
        "result_readout_source": result_source,
        "result_readout_fallback_used": fallback_used,
        "timings_ms": _job_status_timings_ms(job),
        "workflow_timings_ms": workflow_timings_ms,
    }


def _stream_timing_rows(
    report: dict[str, Any],
) -> list[tuple[dict[str, Any], str, dict[str, float]]]:
    rows: list[tuple[dict[str, Any], str, dict[str, float]]] = []
    stream_labels = {
        "confirmation": "Confirmation",
        "run": "Run",
    }
    for run in report.get("runs", []):
        if not isinstance(run, dict):
            continue
        timings = run.get("stream_timings_ms")
        if not isinstance(timings, dict):
            continue
        for stream_key, stream_label in stream_labels.items():
            stream_timings = timings.get(stream_key)
            if isinstance(stream_timings, dict) and stream_timings:
                rows.append((run, stream_label, dict(stream_timings)))
    return rows


def _workflow_timing_rows(
    report: dict[str, Any],
) -> list[tuple[dict[str, Any], dict[str, float]]]:
    rows: list[tuple[dict[str, Any], dict[str, float]]] = []
    for run in report.get("runs", []):
        if not isinstance(run, dict):
            continue
        timings = run.get("workflow_timings_ms")
        if not isinstance(timings, dict) or not timings:
            timings = _workflow_timings_from_verification(
                run.get("supabase_verification")
            )
        if timings:
            rows.append((run, timings))
    return rows


def _workflow_timings_from_verification(value: Any) -> dict[str, float]:
    if not isinstance(value, dict):
        return {}
    job = value.get("backtest_job")
    if not isinstance(job, dict):
        return {}
    timings = job.get("workflow_timings_ms")
    return dict(timings) if isinstance(timings, dict) else {}


def _workflow_timings_ms(workflow_backtest: dict[str, Any]) -> dict[str, float]:
    raw = workflow_backtest.get("timings_ms")
    if not isinstance(raw, dict):
        return {}
    timings: dict[str, float] = {}
    for name, elapsed_ms in raw.items():
        if not isinstance(name, str) or isinstance(elapsed_ms, bool):
            continue
        try:
            numeric = float(elapsed_ms)
        except (TypeError, ValueError):
            continue
        if isfinite(numeric) and numeric >= 0.0:
            timings[name] = round(numeric, 3)
    return timings


def _job_status_timings_ms(job: dict[str, Any]) -> dict[str, float]:
    queued_at = _timestamp_value(job.get("queued_at"))
    started_at = _timestamp_value(job.get("started_at"))
    finished_at = _timestamp_value(job.get("finished_at"))
    timings: dict[str, float] = {}
    if queued_at is not None and started_at is not None:
        timings["queued_to_started"] = round(
            max(0.0, (started_at - queued_at) * 1000.0),
            3,
        )
    if started_at is not None and finished_at is not None:
        timings["started_to_finished"] = round(
            max(0.0, (finished_at - started_at) * 1000.0),
            3,
        )
    if queued_at is not None and finished_at is not None:
        timings["queued_to_finished"] = round(
            max(0.0, (finished_at - queued_at) * 1000.0),
            3,
        )
    return timings


def _render_task_duration_ms(task_run: dict[str, Any] | None) -> float | None:
    if not task_run:
        return None
    started_at = _timestamp_value(
        task_run.get("startedAt")
        or task_run.get("started_at")
        or task_run.get("createdAt")
        or task_run.get("created_at")
    )
    finished_at = _timestamp_value(
        task_run.get("finishedAt")
        or task_run.get("finished_at")
        or task_run.get("completedAt")
        or task_run.get("completed_at")
    )
    if started_at is None or finished_at is None:
        return None
    return max(0.0, (finished_at - started_at) * 1000.0)


def _redacted_render_task_run(task_run: dict[str, Any] | None) -> dict[str, Any] | None:
    if not task_run:
        return None
    allowed_keys = {
        "id",
        "status",
        "createdAt",
        "created_at",
        "startedAt",
        "started_at",
        "finishedAt",
        "finished_at",
        "completedAt",
        "completed_at",
    }
    return {key: value for key, value in task_run.items() if key in allowed_keys}


def _timestamp_value(value: Any) -> float | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized).timestamp()
    except ValueError:
        try:
            return datetime.strptime(
                normalized,
                "%Y-%m-%dT%H:%M:%S.%f%z",
            ).timestamp()
        except ValueError:
            return None


def _rounded_timings(timings: dict[str, float]) -> dict[str, float]:
    return {key: round(value, 3) for key, value in sorted(timings.items())}


def _format_seconds(value: Any) -> str:
    if value is None:
        return "n/a"
    try:
        return f"{float(value) / 1000.0:.2f}s"
    except (TypeError, ValueError):
        return "n/a"


def _post_warmup_ms(timings: dict[str, Any]) -> float | None:
    try:
        total = float(timings["total"])
        warmup = float(timings["warmup_total"])
    except (KeyError, TypeError, ValueError):
        return None
    return max(0.0, total - warmup)


def _elapsed_ms(started: float) -> float:
    return (time.perf_counter() - started) * 1000.0


def _env_first(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value and value.strip() and not value.strip().startswith("YOUR_"):
            return value.strip()
    return None


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _release_contract_value(repo_root: Path, name: str) -> str | None:
    """Read one quoted assignment from the canonical release env contract."""
    contract_path = repo_root / ".github" / "argus-env.sh"
    match = re.search(
        rf'^{re.escape(name)}="([^"]+)"\s*$',
        contract_path.read_text(encoding="utf-8"),
        flags=re.MULTILINE,
    )
    if match is None:
        return None
    value = match.group(1).strip()
    return value or None


def _resolved_api_url(repo_root: Path, explicit: str | None) -> str:
    resolved = (
        (explicit.strip() if explicit and explicit.strip() else None)
        or _env_first("ARGUS_CANARY_API_URL", "ARGUS_PRIVATE_LAUNCH_API_URL")
        or _release_contract_value(repo_root, "ARGUS_PRIVATE_LAUNCH_API_URL")
    )
    if not resolved:
        raise SystemExit(
            "API URL required: pass --api-url or set ARGUS_CANARY_API_URL / "
            "ARGUS_PRIVATE_LAUNCH_API_URL, or keep ARGUS_PRIVATE_LAUNCH_API_URL "
            "in .github/argus-env.sh."
        )
    return resolved


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Benchmark the deployed Argus Render internet backtest path."
    )
    parser.add_argument("--api-url", default=None)
    parser.add_argument("--app-url", default=None)
    parser.add_argument("--email", default=None)
    parser.add_argument("--password", default=None)
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--timeout-seconds", type=float, default=420.0)
    parser.add_argument("--poll-sleep-seconds", type=float, default=5.0)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument(
        "--allow-inline-run",
        action="store_true",
        help="Do not fail if the run path returns an immediate backtest_run instead of an async job.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    repo_root = _repo_root()
    load_dotenv(repo_root / ".env", override=False)
    args = _parse_args(argv or sys.argv[1:])
    if args.repeat < 1:
        raise SystemExit("--repeat must be >= 1")

    email = args.email or _env_first("ARGUS_CANARY_EMAIL", "MOCK_USER_EMAIL")
    password = args.password or _env_first(
        "ARGUS_CANARY_PASSWORD",
        "MOCK_USER_PASSWORD",
    )
    if not email:
        raise SystemExit("ARGUS_CANARY_EMAIL or MOCK_USER_EMAIL is required.")
    if not password:
        raise SystemExit("ARGUS_CANARY_PASSWORD or MOCK_USER_PASSWORD is required.")

    report = run_benchmark(
        repo_root=repo_root,
        output_dir=args.output_dir or default_output_dir(repo_root),
        api_url=_resolved_api_url(repo_root, args.api_url),
        app_url=args.app_url
        or _env_first("ARGUS_CANARY_APP_URL", "ARGUS_PRIVATE_LAUNCH_APP_URL")
        or DEFAULT_APP_URL,
        email=email,
        password=password,
        supabase_url=_env_first("ARGUS_CANARY_SUPABASE_URL", "SUPABASE_URL"),
        supabase_service_role_key=_env_first(
            "ARGUS_CANARY_SUPABASE_SERVICE_ROLE_KEY",
            "SUPABASE_SERVICE_ROLE_KEY",
        ),
        ops_token=_env_first("CUADRAO_OPS_TOKEN"),
        prompt=args.prompt,
        repeat=args.repeat,
        timeout_seconds=args.timeout_seconds,
        poll_sleep_seconds=args.poll_sleep_seconds,
        require_async_job=not args.allow_inline_run,
        render_api_key=_env_first("RENDER_API_KEY"),
    )
    print(json.dumps(report["output"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
