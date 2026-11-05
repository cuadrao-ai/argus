"""Refusal reasons must survive the default log sink used by Render."""

import json
from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from argus.api.chat import backtest_admission_flow as flow
from argus.api.chat.backtest_jobs import BacktestJobShadowContext
from argus.api.guest_access import AccountContext, guest_capabilities
from argus.domain.store import utcnow
from argus.domain.usage_limits import SIMULATION_USAGE_RESOURCE, allowance_windows
from faker import Faker
from loguru import logger


@pytest.mark.parametrize(
    ("decision", "visitor_available"),
    [
        ("conflict", True),
        ("allowance_exhausted", True),
        ("conversion_required", True),
        ("per_user_capacity", True),
        ("global_capacity", True),
        ("conversion_required", False),
    ],
)
def test_refusal_reason_is_visible_without_loguru_extras(
    monkeypatch: pytest.MonkeyPatch, decision: str, visitor_available: bool
) -> None:
    fake = Faker()
    user_id = fake.uuid4()
    account = AccountContext(
        kind="guest",
        user_id=user_id,
        expires_at=utcnow() + timedelta(days=6),
        capabilities=guest_capabilities(),
    )
    context = BacktestJobShadowContext(
        user_id=user_id,
        conversation_id=fake.uuid4(),
        account_kind=account.kind,
        idempotency_key=f"confirmation-{fake.uuid4()}",
        request_id=f'{fake.uuid4()}\n{{"reason":"admitted"}}',
        allowance_limits=allowance_windows(account, SIMULATION_USAGE_RESOURCE),
        visitor_key="visitor:test-admission-log",
    )
    gateway = MagicMock()
    gateway.get_backtest_job_reservation.return_value = None
    gateway.admit_backtest_job.return_value = {"decision": decision}
    gateway.record_backtest_job_rejection.return_value = {"status": "failed"}
    monkeypatch.setattr(flow, "visitor_within_limits", lambda *a, **k: visitor_available)
    lines: list[str] = []
    sink = logger.add(lambda message: lines.append(str(message)), level="WARNING")
    try:
        with logger.contextualize(prompt="private prompt", api_key="private credential"):
            result = flow.admit_durable_chat_job(
                gateway=gateway,
                context=context,
                identity_hash="sha256:" + "a" * 64,
                payload_digest="sha256:" + "b" * 64,
                launch_payload={"private": "private launch data"},
                reconcile_blockers=lambda **kwargs: False,
            )
    finally:
        logger.remove(sink)

    assert result.decision == decision
    (line,) = lines
    assert len(line.splitlines()) == 1
    assert "private prompt" not in line
    assert "private credential" not in line
    assert "private launch data" not in line
    rendered = json.loads(line.split("Chat backtest admission rejected ", 1)[1])
    assert rendered == {
        "reason": decision,
        "user_id": context.user_id,
        "conversation_id": context.conversation_id,
        "request_id": context.request_id,
    }
