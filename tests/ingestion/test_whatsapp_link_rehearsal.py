import json
import secrets
import sys
from pathlib import Path

import httpx
import pytest

from scripts.qa import jose_demo_rehearsal as demo


@pytest.mark.parametrize(
    ("fresh_owner", "creation_status", "mode", "cases", "dry_run", "should_set_tax_id"),
    [
        pytest.param(True, 201, "rehearse", ["1"], False, True, id="new-business"),
        pytest.param(True, 200, "rehearse", ["1"], False, False, id="create-replayed"),
        pytest.param(False, 201, "rehearse", ["1"], False, False, id="existing-owner"),
        pytest.param(
            False, None, "rehearse", ["1"], False, False, id="existing-business"
        ),
        pytest.param(True, 201, "rehearse", ["1"], True, False, id="dry-run"),
        pytest.param(True, 201, "seed", ["1"], False, False, id="seed"),
        pytest.param(True, 201, "rehearse", ["2"], False, False, id="other-case"),
    ],
)
def test_local_rehearsal_whatsapp_link(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fresh_owner: bool,
    creation_status: int | None,
    mode: str,
    cases: list[str],
    dry_run: bool,
    should_set_tax_id: bool,
) -> None:
    token = secrets.token_hex(32)
    code = "CUADRAO TESTCODE"
    linked = False
    has_space = creation_status is None
    space = {
        "space_id": "synthetic-space",
        "name": "Ensayo José Demo",
        "grant_id": "synthetic-grant",
    }
    tax_id_changes = []
    languages = []

    def transport(request: httpx.Request) -> httpx.Response:
        nonlocal linked, has_space
        path = request.url.path
        if path == "/health":
            return httpx.Response(200, json={"git_sha": "synthetic"})
        if path == "/auth/v1/token":
            return httpx.Response(200, json={"access_token": "synthetic"})
        if path == "/api/v1/business/spaces":
            return httpx.Response(200, json={"spaces": [space] if has_space else []})
        if path == "/api/v1/business/space":
            assert creation_status and not has_space
            has_space = True
            return httpx.Response(
                creation_status, json={"id": space["space_id"], "name": space["name"]}
            )
        if path == "/api/v1/business/fiscal-profile" and request.method == "PATCH":
            assert request.headers["X-Business-Grant"] == space["grant_id"]
            tax_id_changes.append(json.loads(request.content))
            return httpx.Response(200, json={})
        if path == "/api/v1/whatsapp/link":
            languages.append(request.url.params.get("language"))
            return httpx.Response(
                200,
                json={
                    "linked": linked,
                    "disclosure": "Aviso de prueba",
                    "disclosure_token": token,
                },
            )
        if path == "/api/v1/whatsapp/link-codes":
            if not tax_id_changes:
                return httpx.Response(409, json={"code": "whatsapp_setup_required"})
            if json.loads(request.content) != {
                "language": "es-419",
                "disclosure_token": token,
            }:
                return httpx.Response(422, json={"code": "invalid_request"})
            return httpx.Response(201, json={"message_text": code})
        if path == "/api/v1/webhooks/whatsapp":
            payload = json.loads(request.content)["entry"][0]["changes"][0]["value"]
            assert payload["messages"][0]["text"]["body"] == code
            linked = True
            return httpx.Response(200, json={})
        if path == "/api/v1/business/receipts":
            raise demo.Untested("Document intake is outside this link rehearsal test")
        raise AssertionError(path)

    env = {
        "SUPABASE_URL": "http://localhost",
        "SUPABASE_ANON_KEY": "synthetic",
        "CUADRAO_WHATSAPP_APP_SECRET": "synthetic",
        "CUADRAO_WHATSAPP_NUMBER_ID": "123",
    }
    monkeypatch.setattr(demo, "load_env_file", lambda _: env)
    monkeypatch.setattr(
        demo,
        "local_owner",
        lambda *_: ("owner@rehearsal.local", "synthetic", fresh_owner),
    )
    monkeypatch.setattr(demo, "pack_files", lambda _: {})
    # Isolate phone setup from accounting, media reads, and the other cases.
    monkeypatch.setattr(demo.Rehearsal, "setup", lambda _: None)
    monkeypatch.setattr(demo.Rehearsal, "case2", lambda _: None)
    monkeypatch.setattr(demo.Rehearsal, "plan", lambda _: {})
    monkeypatch.setattr(demo.Seeder, "run", lambda _: {})
    argv = [
        "jose_demo_rehearsal.py",
        "run",
        "--target",
        "local",
        "--mode",
        mode,
        "--api",
        "http://localhost",
        "--web",
        "http://localhost",
        "--env-file",
        "synthetic",
        "--evidence",
        str(tmp_path),
        "--expect-business",
        space["space_id"],
        "--no-screens",
        "--cases",
        *cases,
    ]
    if dry_run:
        argv.append("--dry-run")
    monkeypatch.setattr(sys, "argv", argv)
    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        monkeypatch.setattr(httpx, "Client", lambda **_: client)
        demo.main()

    assert len(tax_id_changes) == int(should_set_tax_id)
    if mode == "rehearse" and not dry_run and "1" in cases:
        step = (tmp_path / "steps/1-phone-linked.json").read_text()
        assert token not in step
        result = json.loads(step)
        if should_set_tax_id:
            (change,) = tax_id_changes
            assert change["previous_tax_id"] is None
            assert change["previous_name"] == change["name"] == space["name"]
            assert change["tax_id"]["type"] == "rnc"
            assert (
                len(change["tax_id"]["value"]) == 9
                and change["tax_id"]["value"].isdigit()
            )
            assert result["outcome"] == "PASS", result["observed"]
            assert result["observed"]["disclosure"] == "Aviso de prueba"
            assert languages[0] == "es-419"
            assert linked
        else:
            assert result["outcome"] == "FAIL"
            assert "whatsapp_setup_required" in result["observed"]["failure"]
