import json
from uuid import uuid4

import httpx
import pytest
from argus.domain.account_deletion.service import (
    AccountDeletionIncomplete,
    subject_hash,
)
from argus.observability.posthog_deletion import PostHogEventDeletion

from tests.household.financial_fixtures import DSN
from tests.household.financial_fixtures import lane as lane
from tests.test_account_deletion_apple_admission_postgres import (
    apple as apple,  # noqa: F401
)
from tests.test_account_deletion_apple_admission_postgres import (
    capture,
    link,
)
from tests.test_account_deletion_fk_census_postgres import (
    _invite_code_secret,  # noqa: F401
)
from tests.test_account_deletion_postgres import (
    SqlAuthAdmin,
    _locked,
    _run,
    _run_id,
    _service,
    world,  # noqa: F401
)

pytestmark = pytest.mark.skipif(not DSN, reason="Disposable PostgreSQL required")


def test_relaunch_polls_saved_request_and_only_then_deletes_auth(lane, world):  # noqa: F811
    a = world["a"]
    request_id = str(uuid4())
    submissions = []

    def submit(request):
        submissions.append(json.loads(request.content))
        body = {
            "id": request_id,
            "submission_id": submissions[-1]["submission_id"],
            "status": "pending",
            "count": None,
        }
        return httpx.Response(201, json=body)

    admin = SqlAuthAdmin()
    adapter = PostHogEventDeletion(
        "https://us.posthog.com", "1", "synthetic", transport=httpx.MockTransport(submit)
    )
    with pytest.raises(AccountDeletionIncomplete) as raised:
        _service(lane, admin, analytics=adapter, allow_fake=False).delete_account(
            user_id=a
        )
    world["placeholders"] += admin.created
    assert raised.value.pending == ["analytics"]
    assert admin.deleted == []
    assert _locked(a) == (True, True)
    run_id = _run_id(a)
    assert submissions[0]["submission_id"] == run_id
    evidence = _run(run_id)[4]["analytics_evidence"]
    assert evidence["request_id"] == request_id
    assert evidence["outcome"] == "pending"
    assert "distinct_id" not in evidence and "query" not in evidence
    polls = []

    def poll(request):
        polls.append(request)
        return httpx.Response(
            200,
            json={
                "id": request_id,
                "submission_id": run_id,
                "status": "completed",
                "count": 7,
            },
        )

    restarted = PostHogEventDeletion(
        "https://us.posthog.com", "1", "synthetic", transport=httpx.MockTransport(poll)
    )
    assert (
        _service(lane, SqlAuthAdmin(), analytics=restarted, allow_fake=False)
        .delete_account(user_id=a)
        .status
        == "done"
    )
    assert len(polls) == 1 and polls[0].method == "GET"
    final = _run(run_id)
    assert final[0] == "done" and final[1] is None and final[2] is None
    assert final[4]["analytics_evidence"]["selected_event_count"] == 7


def test_alpha_denial_is_durable_operator_needed_and_retryable(lane, world):  # noqa: F811
    a, admin = world["a"], SqlAuthAdmin()
    adapter = PostHogEventDeletion(
        "https://us.posthog.com",
        "1",
        "synthetic",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(403, json={"detail": "synthetic private detail"})
        ),
    )
    for _ in range(2):
        with pytest.raises(AccountDeletionIncomplete):
            _service(lane, admin, analytics=adapter, allow_fake=False).delete_account(
                user_id=a
            )
    world["placeholders"] += admin.created
    steps = _run(_run_id(a))[4]
    assert steps["analytics"] == "operator_needed"
    assert steps["analytics_evidence"]["http_status"] == 403
    assert steps["last_error"]["analytics"] == "analytics_delete_operator_needed"
    assert admin.deleted == [] and _locked(a) == (True, True)
    assert "private detail" not in json.dumps(steps)

    assert _service(lane, SqlAuthAdmin()).delete_account(user_id=a).status == "done"


@pytest.mark.parametrize("lost_response", [False, True])
def test_apple_admission_and_receipt_survive_analytics_retry(
    lane, world, apple, lost_response  # noqa: F811
):
    user, admin = world["a"], SqlAuthAdmin()
    request_id = str(uuid4())
    submissions = []

    def submit(request):
        submissions.append(json.loads(request.content))
        if lost_response and len(submissions) == 1:
            raise httpx.ReadTimeout("synthetic lost response", request=request)
        return httpx.Response(
            201,
            json={
                "id": request_id,
                "submission_id": submissions[-1]["submission_id"],
                "status": "pending",
            },
        )

    adapter = PostHogEventDeletion(
        "https://us.posthog.com", "1", "synthetic", transport=httpx.MockTransport(submit)
    )
    service = _service(
        lane, admin, analytics=adapter, apple=apple.service, allow_fake=False
    )
    link(user)
    with pytest.raises(Exception) as denied:
        service.delete_account(user_id=user)
    assert denied.value.code == "apple_reauthorization_required"
    assert submissions == admin.locked == admin.created == admin.deleted == []
    assert service._revoker.calls == apple.fake.calls == []
    assert _locked(user) == (False, False)

    capture(apple, user)
    with pytest.raises(AccountDeletionIncomplete) as first:
        service.delete_account(user_id=user)
    world["placeholders"] += admin.created
    assert first.value.pending == ["analytics"]
    run_id = _run_id(user)
    assert _run(run_id)[4]["apple_revoke"] == "revoked"
    assert apple.service.repository.get(user_id=user) is None
    assert _locked(user) == (True, True) and admin.deleted == []
    apple_calls = len(apple.fake.calls)
    submission_calls = 2 if lost_response else 1
    assert len(submissions) == submission_calls

    claim = service._claim(user, subject_hash(user))
    with pytest.raises(AccountDeletionIncomplete, match="in_progress"):
        service.delete_account(user_id=user)
    assert len(submissions) == submission_calls and len(apple.fake.calls) == apple_calls
    service._release(claim["id"], claim["claim"])

    if lost_response:
        assert submissions[0] == submissions[1]
        assert _run(run_id)[4]["analytics_evidence"]["request_id"] == request_id

    polls = []

    def completed(request):
        polls.append(request)
        return httpx.Response(
            200,
            json={"id": request_id, "submission_id": run_id, "status": "completed"},
        )

    restarted = PostHogEventDeletion(
        "https://us.posthog.com",
        "1",
        "synthetic",
        transport=httpx.MockTransport(completed),
    )
    assert (
        _service(lane, admin, analytics=restarted, apple=apple.service, allow_fake=False)
        .delete_account(user_id=user)
        .status
        == "done"
    )
    assert len(polls) == 1 and polls[0].method == "GET"
    assert len(apple.fake.calls) == apple_calls
    assert _run(run_id)[4]["apple_revoke"] == "revoked"
    assert admin.deleted == [user]
