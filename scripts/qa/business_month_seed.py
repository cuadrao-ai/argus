"""Fill one staging Business with one period of practice books and a bank CSV.

Documents go through the product upload, preparation, review, and approval
path. Bank lines are written to a CSV because Cuadrao has no statement
import, and, with ``--with-plaid``, the same lines are created in Plaid
sandbox. Nothing here talks to a project other than staging.

``--email`` must be ``qa-seed@...`` or ``qa-seed+...@...``. The account may
own no Business, or only the Business this seed created (named ``QA Seed``).
``--reset`` disconnects seed documents and seed Plaid connections. It cannot
clear approved expenses and incomes. The product has no void, delete, or
reversal for those books.

A dry run needs the dev dependency group (``faker``).

    python scripts/qa/business_month_seed.py --dry-run
    python scripts/qa/business_month_seed.py --email qa-seed+october@example.com --reset
    python scripts/qa/business_month_seed.py --email qa-seed+october@example.com --with-plaid
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

QA_DIR = Path(__file__).resolve().parent
if str(QA_DIR) not in sys.path:
    sys.path.insert(0, str(QA_DIR))

from business_month_guard import (  # noqa: E402
    SEED_SPACE_NAME,
    StagingRefused,
    refuse_unless_plaid_sandbox,
    refuse_unless_staging,
    require_qa_owner,
    require_seed_space,
)
from dgii_fiscal import (  # noqa: E402
    DRY_RUN_END,
    DRY_RUN_START,
    UNSUPPORTED_DECLARATION_FIELDS,
    build_plan,
    duplicate_guard_line,
    parse_period,
    plaid_transactions,
    write_duplicate_guard,
    write_outputs,
)

DUPLICATE_SECOND = "qa-seed-roto-ncf-duplicado-b.txt"

APPROVED_BOOKS = (
    "approved-books: not cleared; the product has no void, delete, or reversal "
    "for an approved expense or income"
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seed one staging Business period for QA."
    )
    parser.add_argument(
        "--email",
        default="",
        help="QA seed owner: qa-seed@ or qa-seed+...@, with no other Business.",
    )
    parser.add_argument("--from", dest="start", default=DRY_RUN_START.isoformat())
    parser.add_argument("--to", dest="end", default=DRY_RUN_END.isoformat())
    parser.add_argument("--seed", type=int, default=202609)
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Disconnect seed documents and seed Plaid connections.",
    )
    parser.add_argument(
        "--with-plaid", action="store_true", help="Mirror the CSV in Plaid sandbox."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Write the CSV, manifest, and practice files only.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.email.strip():
        try:
            require_qa_owner(args.email)
        except StagingRefused as error:
            print(str(error), file=sys.stderr)
            return 2
    try:
        period = parse_period(args.start, args.end)
    except ValueError as error:
        print(f"refusing to write: {error}", file=sys.stderr)
        return 2
    plan = build_plan(period, args.seed)
    paths = write_outputs(plan)
    print(f"csv: {paths['csv']}")
    print(f"manifest: {paths['manifest']}")
    print(f"practica-606: {paths['practica_606']}")
    print(f"practica-607: {paths['practica_607']}")
    print(
        "formato-606-607-export: not in the product; these practice files are the fixture renderer"
    )
    print(
        "statement-import: not in the product; the CSV is the bank file QA can import later"
    )
    print(
        "declaration-facts: review and approve do not accept "
        + ", ".join(UNSUPPORTED_DECLARATION_FIELDS)
    )
    print(APPROVED_BOOKS)
    print(f"documents: {len(plan.documents)}")
    print(f"bank-lines: {len(plan.lines)}")
    print(f"pairs: {len(plan.manifest['pairs'])}")
    if args.dry_run:
        print(duplicate_guard_line(None))
        print("intake: not run")
        return 0
    if not args.email.strip():
        print("refusing to write: --email is required", file=sys.stderr)
        return 2
    try:
        refuse_unless_staging(os.environ)
        if args.with_plaid:
            refuse_unless_plaid_sandbox(os.environ)
    except StagingRefused as error:
        print(str(error), file=sys.stderr)
        return 2
    try:
        return _ingest(args, plan, paths["manifest"])
    except StagingRefused as error:
        print(str(error), file=sys.stderr)
        return 2


def _ingest(args: argparse.Namespace, plan, manifest_path: Path) -> int:  # noqa: ANN001
    """Import product code only after the staging guard has already refused."""

    refuse_unless_staging(os.environ)
    if args.with_plaid:
        _require_sandbox_client()

    from datetime import datetime, time, timezone
    from uuid import UUID
    from zoneinfo import ZoneInfo

    from argus.domain.business.actions.service import BusinessActions
    from argus.domain.business.contracts.authority import TrustedActor
    from argus.domain.business.receipt_consent import BusinessReceiptConsentStore
    from argus.domain.business.spaces import PostgresSpaceStore
    from argus.domain.ingestion.connections_postgres import PostgresConnectionRepository
    from argus.domain.ingestion.documents.objects import SupabaseSourceObjects
    from argus.domain.ingestion.documents.service import DocumentsService
    from argus.domain.ingestion.documents.store_postgres import PostgresDocumentStore
    from argus.domain.ingestion.hub import IngestionHub
    from argus.domain.ingestion.reconcile.service import ReconciliationService
    from argus.domain.ingestion.reconcile.store_postgres import PostgresImportStore
    from argus.domain.owner_scope import BusinessSpace
    from argus.domain.recording.money_service import MoneyService
    from argus.domain.recording.postgres_repository import (
        PostgresFinancialAccountRepository,
    )
    from argus.domain.recording.schemas import CreateFinancialAccountRequest
    from argus.domain.recording.service import FinancialAccountService
    from psycopg_pool import ConnectionPool

    from supabase import create_client

    database_url = os.environ["DATABASE_URL"]
    supabase_url = os.environ.get("SUPABASE_URL") or os.environ["SUPABASE_PROJECT_URL"]
    pool = ConnectionPool(database_url, min_size=0, max_size=2, open=True)
    try:
        clock = lambda: datetime.now(timezone.utc)  # noqa: E731
        connections = PostgresConnectionRepository(pool)
        accounts = FinancialAccountService(PostgresFinancialAccountRepository(pool))
        sink = ReconciliationService(
            PostgresImportStore(pool),
            MoneyService(accounts),
            clock,
            connections=connections,
        )
        box = None
        if args.with_plaid:
            from argus.domain.ingestion.secrets import SecretBox

            box = SecretBox.from_env()
        hub = IngestionHub(connections, box=box, sink=sink, clock=clock)
        store = PostgresDocumentStore(
            pool,
            SupabaseSourceObjects(
                create_client(
                    supabase_url, os.environ["SUPABASE_SERVICE_ROLE_KEY"]
                ).storage
            ),
        )
        actions = BusinessActions(pool, sink)
        service = DocumentsService(
            hub,
            store,
            _SeedExtractor(plan.documents),
            jobs_recover_interruptions=False,
            business_actions=actions,
            business_preparation_required=True,
        )
        service.business_receipt_consent = BusinessReceiptConsentStore(pool)
        email = require_qa_owner(args.email)
        user_id = _owner_id(pool, email)
        spaces = PostgresSpaceStore(pool)
        existing = spaces.open_space(user_id)
        require_seed_space(None if existing is None else existing.name)
        space, _created = spaces.create(user_id, SEED_SPACE_NAME)
        scope = BusinessSpace(space.id)
        if args.reset:
            _reset(hub, store, sink, user_id, scope, args.with_plaid)
        account_id = accounts.create(
            user_id=user_id,
            idempotency_key="qa-seed-checking-dop",
            request=CreateFinancialAccountRequest(
                type="checking",
                currency="DOP",
                nickname="QA Seed operativo",
                amount="5000000.00",
                as_of=datetime.combine(
                    plan.period.start, time(0), tzinfo=ZoneInfo("America/Santo_Domingo")
                ),
                time_zone="America/Santo_Domingo",
            ),
            scope=scope,
        ).stored.id
        _enable_consent(service.business_receipt_consent, space.id, user_id)
        context = actions.resolve_actor(
            TrustedActor(
                actor_id=UUID(user_id), actor_kind="member", space_id=UUID(space.id)
            )
        )
        prepared = approved = refused = 0

        async def capture_all() -> None:
            nonlocal prepared, approved, refused
            for document in plan.documents:
                outcome = await _capture(
                    service, actions, context, user_id, scope, document
                )
                prepared += 1
                result = _approve(actions, sink, context, document, account_id, outcome)
                if document.filename == DUPLICATE_SECOND:
                    print(write_duplicate_guard(manifest_path, result))
                if result == "approved":
                    approved += 1
                elif result == "unsupported":
                    print(
                        f"approval {document.filename}: approval command missing for {document.kind}"
                    )
                elif result != "replayed":
                    refused += 1
                    print(f"approval {document.filename}: {result}")

        asyncio.run(capture_all())
        print(f"prepared: {prepared}")
        print(f"approved: {approved}")
        print(f"approval-refused: {refused}")
        if args.with_plaid:
            print(_plaid(hub, user_id, plan))
        print(f"project: {refuse_unless_staging(os.environ)}")
        return 0
    finally:
        pool.close()


class _SeedExtractor:
    """Reads the practice text itself. No model call."""

    def __init__(self, documents) -> None:  # noqa: ANN001
        self._documents = {document.filename: document for document in documents}

    async def extract(
        self,
        *,
        content: bytes,
        filename: str,
        media_type: str,
        connection_id: str,
        observed_at,
        prepared=None,
    ):
        import hashlib

        from argus.domain.ingestion.contract import Attachment
        from argus.domain.ingestion.documents.extractor import batch_from_result
        from argus.domain.ingestion.documents.models import (
            ExtractedObservation,
            ExtractionResult,
            ReceiptDetails,
            ReceiptItem,
        )

        document = self._documents[filename]
        amount = f"{document.amount:.2f}"
        result = ExtractionResult(
            complete=True,
            readable=True,
            pages_read=(1,),
            observations=(
                ExtractedObservation(
                    page=1,
                    row=1,
                    evidence="transaction",
                    occurred_on=document.occurred_on,
                    amount=amount,
                    currency="DOP",
                    direction=document.direction,
                    kind_hint=document.kind,
                    merchant=document.counterparty,
                    description=(
                        document.ncf or document.ecf or document.tag or "QA-SEED"
                    ),
                ),
            ),
            receipt=ReceiptDetails(
                merchant=document.counterparty,
                occurred_on=document.occurred_on,
                currency="DOP",
                subtotal=f"{document.subtotal:.2f}",
                itbis=f"{document.itbis:.2f}",
                tip=f"{document.propina:.2f}" if document.propina else None,
                total=amount,
                rnc=document.rnc,
                ncf=document.ncf,
                ecf=document.ecf,
                items=(
                    ReceiptItem(
                        id="1",
                        description=document.ncf or document.ecf or "QA-SEED",
                        total=f"{document.subtotal:.2f}",
                    ),
                ),
            ),
        )
        digest = hashlib.sha256(content).hexdigest()
        batch = batch_from_result(result, digest, connection_id, observed_at, 1)
        attachment = Attachment(
            external_id=digest,
            sha256=digest,
            media_type=media_type,
            size_bytes=len(content),
            filename=filename,
        )
        candidates = tuple(
            candidate.model_copy(update={"attachments": (attachment,)})
            for candidate in batch.candidates
        )
        return batch.model_copy(
            update={
                "candidates": candidates,
                "metadata": {"sha256": digest, "pages": 1, "media_type": media_type},
            }
        )


def _require_sandbox_client() -> None:
    from argus.domain.ingestion.plaid.config import plaid_config_from_env

    config = plaid_config_from_env()
    if config.environment != "sandbox" or config.base_url != "https://sandbox.plaid.com":
        raise StagingRefused("refusing to write: Plaid is not sandbox")
    if not config.configured:
        raise StagingRefused(
            "refusing to write: Plaid sandbox credentials are not configured"
        )


def _owner_id(pool, email: str) -> str:  # noqa: ANN001
    with pool.connection() as connection:
        row = connection.execute(
            "select id::text from auth.users where lower(email)=%s"
            " and email_confirmed_at is not null and coalesce(is_anonymous, false)=false"
            " order by created_at limit 1",
            (email.strip().lower(),),
        ).fetchone()
    if row is None:
        raise StagingRefused("refusing to write: no confirmed account for that email")
    return row[0]


def _enable_consent(store, space_id: str, user_id: str) -> None:  # noqa: ANN001
    from argus.domain.business.receipt_consent import SCOPE_VERSION

    status = store.status(space_id, user_id, "es-419")
    if not status["available"]:
        raise StagingRefused(
            "refusing to write: receipt reading model is not configured, so consent cannot be recorded"
        )
    if status["enabled"]:
        return
    store.set(
        space_id,
        user_id,
        enabled=True,
        version=SCOPE_VERSION,
        disclosure_token=status["disclosure_token"],
        language="es-419",
        idempotency_key="qa-seed-receipt-consent",
    )


def _reset(hub, store, sink, user_id: str, scope, with_plaid: bool) -> None:  # noqa: ANN001
    from argus.domain.owner_scope import PERSONAL

    removed = 0
    for connection in hub.list(user_id=user_id, scope=scope):
        if connection.source != "statement" or connection.status == "disconnected":
            continue
        draft = store.draft(user_id=user_id, connection_id=connection.id)
        if draft is None or not draft.filename.startswith("qa-seed-"):
            continue
        hub.disconnect(user_id=user_id, connection_id=connection.id, scope=scope)
        removed += 1
    plaid_removed = 0
    if with_plaid:
        _register_plaid(hub)
    for connection in hub.list(user_id=user_id, scope=PERSONAL):
        if connection.source != "plaid" or connection.status == "disconnected":
            continue
        if not _marked(sink, user_id, connection.id):
            continue
        hub.disconnect(user_id=user_id, connection_id=connection.id, scope=PERSONAL)
        plaid_removed += 1
    print(f"reset-documents: {removed}")
    print(f"reset-plaid: {plaid_removed}")
    print(APPROVED_BOOKS)


def _register_plaid(hub) -> None:  # noqa: ANN001
    from argus.domain.ingestion.plaid.config import plaid_config_from_env
    from argus.domain.ingestion.plaid.connector import PlaidConnector

    config = plaid_config_from_env()
    if config.environment != "sandbox" or config.base_url != "https://sandbox.plaid.com":
        raise StagingRefused("refusing to write: Plaid is not sandbox")
    connector = PlaidConnector(hub, config)
    hub.register(connector.adapter)
    hub._qa_plaid = connector  # noqa: SLF001


def _marked(sink, user_id: str, connection_id: str) -> bool:  # noqa: ANN001
    from argus.domain.owner_scope import PERSONAL

    with sink.store.transaction(user_id, scope=PERSONAL) as tx:
        observations = tx.connection_observations(connection_id)
    for observation in observations:
        text = " ".join(
            str(observation.candidate.get(name) or "")
            for name in ("description", "merchant")
        )
        if "QA-SEED" in text:
            return True
    return False


async def _capture(service, actions, context, user_id, scope, document):  # noqa: ANN001
    from uuid import UUID

    content = document.body.encode("utf-8")
    outcome = await service.upload(
        user_id=user_id,
        content=content,
        filename=document.filename,
        media_type="text/plain",
        scope=scope,
    )
    actions.capture_attachment_preparation(
        context, UUID(outcome.connection_id), target=None
    )
    return await service.resume(
        user_id=user_id, connection_id=outcome.connection_id, scope=scope
    )


def _approve(actions, sink, context, document, account_id, outcome) -> str:  # noqa: ANN001
    from uuid import UUID

    from argus.domain.business.contracts.actions import (
        ApproveExpense,
        ApproveIncome,
        ReviewDraft,
    )

    if document.approval == "unsupported":
        return "unsupported"
    event = _event(actions, context, sink, outcome.connection_id)
    if event.state == "accepted":
        return "replayed"
    facts = event.resolution.get("business", {}).get("facts", {})
    if facts.get("funding", {}).get("state") != "known":
        reviewed = actions.review(
            context,
            UUID(event.id),
            ReviewDraft(version=event.version, facts=_funding_patch(account_id)),
            f"qa-seed-review:{document.filename}",
        )
        if getattr(reviewed, "outcome", None) not in {"applied", "replayed"}:
            return getattr(reviewed, "code", None) or reviewed.outcome
        event = _event(actions, context, sink, outcome.connection_id)
    request_type = ApproveIncome if document.approval == "income" else ApproveExpense
    action_name = "record_income" if document.approval == "income" else "record_expense"
    approve = actions.approve_income if document.approval == "income" else actions.approve
    result = approve(
        context,
        UUID(event.id),
        request_type(version=event.version, action=action_name),
        f"qa-seed-approve:{document.filename}",
    )
    if getattr(result, "outcome", None) in {"applied", "replayed"}:
        return "approved"
    return getattr(result, "code", None) or result.outcome


def _funding_patch(account_id: str):
    from uuid import UUID

    from argus.domain.business.contracts.facts import (
        BusinessAccountFunding,
        BusinessFactPatch,
        KnownInput,
        WholeBusinessShare,
    )

    return BusinessFactPatch(
        funding=KnownInput(value=BusinessAccountFunding(account_id=UUID(account_id))),
        business_share=KnownInput(value=WholeBusinessShare(kind="all")),
        receipt_state=KnownInput(value="fiscal_receipt"),
    )


def _event(actions, context, sink, connection_id: str):  # noqa: ANN001
    """The draft the document preparation recorded for this upload."""

    from uuid import UUID

    from argus.domain.business.actions.receipts import draft_for_receipt
    from argus.domain.business.transactions import transaction

    with transaction(actions.authority, context, "read") as tx:
        draft_id, ambiguous = draft_for_receipt(tx, UUID(connection_id), None)
    if ambiguous or draft_id is None:
        raise StagingRefused(
            "refusing to continue: the document produced no single draft"
        )
    with sink.store.transaction(context.owner_id, scope=context.scope) as tx:
        return tx.event(str(draft_id))


def _plaid(hub, user_id: str, plan) -> str:  # noqa: ANN001
    connector = getattr(hub, "_qa_plaid", None)
    if connector is None:
        _register_plaid(hub)
        connector = hub._qa_plaid  # noqa: SLF001
    for connection in hub.list(user_id=user_id, scope=_personal()):
        if (
            connection.source == "plaid"
            and connection.status != "disconnected"
            and _marked(hub.sink, user_id, connection.id)
        ):
            return "plaid: replayed"
    public = connector.client.post(
        "/sandbox/public_token/create",
        {
            "institution_id": "ins_109508",
            "initial_products": ["transactions"],
            "options": {
                "override_username": "user_transactions_dynamic",
                "override_password": "pass_good",
            },
        },
    )["public_token"]
    exchanged = connector.link.exchange(user_id=user_id, public_token=public)
    token = hub.credential(exchanged.connection)
    if not token:
        raise StagingRefused("refusing to continue: the sandbox credential did not open")
    transactions = plaid_transactions(plan.lines)
    aligned = _create_transactions(connector, token, transactions)
    connector.client.post("/transactions/refresh", {"access_token": token})
    outcome = connector.sync(exchanged.connection)
    return f"plaid: {outcome.status} added={outcome.added} currency_aligned={aligned}"


def _personal():
    from argus.domain.owner_scope import PERSONAL

    return PERSONAL


def _create_transactions(connector, token: str, transactions: list[dict]) -> bool:  # noqa: ANN001
    from argus.domain.ingestion.plaid.client import PlaidError

    try:
        connector.client.post(
            "/sandbox/transactions/create",
            {"access_token": token, "transactions": transactions},
        )
        return True
    except PlaidError as error:
        if error.error_code not in {"INVALID_FIELD", "INVALID_REQUEST"}:
            raise StagingRefused(
                f"plaid sandbox refused the lines: {error.error_type}/{error.error_code}"
            ) from None
    fallback = [{**row, "iso_currency_code": "USD"} for row in transactions]
    connector.client.post(
        "/sandbox/transactions/create",
        {"access_token": token, "transactions": fallback},
    )
    return False


if __name__ == "__main__":
    raise SystemExit(main())
