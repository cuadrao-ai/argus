import hashlib
import io
import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4
from zipfile import ZipFile

import pytest
from argus.domain.business.authority import ActionError
from argus.domain.business.contracts.actions import (
    ApproveExpense,
    ApproveIncome,
    ApproveRefund,
    CaptureNote,
    ReviewDraft,
)
from argus.domain.business.contracts.authority import TrustedActor
from argus.domain.business.contracts.dgii import FiscalReview
from argus.domain.business.contracts.facts import BusinessFactPatch
from argus.domain.business.export import ExportPeriod, export_package
from argus.domain.business.fiscal_profile import (
    FiscalProfileChange,
    read_profile,
    set_profile,
)
from argus.domain.ingestion.documents.objects import InMemorySourceObjects
from argus.domain.recording.repository import NewAccount

from tests import test_business_actions_postgres as shared

users = shared.users
shared_actions = shared.actions
pytestmark = [shared.pytestmark, pytest.mark.owner_acts]
FIXTURES = Path(__file__).parent / "dgii/fixtures"
INPUTS = json.loads((FIXTURES / "practice-inputs.json").read_text())["records"]
ORACLE = {
    row["id"]: row
    for row in json.loads((FIXTURES / "practice-oracle.json").read_text())["records"]
}


@pytest.fixture
def actions(shared_actions):
    from argus.domain.business.spaces import PostgresSpaceStore

    service, context, grant = shared_actions
    PostgresSpaceStore(service.authority.pool).rename(context.owner_id, "PRÁCTICA José")
    yield service, context, grant


PRACTICE_NAME = "PRÁCTICA José"


def filer_change(
    value: str | None,
    previous: str | None = None,
    *,
    name: str = PRACTICE_NAME,
    previous_name: str = PRACTICE_NAME,
):
    def tax(digits: str | None):
        if digits is None:
            return None
        return {"type": "cedula" if len(digits) == 11 else "rnc", "value": digits}

    return FiscalProfileChange(
        name=name,
        previous_name=previous_name,
        tax_id=tax(value),
        previous_tax_id=tax(previous),
    )


def cash_account(service, context):
    return service.imports.money.repository.create(
        user_id=context.owner_id,
        idempotency_key=str(uuid4()),
        identity_hash=uuid4().hex,
        account=NewAccount(
            type="cash",
            currency="DOP",
            nickname="PRÁCTICA caja",
            ownership_share_bps=10000,
        ),
        opening=shared.shared._opening(
            1000000, datetime(2026, 9, 1, 12, tzinfo=timezone.utc)
        ),
        scope=context.scope,
    ).stored.account.id


def reviewed(service, context, account, index=0, purchase=None, override=None):
    item = INPUTS[index]
    data = ORACLE[item["record_id"]]
    value = json.loads(json.dumps(item["input"]))
    if purchase:
        value["declaration"]["purchase_activity_id"] = str(purchase)
    if override:
        value["fiscal"].update(override)
    capture = service.capture(
        context,
        CaptureNote(
            text=f"PRÁCTICA {item['record_id']} {data['date']} {data['gross']} DOP"
        ),
        str(uuid4()),
    )
    kind = (
        "refund"
        if purchase
        else "expense"
        if value["declaration"]["form"] == "606"
        else "income"
    )
    facts = BusinessFactPatch.model_validate(
        {
            name: {"state": "known", "value": value}
            for name, value in {
                "kind": kind,
                "amount": data["gross"],
                "currency": "DOP",
                "occurred_on": data["date"],
                "counterparty": f"PRÁCTICA {item['record_id']}",
                "funding": {"kind": "business_account", "account_id": str(account)},
                "business_share": {"kind": "all"},
                "receipt_state": "fiscal_receipt",
            }.items()
        }
    )
    result = service.review(
        context,
        capture.draft_id,
        ReviewDraft(
            version=capture.version, facts=facts, dgii=FiscalReview.model_validate(value)
        ),
        str(uuid4()),
    )
    assert result.outcome == "applied", result
    return result.draft_id, result.version, kind


def approve(service, context, draft):
    identifier, version, kind = draft
    request = {
        "expense": ApproveExpense(version=version, action="record_expense"),
        "income": ApproveIncome(version=version, action="record_income"),
        "refund": ApproveRefund(version=version, action="record_refund"),
    }[kind]
    return {
        "expense": service.approve,
        "income": service.approve_income,
        "refund": service.approve_refund,
    }[kind](context, identifier, request, str(uuid4()))


def test_practice_human_capture_revision_approval_and_actual_export(actions):
    service, context, _ = actions
    account = cash_account(service, context)
    set_profile(
        service.authority,
        context,
        filer_change("199990013"),
        "rnc",
    )
    first = None
    drafts = []
    for index in range(6):
        draft = reviewed(service, context, account, index, first if index == 3 else None)
        outcome = approve(service, context, draft)
        assert outcome.outcome == "applied", outcome
        if index == 0:
            first = outcome.activity_id
        drafts.append(draft)
    blob = export_package(
        service.authority,
        context,
        ExportPeriod(date(2026, 9, 1), date(2026, 9, 30)),
        InMemorySourceObjects(),
    )
    with ZipFile(io.BytesIO(blob)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["dgii"]["issues"] == []
        assert manifest["dgii"]["totals_dop"]["itbis_por_adelantar"] == "252.00"
        assert manifest["dgii"]["totals_dop"]["itbis_facturado"] == "450.00"
        assert len(manifest["records"]) == 6
        assert (
            hashlib.sha256(
                archive.read("dgii/DGII_F_606_199990013_202609.TXT")
            ).hexdigest()
            == "729e044ba0a1de65c2dbb46617c38617f25697e3e5e42dc4ed23f2fd4b3e01a5"
        )
        assert (
            hashlib.sha256(
                archive.read("dgii/DGII_F_607_199990013_202609.TXT")
            ).hexdigest()
            == "73b5366cb83900e54b48eb4573c6bc29fb3115b2421985d67981479ced474d09"
        )
        output = os.getenv("CUADRAO_DGII_FIXTURE_OUTPUT")
        if output:
            root = Path(output)
            root.mkdir(parents=True, exist_ok=True)
            (root / "PRÁCTICA-José-local-export.zip").write_bytes(blob)
            for name in archive.namelist():
                if name.startswith("dgii/"):
                    (root / Path(name).name).write_bytes(archive.read(name))
    for draft, _, _ in drafts:
        dossier = service.dossier(context, draft)
        assert dossier.dgii is not None
        assert dossier.history[-1].after_dgii is not None
        assert dossier.history[-1].actor.actor_id == context.actor.actor_id
        assert dossier.approval_result.approved_revision == dossier.history[-1].version


@pytest.mark.parametrize("sale,buyer", [(False, None), (True, "199990048"), (True, None)])
def test_fiscal_duplicate_approvals_create_one_money_activity(actions, sale, buyer):
    service, context, _ = actions
    account = cash_account(service, context)
    index = 4 if sale else 0
    first = reviewed(service, context, account, index)
    second = reviewed(
        service, context, account, index, override={"rnc": buyer} if sale else None
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(lambda draft: approve(service, context, draft), [first, second])
        )
    assert sorted(result.outcome for result in results) == ["applied", "invalid_input"]
    assert (
        next(result.code for result in results if result.outcome == "invalid_input")
        == "fiscal_duplicate_document"
    )
    with service.authority.pool.connection() as db:
        assert (
            db.execute(
                "select count(*) from public.financial_records where user_id=%s and record_kind in ('expense','income')",
                (context.owner_id,),
            ).fetchone()[0]
            == 1
        )


def test_conflicting_amount_same_ncf_is_refused_before_money_and_review_keeps_tax(
    actions,
):
    service, context, _ = actions
    account = cash_account(service, context)
    first = reviewed(service, context, account)
    assert approve(service, context, first).outcome == "applied"
    second = reviewed(service, context, account)
    changed = service.review(
        context,
        second[0],
        ReviewDraft(
            version=second[1],
            facts=BusinessFactPatch(amount={"state": "known", "value": "1200"}),
        ),
        "amount-change",
    )
    before = service.dossier(context, second[0])
    assert before.dgii is not None
    assert before.history[-1].before_dgii == before.history[-1].after_dgii
    outcome = approve(service, context, (second[0], changed.version, second[2]))
    assert outcome.code == "fiscal_duplicate_document"


def test_accountant_cannot_change_rnc_or_approve_refund_but_reads_same_fiscal_packet(
    actions, users
):
    service, context, _ = actions
    with service.authority.pool.connection() as db:
        grant = db.execute(
            "insert into public.business_client_grants(space_id,grantee_id,issuer_id,capabilities) values(%s,%s,%s,array['read','prepare']) returning id",
            (context.actor.space_id, users["other"], users["owner"]),
        ).fetchone()[0]
    accountant = service.resolve_actor(
        TrustedActor(
            actor_id=users["other"], actor_kind="member", space_id=context.actor.space_id
        ),
        grant_id=grant,
    )
    assert read_profile(service.authority, accountant)["can_edit"] is False
    with pytest.raises(ActionError, match="business_permission_denied"):
        set_profile(
            service.authority,
            accountant,
            filer_change("199990013"),
            "rnc",
        )
    denied = service.approve_refund(
        accountant, uuid4(), ApproveRefund(version=1, action="record_refund"), "refund"
    )
    assert denied.code == "business_permission_denied"
    period = ExportPeriod(date(2026, 9, 1), date(2026, 9, 30))
    owner_blob = export_package(
        service.authority, context, period, InMemorySourceObjects()
    )
    accountant_blob = export_package(
        service.authority, accountant, period, InMemorySourceObjects()
    )
    with (
        ZipFile(io.BytesIO(owner_blob)) as owner,
        ZipFile(io.BytesIO(accountant_blob)) as other,
    ):
        assert owner.read("dgii/606-607.xlsx") == other.read("dgii/606-607.xlsx")
        assert (
            json.loads(owner.read("manifest.json"))["dgii"]
            == json.loads(other.read("manifest.json"))["dgii"]
        )


def test_rnc_profile_revision_and_accepted_fiscal_edit_never_reposts_money(actions):
    service, context, _ = actions
    account = cash_account(service, context)
    command = filer_change("199990013")
    assert set_profile(service.authority, context, command, "same") == set_profile(
        service.authority, context, command, "same"
    )
    with pytest.raises(ActionError, match="stale_version"):
        set_profile(
            service.authority,
            context,
            filer_change(None),
            "stale",
        )
    draft = reviewed(service, context, account)
    assert approve(service, context, draft).outcome == "applied"
    saved = service.dossier(context, draft[0])
    result = service.review(
        context,
        draft[0],
        ReviewDraft(
            version=saved.version, dgii=FiscalReview.model_validate(INPUTS[0]["input"])
        ),
        "late-fiscal",
    )
    assert result.code == "recorded_correction_unsupported"


def test_legacy_printed_supplier_identity_blocks_new_canonical_duplicate(actions):
    from dataclasses import replace

    from argus.domain.business.actions import mutations
    from argus.domain.business.contracts.facts import BusinessResolution
    from argus.domain.business.transactions import transaction

    service, context, _ = actions
    account = cash_account(service, context)
    first = reviewed(service, context, account)
    source_id = shared.source(
        service,
        context,
        "PRÁCTICA legacy printed source RNC 199-99002-1, NCF b0100000001",
    )
    with transaction(service.authority, context, "prepare") as tx:
        event = tx.imports.event(str(first[0]))
        facts = BusinessResolution.model_validate(event.resolution["business"]).facts
        fiscal = facts.fiscal.model_copy(
            update={
                "rnc": facts.fiscal.rnc.model_copy(update={"value": "199-99002-1"}),
                "ncf": facts.fiscal.ncf.model_copy(update={"value": "b0100000001"}),
            }
        )
        event = replace(event, version=event.version + 1)
        changed = mutations.save_revision(
            tx,
            event,
            facts,
            facts.model_copy(update={"fiscal": fiscal}),
            (source_id,),
            tx.authorization.provenance,
            None,
        )
    assert (
        approve(service, context, (first[0], changed.version, first[2])).outcome
        == "applied"
    )
    second = reviewed(service, context, account)
    assert approve(service, context, second).code == "fiscal_duplicate_document"


def test_fiscal_profile_api_and_column_privileges_keep_owner_boundary(actions, users):
    from argus.api.business import BusinessPerson, require_business_person
    from argus.api.business_drafts import DraftContext, require_drafts
    from argus.api.routers.business_fiscal import router
    from argus.domain.business.spaces import PostgresSpaceStore
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    service, context, grant = actions
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_drafts] = lambda: DraftContext(
        service, context.actor.actor_id, str(context.actor.space_id), grant
    )
    app.dependency_overrides[require_business_person] = lambda: BusinessPerson(
        str(context.actor.actor_id), PostgresSpaceStore(service.authority.pool)
    )

    @app.middleware("http")
    async def request_id(request, call_next):
        request.state.request_id = "dgii-synthetic-api"
        return await call_next(request)

    with TestClient(app) as client:
        profile = client.get("/business/fiscal-profile")
        assert profile.status_code == 200 and profile.json() == {
            "name": "PRÁCTICA José",
            "tax_id": None,
            "can_edit": True,
        }
        assert profile.headers["cache-control"] == "no-store"
        fields = client.get("/business/fiscal-profile/fields")
        assert fields.status_code == 200
        assert next(
            field for field in fields.json()["607"] if field["name"] == "income_type"
        )["options"] == ["1", "2", "3", "4", "5", "6"]
        invalid = client.patch(
            "/business/fiscal-profile",
            json={
                "name": "PRÁCTICA José",
                "previous_name": "PRÁCTICA José",
                "tax_id": {"type": "rnc", "value": "000000000"},
                "previous_tax_id": None,
            },
            headers={"Idempotency-Key": "invalid"},
        )
        assert (
            invalid.status_code == 422
            and invalid.headers["cache-control"] == "no-store"
            and invalid.json()["detail"]["code"] == "tax_id_all_zero"
        )
        changed = client.patch(
            "/business/fiscal-profile",
            json={
                "name": "PRÁCTICA José",
                "previous_name": "PRÁCTICA José",
                "tax_id": {"type": "rnc", "value": "199-99001-3"},
                "previous_tax_id": None,
            },
            headers={"Idempotency-Key": "valid"},
        )
        assert changed.status_code == 200 and changed.json()["tax_id"] == {
            "type": "rnc",
            "value": "199990013",
        }
        with service.authority.pool.connection() as db:
            assert (
                db.execute(
                    "select has_column_privilege('authenticated','public.spaces','business_rnc','SELECT')"
                ).fetchone()[0]
                is False
            )
            assert (
                db.execute(
                    "select has_column_privilege('anon','public.spaces','business_tax_id_type','UPDATE')"
                ).fetchone()[0]
                is False
            )
            db.execute(
                "update public.business_client_grants set revoked_at=now() where id=%s",
                (grant,),
            )
        denied = client.get("/business/fiscal-profile")
        assert denied.status_code == 404 and denied.headers["cache-control"] == "no-store"


def test_cedula_filer_persists_and_exports_both_formats(actions):
    service, context, _ = actions
    account = cash_account(service, context)
    filer = "00100000001"
    profile = set_profile(
        service.authority,
        context,
        filer_change(filer),
        "cedula-profile",
    )
    assert profile["tax_id"]["value"] == filer
    from psycopg.errors import CheckViolation

    with service.authority.pool.connection() as db:
        with pytest.raises(CheckViolation):
            with db.transaction():
                db.execute(
                    "update public.spaces set business_rnc=%s where id=%s",
                    ("00000000000", context.actor.space_id),
                )
    assert read_profile(service.authority, context)["tax_id"]["value"] == filer
    for index in (0, 4):
        assert (
            approve(service, context, reviewed(service, context, account, index)).outcome
            == "applied"
        )
    with ZipFile(
        io.BytesIO(
            export_package(
                service.authority,
                context,
                ExportPeriod(date(2026, 9, 1), date(2026, 9, 30)),
                InMemorySourceObjects(),
            )
        )
    ) as archive:
        manifest = json.loads(archive.read("manifest.json"))["dgii"]
        for form in ("606", "607"):
            assert manifest["forms"][form]["status"] == "prepared_candidate"
            assert (
                archive.read(f"dgii/DGII_F_{form}_{filer}_202609.TXT").split(b"\r\n")[0]
                == f"{form}|{filer}|202609|1".encode()
            )


def test_typed_profile_feeds_the_export_header_and_a_non_owner_cannot_edit(
    actions, users
):
    service, context, _ = actions
    saved = set_profile(
        service.authority,
        context,
        FiscalProfileChange(
            name="Taller Norte",
            previous_name="PRÁCTICA José",
            tax_id={"type": "rnc", "value": "199-99001-3"},
            previous_tax_id=None,
        ),
        "profile-rnc",
    )
    assert saved == {
        "name": "Taller Norte",
        "tax_id": {"type": "rnc", "value": "199990013"},
        "can_edit": True,
    }
    cedula = set_profile(
        service.authority,
        context,
        FiscalProfileChange(
            name="Taller Norte",
            previous_name="Taller Norte",
            tax_id={"type": "cedula", "value": "001 0000000 1"},
            previous_tax_id={"type": "rnc", "value": "199990013"},
        ),
        "profile-cedula",
    )
    assert cedula["tax_id"] == {"type": "cedula", "value": "00100000001"}
    with service.authority.pool.connection() as db:
        row = db.execute(
            "select actor_id::text as actor_id, created_at, command"
            " from public.business_action_receipts"
            " where space_id=%s and idempotency_key=%s",
            (context.actor.space_id, "profile-cedula"),
        ).fetchone()
        assert row["actor_id"] == str(context.actor.actor_id)
        assert row["created_at"] is not None
        assert row["command"]["tax_id"]["type"] == "cedula"
        assert row["command"]["tax_id"]["value"] == "00100000001"
        assert row["command"]["name"] == "Taller Norte"
        from psycopg.errors import CheckViolation

        with pytest.raises(CheckViolation):
            with db.transaction():
                db.execute(
                    "update public.spaces set business_tax_id_type=%s, business_rnc=%s where id=%s",
                    ("rnc", "00100000001", context.actor.space_id),
                )
        with pytest.raises(CheckViolation):
            with db.transaction():
                db.execute(
                    "update public.spaces set business_tax_id_type=%s, business_rnc=%s where id=%s",
                    ("cedula", "199990013", context.actor.space_id),
                )
    with service.authority.pool.connection() as db:
        grant = db.execute(
            "insert into public.business_client_grants(space_id,grantee_id,issuer_id,capabilities)"
            " values(%s,%s,%s,array['read','prepare']) returning id",
            (context.actor.space_id, users["other"], users["owner"]),
        ).fetchone()[0]
    accountant = service.resolve_actor(
        TrustedActor(
            actor_id=users["other"],
            actor_kind="member",
            space_id=context.actor.space_id,
        ),
        grant_id=grant,
    )
    assert read_profile(service.authority, accountant)["can_edit"] is False
    with pytest.raises(ActionError, match="business_permission_denied"):
        set_profile(
            service.authority,
            accountant,
            FiscalProfileChange(
                name="Otro nombre",
                previous_name="Taller Norte",
                tax_id={"type": "rnc", "value": "199990048"},
                previous_tax_id={"type": "cedula", "value": "00100000001"},
            ),
            "accountant-edit",
        )
    account = cash_account(service, context)
    for index in (0, 4):
        assert (
            approve(service, context, reviewed(service, context, account, index)).outcome
            == "applied"
        )
    with ZipFile(
        io.BytesIO(
            export_package(
                service.authority,
                context,
                ExportPeriod(date(2026, 9, 1), date(2026, 9, 30)),
                InMemorySourceObjects(),
            )
        )
    ) as archive:
        manifest = json.loads(archive.read("manifest.json"))["dgii"]
        assert manifest["business_name"] == "Taller Norte"
        assert manifest["reporter_rnc"] == "00100000001"
        for form in ("606", "607"):
            assert (
                archive.read(f"dgii/DGII_F_{form}_00100000001_202609.TXT").split(b"\r\n")[
                    0
                ]
                == f"{form}|00100000001|202609|1".encode()
            )
