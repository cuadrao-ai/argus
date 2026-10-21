"""Staging approval records stay bound to the hosts and users they name."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from tests.test_apply_approved_migrations import _Cursor

from scripts.ops import apply_approved_migrations as applier

_STAGING_APPROVAL = (
    "docs/release-manifests/2026-10-18-staging-security-waitlist-apply.json"
)
_STAGING_SHA = "c940a8b319086bea023bc63b8b6817a87dbffafd"
_STAGING_VERSIONS = ["20261018030000", "20261018030016", "20261018040000"]


def test_the_staging_security_waitlist_record_holds_inside_its_window() -> None:
    text = (Path(__file__).resolve().parents[1] / _STAGING_APPROVAL).read_text()
    approval = applier.parse_hosted_approval(
        text,
        _STAGING_SHA,
        _STAGING_VERSIONS,
        (),
        datetime.fromisoformat("2026-10-19T15:00:00-05:00"),
    )
    assert approval == applier.HostedApproval(
        "staging-apply-2026-10-18",
        "skedzwocnmrhfigiwyzi",
        (
            "db.skedzwocnmrhfigiwyzi.supabase.co",
            "aws-0-us-east-1.pooler.supabase.com",
        ),
        "postgres",
        _STAGING_SHA,
        "b963585771acb2fd0922a3d8cf9d020e60a5dc14786fe4f032f8764d0d49d866",
        datetime.fromisoformat("2026-10-21T03:38:00-05:00"),
    )
    with pytest.raises(applier.ApplyError, match="not valid now"):
        applier.parse_hosted_approval(
            text,
            _STAGING_SHA,
            _STAGING_VERSIONS,
            (),
            datetime.fromisoformat("2026-10-21T03:38:00-05:00"),
        )


_STAGING_APPROVAL_B = (
    "docs/release-manifests/2026-10-18-staging-invites-bank-matching-registry-apply.json"
)
_STAGING_SHA_B = "fb6d969505f364fa08e4eb89e7317619f7de4781"
_STAGING_VERSIONS_B = [
    "20261018040438",
    "20261018180000",
    "20261018190000",
    "20261018210000",
]


def test_the_staging_invites_bank_matching_registry_record_holds_inside_its_window() -> (
    None
):
    text = (Path(__file__).resolve().parents[1] / _STAGING_APPROVAL_B).read_text()
    approval = applier.parse_hosted_approval(
        text,
        _STAGING_SHA_B,
        _STAGING_VERSIONS_B,
        (),
        datetime.fromisoformat("2026-10-19T15:00:00-05:00"),
    )
    assert approval == applier.HostedApproval(
        "staging-apply-2026-10-18-b",
        "skedzwocnmrhfigiwyzi",
        (
            "db.skedzwocnmrhfigiwyzi.supabase.co",
            "aws-0-us-east-1.pooler.supabase.com",
        ),
        "postgres",
        _STAGING_SHA_B,
        "6832fd3b890048119f8e881a108ca02c2b96445731180f208132bb5327b563fc",
        datetime.fromisoformat("2026-10-21T10:56:00-05:00"),
    )
    for versions in (
        [*_STAGING_VERSIONS_B, "20261018220000"],
        [*_STAGING_VERSIONS_B, "20261018220000", "20261018230000"],
        _STAGING_VERSIONS_B[:3],
    ):
        with pytest.raises(applier.ApplyError, match="different list of versions"):
            applier.parse_hosted_approval(
                text,
                _STAGING_SHA_B,
                versions,
                (),
                datetime.fromisoformat("2026-10-19T15:00:00-05:00"),
            )
    with pytest.raises(applier.ApplyError, match="not valid now"):
        applier.parse_hosted_approval(
            text,
            _STAGING_SHA_B,
            _STAGING_VERSIONS_B,
            (),
            datetime.fromisoformat("2026-10-21T10:56:00-05:00"),
        )


_STAGING_APPROVAL_C = (
    "docs/release-manifests/2026-10-18-staging-dgii-export-month-close-apply.json"
)
_STAGING_SHA_C = "789ee2236325f9a2df4a03c49f07a69d49318104"
_STAGING_VERSIONS_C = ["20261018220000", "20261018230000"]


def test_the_staging_dgii_export_month_close_record_holds_inside_its_window() -> None:
    text = (Path(__file__).resolve().parents[1] / _STAGING_APPROVAL_C).read_text()
    approval = applier.parse_hosted_approval(
        text,
        _STAGING_SHA_C,
        _STAGING_VERSIONS_C,
        (),
        datetime.fromisoformat("2026-10-19T15:00:00-05:00"),
    )
    assert approval == applier.HostedApproval(
        "staging-apply-2026-10-18-c",
        "skedzwocnmrhfigiwyzi",
        (
            "db.skedzwocnmrhfigiwyzi.supabase.co",
            "aws-0-us-east-1.pooler.supabase.com",
        ),
        "postgres",
        _STAGING_SHA_C,
        "75ef583cec3d0baf25df6350878f5ad63f514bbe149bd9b1caadad496d629529",
        datetime.fromisoformat("2026-10-21T14:20:00-05:00"),
    )
    for versions in (
        ["20261018210000", *_STAGING_VERSIONS_C],
        _STAGING_VERSIONS_C[:1],
        _STAGING_VERSIONS_C[1:],
    ):
        with pytest.raises(applier.ApplyError, match="different list of versions"):
            applier.parse_hosted_approval(
                text,
                _STAGING_SHA_C,
                versions,
                (),
                datetime.fromisoformat("2026-10-19T15:00:00-05:00"),
            )
    with pytest.raises(applier.ApplyError, match="not valid now"):
        applier.parse_hosted_approval(
            text,
            _STAGING_SHA_C,
            _STAGING_VERSIONS_C,
            (),
            datetime.fromisoformat("2026-10-21T14:20:00-05:00"),
        )


_STAGING_APPROVAL_D = (
    "docs/release-manifests/2026-10-19-staging-bank-import-receipt-address-apply.json"
)
_STAGING_SHA_D = "471d4dd778fe2bf6e70af2327a0e77db74d65e88"
_STAGING_VERSIONS_D = ["20261019020000", "20261019040000"]


def test_the_staging_bank_import_receipt_address_record_holds_inside_its_window() -> None:
    text = (Path(__file__).resolve().parents[1] / _STAGING_APPROVAL_D).read_text()
    approval = _staging_approval(_STAGING_APPROVAL_D, _STAGING_SHA_D, _STAGING_VERSIONS_D)
    expires = datetime.fromisoformat("2026-10-22T13:00:00-05:00")
    assert (approval.id, approval.expires_at) == ("staging-apply-2026-10-19-a", expires)
    for versions in (["20261018230000", *_STAGING_VERSIONS_D], _STAGING_VERSIONS_D[:1]):
        with pytest.raises(applier.ApplyError, match="different list of versions"):
            applier.parse_hosted_approval(
                text, _STAGING_SHA_D, versions, (), _STAGING_NOW
            )
    with pytest.raises(applier.ApplyError, match="not valid now"):
        applier.parse_hosted_approval(
            text, _STAGING_SHA_D, _STAGING_VERSIONS_D, (), expires
        )


_STAGING_APPROVAL_E = (
    "docs/release-manifests/2026-10-19-staging-business-consent-acceptances-apply.json"
)
_STAGING_SHA_E = "43001d9f83306bd245605e676f205fda225b4998"
_STAGING_VERSIONS_E = ["20261019050000"]
_STAGING_APPROVAL_F = (
    "docs/release-manifests/2026-10-19-staging-profile-age-confirmation-apply.json"
)
_STAGING_SHA_F = "d7fdf5a55719582372226617a6ad28310561f085"
_STAGING_VERSIONS_F = ["20261019060000"]


@pytest.mark.parametrize(
    ("path", "sha", "versions", "record_id", "wrong"),
    [
        (_STAGING_APPROVAL_E, _STAGING_SHA_E, _STAGING_VERSIONS_E,
         "staging-apply-2026-10-19-b", ["20261019040000", "20261019050000"]),
        (_STAGING_APPROVAL_F, _STAGING_SHA_F, _STAGING_VERSIONS_F,
         "staging-apply-2026-10-19-c", ["20261019050000", "20261019060000"]),
    ],
)  # fmt: skip
def test_the_staging_consent_and_age_records_hold_inside_their_window(
    path: str, sha: str, versions: list[str], record_id: str, wrong: list[str]
) -> None:
    text = (Path(__file__).resolve().parents[1] / path).read_text()
    approval = _staging_approval(path, sha, versions)
    expires = datetime.fromisoformat("2026-10-22T16:55:00-05:00")
    assert (approval.id, approval.expires_at) == (record_id, expires)
    with pytest.raises(applier.ApplyError, match="different list of versions"):
        applier.parse_hosted_approval(text, sha, wrong, (), _STAGING_NOW)
    other = _STAGING_SHA_F if sha == _STAGING_SHA_E else _STAGING_SHA_E
    with pytest.raises(applier.ApplyError, match="different candidate commit"):
        applier.parse_hosted_approval(text, other, versions, (), _STAGING_NOW)
    with pytest.raises(applier.ApplyError, match="not valid now"):
        applier.parse_hosted_approval(text, sha, versions, (), expires)


_STAGING_APPROVAL_G = (
    "docs/release-manifests/2026-10-20-staging-business-fiscal-profile-apply.json"
)
_STAGING_APPROVAL_H = (
    "docs/release-manifests/2026-10-20-staging-business-due-on-apply.json"
)
_STAGING_SHA_GH = "468de3986c4673ddda2bd94fc19746dff921f818"
_STAGING_VERSIONS_G = ["20261019070000"]
_STAGING_VERSIONS_H = ["20261020120000"]


@pytest.mark.parametrize(
    ("path", "versions", "record_id", "wrong"),
    [
        (_STAGING_APPROVAL_G, _STAGING_VERSIONS_G, "staging-apply-2026-10-20-a",
         ["20261019070000", "20261020120000"]),
        (_STAGING_APPROVAL_H, _STAGING_VERSIONS_H, "staging-apply-2026-10-20-b",
         ["20261019070000", "20261020120000"]),
    ],
)  # fmt: skip
def test_the_staging_fiscal_profile_and_due_on_records_hold_inside_their_window(
    path: str, versions: list[str], record_id: str, wrong: list[str]
) -> None:
    text = (Path(__file__).resolve().parents[1] / path).read_text()
    approval = _staging_approval(path, _STAGING_SHA_GH, versions)
    expires = datetime.fromisoformat("2026-10-23T20:55:00-05:00")
    assert (approval.id, approval.expires_at) == (record_id, expires)
    with pytest.raises(applier.ApplyError, match="different list of versions"):
        applier.parse_hosted_approval(text, _STAGING_SHA_GH, wrong, (), _STAGING_NOW)
    with pytest.raises(applier.ApplyError, match="different candidate commit"):
        applier.parse_hosted_approval(text, _STAGING_SHA_F, versions, (), _STAGING_NOW)
    with pytest.raises(applier.ApplyError, match="not valid now"):
        applier.parse_hosted_approval(text, _STAGING_SHA_GH, versions, (), expires)


_STAGING_REF = "skedzwocnmrhfigiwyzi"
_STAGING_DIRECT = f"db.{_STAGING_REF}.supabase.co"
_STAGING_POOLER = "aws-0-us-east-1.pooler.supabase.com"
_STAGING_OTHER_POOLER = "aws-0-eu-west-1.pooler.supabase.com"
_STAGING_PASSWORD = "fake-password-do-not-echo"
_STAGING_NOW = datetime.fromisoformat("2026-10-20T21:00:00-05:00")
_STAGING_RECORDS = (
    (_STAGING_APPROVAL, _STAGING_SHA, _STAGING_VERSIONS),
    (_STAGING_APPROVAL_B, _STAGING_SHA_B, _STAGING_VERSIONS_B),
    (_STAGING_APPROVAL_C, _STAGING_SHA_C, _STAGING_VERSIONS_C),
    (_STAGING_APPROVAL_D, _STAGING_SHA_D, _STAGING_VERSIONS_D),
    (_STAGING_APPROVAL_E, _STAGING_SHA_E, _STAGING_VERSIONS_E),
    (_STAGING_APPROVAL_F, _STAGING_SHA_F, _STAGING_VERSIONS_F),
    (_STAGING_APPROVAL_G, _STAGING_SHA_GH, _STAGING_VERSIONS_G),
    (_STAGING_APPROVAL_H, _STAGING_SHA_GH, _STAGING_VERSIONS_H),
)


def _staging_approval(path: str, sha: str, versions: list[str]) -> applier.HostedApproval:
    text = (Path(__file__).resolve().parents[1] / path).read_text()
    return applier.parse_hosted_approval(text, sha, versions, (), _STAGING_NOW)


def _staging_url(
    user: str, host: str, port: int = 5432, password: str = _STAGING_PASSWORD
) -> str:
    return f"postgresql://{user}:{password}@{host}:{port}/postgres"


@pytest.mark.parametrize(("path", "sha", "versions"), _STAGING_RECORDS)
def test_each_staging_record_accepts_the_session_pooler(
    path: str, sha: str, versions: list[str]
) -> None:
    applier.check_target(
        _staging_url(f"postgres.{_STAGING_REF}", _STAGING_POOLER),
        [_STAGING_DIRECT, _STAGING_POOLER],
        ["postgres"],
        environ={},
        hosted=_staging_approval(path, sha, versions),
    )


@pytest.mark.parametrize(("path", "sha", "versions"), _STAGING_RECORDS)
def test_each_staging_record_still_accepts_the_direct_host(
    path: str, sha: str, versions: list[str]
) -> None:
    hosted = _staging_approval(path, sha, versions)
    url = _staging_url("postgres", _STAGING_DIRECT)
    applier.check_target(url, [_STAGING_DIRECT], ["postgres"], environ={}, hosted=hosted)
    applier.check_target(
        url, [_STAGING_DIRECT, _STAGING_POOLER], ["postgres"], environ={}, hosted=hosted
    )


@pytest.mark.parametrize(
    ("user", "port", "host", "pattern"),
    [
        ("postgres.zzzzzzzzzzzzzzzzzzzz", 5432, _STAGING_POOLER, "project ref"),
        (f"postgres.{_STAGING_REF}", 6543, _STAGING_POOLER, "port 5432"),
        (f"postgres.{_STAGING_REF}", 5432, _STAGING_OTHER_POOLER, "not named"),
    ],
)
@pytest.mark.parametrize(("path", "sha", "versions"), _STAGING_RECORDS)
def test_a_staging_pooler_url_is_refused_for_the_wrong_ref_port_or_host(
    user: str,
    port: int,
    host: str,
    pattern: str,
    path: str,
    sha: str,
    versions: list[str],
) -> None:
    with pytest.raises(applier.ApplyError, match=pattern) as caught:
        applier.check_target(
            _staging_url(user, host, port),
            [_STAGING_DIRECT, _STAGING_POOLER],
            ["postgres"],
            environ={},
            hosted=_staging_approval(path, sha, versions),
        )
    leaked = _STAGING_PASSWORD in str(caught.value)
    assert not leaked


def test_a_quoted_pooler_url_is_accepted_for_either_staging_record(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    for path, sha, versions in _STAGING_RECORDS:
        for quote in ("'", '"'):
            password = "fake'password" if quote == "'" else _STAGING_PASSWORD
            bare = _staging_url(
                f"postgres.{_STAGING_REF}", _STAGING_POOLER, password=password
            )
            _assert_quoted_dry_run(
                monkeypatch,
                tmp_path,
                capsys,
                path,
                sha,
                versions,
                quote + bare + quote,
                password,
            )


def test_mismatched_quotes_around_the_url_are_left_alone(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path, sha, versions = _STAGING_RECORDS[0]
    bare = _staging_url(f"postgres.{_STAGING_REF}", _STAGING_POOLER)
    monkeypatch.setattr("psycopg.connect", lambda *_a, **_k: pytest.fail("connected"))
    with pytest.raises(applier.ApplyError) as caught:
        _quoted_main(monkeypatch, tmp_path, path, sha, versions, "'" + bare + '"')
    leaked = _STAGING_PASSWORD in str(caught.value)
    assert not leaked


def _refusal_chain(error: BaseException) -> str:
    pieces: list[str] = []
    pending: list[BaseException | None] = [error]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if current is None or id(current) in seen:
            continue
        seen.add(id(current))
        pieces.append(str(current))
        pending.append(current.__cause__)
        pending.append(current.__context__)
    return "\n".join(pieces)


def _require_quiet_refusal(error: Exception | None, out: str, err: str) -> None:
    if not isinstance(error, applier.ApplyError):
        raise AssertionError("the refusal was not an ApplyError")
    visible = "\n".join((out, err, _refusal_chain(error)))
    if _STAGING_PASSWORD in visible:
        raise AssertionError("the database password appeared in the refusal")


def _connect_must_not_run(*_args: object, **_kwargs: object) -> None:
    raise RuntimeError("connected")


def _refuse_quoted_url(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    url: str,
    connect: object,
) -> None:
    path, sha, versions = _STAGING_RECORDS[0]
    monkeypatch.setattr("psycopg.connect", connect)
    caught: Exception | None = None
    try:
        _quoted_main(monkeypatch, tmp_path, path, sha, versions, url)
    except Exception as error:
        caught = error
    captured = capsys.readouterr()
    _require_quiet_refusal(caught, captured.out, captured.err)


def test_a_quoted_url_with_a_leading_space_does_not_echo_the_password(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bare = _staging_url(f"postgres.{_STAGING_REF}", _STAGING_POOLER)
    _refuse_quoted_url(
        monkeypatch,
        tmp_path,
        capsys,
        '"' + " " + bare + '"',
        _connect_must_not_run,
    )


def test_a_control_character_in_the_password_does_not_echo_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bare = _staging_url(
        f"postgres.{_STAGING_REF}",
        _STAGING_POOLER,
        password=_STAGING_PASSWORD + "\x07",
    )
    _refuse_quoted_url(
        monkeypatch,
        tmp_path,
        capsys,
        '"' + bare + '"',
        _connect_must_not_run,
    )


def test_a_fullwidth_at_in_the_password_does_not_echo_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bare = _staging_url(
        f"postgres.{_STAGING_REF}",
        _STAGING_POOLER,
        password=_STAGING_PASSWORD + "\uff20",
    )
    _refuse_quoted_url(
        monkeypatch,
        tmp_path,
        capsys,
        '"' + bare + '"',
        _connect_must_not_run,
    )


def test_a_connect_failure_does_not_echo_the_password(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    import psycopg

    bare = _staging_url(f"postgres.{_STAGING_REF}", _STAGING_POOLER)

    def connect(*_args: object, **_kwargs: object) -> None:
        raise psycopg.OperationalError("connect failed " + _STAGING_PASSWORD)

    _refuse_quoted_url(monkeypatch, tmp_path, capsys, '"' + bare + '"', connect)


@pytest.mark.parametrize(("outer", "inner"), [('"', "'"), ('"', '"')])
def test_a_second_quote_pair_around_a_valid_url_is_refused(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    outer: str,
    inner: str,
) -> None:
    bare = _staging_url(f"postgres.{_STAGING_REF}", _STAGING_POOLER)
    _refuse_quoted_url(
        monkeypatch,
        tmp_path,
        capsys,
        outer + inner + bare + inner + outer,
        _connect_must_not_run,
    )


def test_another_project_ref_in_the_pooler_username_is_refused() -> None:
    other_ref = "p9k3m7n2q8r4t6v1x5z0"
    assert other_ref != _STAGING_REF
    path, sha, versions = _STAGING_RECORDS[0]
    with pytest.raises(applier.ApplyError, match="project ref") as caught:
        applier.check_target(
            _staging_url(f"postgres.{other_ref}", _STAGING_POOLER),
            [_STAGING_DIRECT, _STAGING_POOLER],
            ["postgres"],
            environ={},
            hosted=_staging_approval(path, sha, versions),
        )
    if _STAGING_PASSWORD in str(caught.value):
        raise AssertionError("the database password appeared in the refusal")


def _assert_quoted_dry_run(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    path: str,
    sha: str,
    versions: list[str],
    url: str,
    password: str,
) -> None:
    seen: dict[str, object] = {}

    def connect(target: str, **options: object) -> _PlanServer:
        seen["wrapped"] = target[:1] in "'\"" or target[-1:] in "'\""
        seen["inner"] = password in target
        seen["sslmode"] = options.get("sslmode")
        return _PlanServer(["20261018000000"], _STAGING_POOLER)

    monkeypatch.setattr("psycopg.connect", connect)
    assert _quoted_main(monkeypatch, tmp_path, path, sha, versions, url) == 0
    captured = capsys.readouterr()
    leaked = password in captured.out or password in captured.err
    assert seen == {"wrapped": False, "inner": True, "sslmode": "verify-full"}
    assert "dry run" in captured.out
    assert not leaked


def _quoted_main(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    path: str,
    sha: str,
    versions: list[str],
    url: str,
) -> int:
    from tests.test_apply_approved_migrations import _migration

    text = (Path(__file__).resolve().parents[1] / path).read_text()
    monkeypatch.setattr(applier, "read_committed_record", lambda *_args: text)
    monkeypatch.setattr(
        applier,
        "datetime",
        SimpleNamespace(
            now=lambda _tz: _STAGING_NOW, fromisoformat=datetime.fromisoformat
        ),
    )
    approved = tmp_path / "approved.json"
    approved.write_text(json.dumps(versions))
    cert = tmp_path / "ca.pem"
    cert.write_text("fixture")
    monkeypatch.setenv("ARGUS_APPLY_DATABASE_URL", url)
    for name in applier._REFUSED_ENVIRONMENT:
        monkeypatch.delenv(name, raising=False)
    head = "20261018000000"
    candidates = [
        _migration(head, "ledger_head"),
        *[_migration(version, "step") for version in versions],
    ]
    monkeypatch.setattr(applier.gate, "read_candidate_migrations", lambda *_a: candidates)
    return applier.main(
        [
            "--candidate-sha", sha, "--approved-file", str(approved),
            "--allow-host", _STAGING_DIRECT, "--allow-host", _STAGING_POOLER,
            "--allow-database", "postgres", "--hosted-approval", path,
            "--ssl-root-cert", str(cert),
        ]
    )  # fmt: skip


class _PlanServer:
    def __init__(self, ledger: list[str], host: str) -> None:
        self.ledger = ledger
        self.info = SimpleNamespace(
            host=host,
            hostaddr="203.0.113.10",
            port=5432,
            user=f"postgres.{_STAGING_REF}",
        )

    def __enter__(self) -> _PlanServer:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, sql: str, params: object = None) -> _Cursor:
        from tests.test_apply_approved_migrations import _Cursor

        if "current_database" in sql:
            return _Cursor([("postgres",)])
        if "pg_try_advisory_lock" in sql:
            return _Cursor([(True,)])
        if "schema_migrations order by" in sql:
            return _Cursor([(version,) for version in self.ledger])
        return _Cursor([])
