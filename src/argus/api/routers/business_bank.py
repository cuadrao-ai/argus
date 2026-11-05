"""Business bank statement routes. Mounted from the Business router.

Default-off. The personal import queue is not this surface.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Header, Request, Response, UploadFile
from loguru import logger

from argus.api.business import (
    BusinessPerson,
    require_business_person,
    unavailable_problem,
    working_scope,
)
from argus.api.business_bank_schemas import (
    BankImportResponse,
    BankLineResponse,
    BankSuggestionResponse,
    UnmatchedChargesResponse,
)
from argus.api.business_drafts import action_problem
from argus.api.business_spaces import business_access, space_missing_problem
from argus.api.dependencies import problem
from argus.api.documents import NO_STORE
from argus.domain.business.authority import ActionError
from argus.domain.business.bank.model import (
    AmountAndSignColumns,
    BankLine,
    BankMatchingError,
    CsvMapping,
    DebitAndCreditColumns,
    Suggestion,
)
from argus.domain.business.bank.service import (
    bank_matching_on,
    bank_matching_service,
    confidence_of,
)
from argus.domain.business.bank.store_postgres import PostgresBankStore
from argus.domain.business.contracts.authority import TrustedActor

router = APIRouter(prefix="/bank", tags=["business-bank"])

_MAX_BYTES = 2 * 1024 * 1024
_STATUSES = {
    "business_permission_denied": 403,
    "one_account": 409,
    "layout_not_ready": 422,
    "unsupported_layout": 422,
    "invalid_mapping": 422,
    "invalid_statement": 422,
    "account_not_in_space": 404,
    "suggestion_not_found": 404,
    "suggestion_not_pending": 409,
    "pair_declined": 409,
    "line_already_confirmed": 409,
    "line_marked_no_receipt": 409,
    "line_not_matched": 409,
    "line_not_marked": 409,
    "line_not_found": 404,
    "document_already_matched": 409,
    "document_not_matchable": 422,
    "target_not_approved": 409,
    "idempotency_conflict": 409,
    "business_bank_matching_off": 404,
}


def require_bank_surface(request: Request) -> None:
    if not bank_matching_on():
        raise unavailable_problem(request)


def required_key(request: Request, raw: str | None) -> str:
    from argus.domain.idempotency import validate_idempotency_key

    state, key = validate_idempotency_key(raw)
    if state == "ok" and key is not None:
        return key
    if state == "invalid":
        raise problem(
            request,
            status_code=422,
            code="validation_error",
            title="Validation Error",
            detail="Idempotency-Key must be 1-128 visible ASCII characters with no whitespace.",
            headers=NO_STORE,
        )
    raise problem(
        request,
        status_code=400,
        code="idempotency_key_required",
        title="Idempotency Key Required",
        detail="This request requires an Idempotency-Key header.",
        headers=NO_STORE,
    )


def _scope(request: Request, person: BusinessPerson):
    scope = working_scope(request, person.spaces, person.person_id)
    if scope is None:
        raise space_missing_problem(request)
    return scope


def _capabilities(space_id: str, person_id: str) -> frozenset[str]:
    access = business_access()
    if access is None:
        return frozenset()
    return frozenset(access.capabilities(space_id, person_id))


@contextmanager
def _bank_access(
    service, scope, person: BusinessPerson, capability: str
) -> Iterator[frozenset[str]]:  # noqa: ANN001
    if isinstance(service.store, PostgresBankStore):
        actor = TrustedActor(
            actor_id=UUID(person.person_id),
            actor_kind="member",
            space_id=UUID(scope.owner.space_id),
        )
        grant_id = UUID(scope.grant_id) if scope.grant_id else None
        with service.store.authorized_transaction(
            actor, grant_id, capability
        ) as authorization:
            yield authorization.capabilities
    else:
        yield _capabilities(scope.owner.space_id, person.person_id)


def bank_problem(request: Request, error: BankMatchingError) -> Exception:
    status = _STATUSES.get(error.code, 400)
    return problem(
        request,
        status_code=status,
        code=error.code,
        title="Bank matching",
        detail=error.code,
        headers=NO_STORE,
    )


def _line(service, line: BankLine) -> BankLineResponse:  # noqa: ANN001
    return BankLineResponse(
        id=line.id,
        occurred_on=line.occurred_on,
        description=line.description,
        amount=line.amount,
        currency=line.currency,
        sense=line.sense,
        state=service.line_state(line),
    )


def _suggestion(service, row: Suggestion) -> BankSuggestionResponse:  # noqa: ANN001
    status, actionable = service.suggestion_view(row)
    return BankSuggestionResponse(
        id=row.id,
        line_id=row.line_id,
        target_id=row.target_id,
        target_kind=row.target_kind,
        status=status,
        amount_score=row.parts.amount_score,
        date_score=row.parts.date_score,
        merchant_score=row.parts.merchant_score,
        confidence=confidence_of(row),
        actionable=actionable,
    )


@router.post(
    "/imports",
    response_model=BankImportResponse,
    status_code=201,
    dependencies=[Depends(require_bank_surface)],
)
async def import_statement(
    request: Request,
    response: Response,
    person: Annotated[BusinessPerson, Depends(require_business_person)],
    statement: Annotated[UploadFile, File()],
    account_id: Annotated[UUID, Form()],
    reader_id: Annotated[
        Literal[
            "pilot_bank",
            "banco_popular",
            "bhd",
            "mercury",
            "sandbox_csv",
            "mapped_csv",
        ]
        | None,
        Form(),
    ] = None,
    date_column: Annotated[str | None, Form()] = None,
    description_column: Annotated[str | None, Form()] = None,
    amount_column: Annotated[str | None, Form()] = None,
    sign_column: Annotated[str | None, Form()] = None,
    debit_column: Annotated[str | None, Form()] = None,
    credit_column: Annotated[str | None, Form()] = None,
    currency_column: Annotated[str | None, Form()] = None,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> BankImportResponse:
    response.headers.update(NO_STORE)
    key = required_key(request, idempotency_key)
    scope = _scope(request, person)
    actor_id = UUID(scope.actor_id or scope.person_id)
    content = await statement.read(_MAX_BYTES + 1)
    if len(content) > _MAX_BYTES:
        raise problem(
            request,
            status_code=413,
            code="statement_too_large",
            title="Bank matching",
            detail="statement_too_large",
            headers=NO_STORE,
        )
    service = bank_matching_service()
    if service is None:
        raise unavailable_problem(request)
    try:
        with _bank_access(service, scope, person, "prepare") as capabilities:
            result = service.import_statement(
                space_id=UUID(scope.owner.space_id),
                actor_id=actor_id,
                owner_id=UUID(scope.person_id),
                capabilities=capabilities,
                content=content,
                account_id=account_id,
                reader_id=reader_id,
                mapping=_mapping(
                    date_column,
                    description_column,
                    amount_column,
                    sign_column,
                    debit_column,
                    credit_column,
                    currency_column,
                ),
                idempotency_key=key,
            )
            logger.info(
                "business bank import space={} reader={} inserted={} unchanged={}",
                scope.owner.space_id,
                result.bank_import.reader_id,
                result.bank_import.inserted_count,
                result.bank_import.unchanged_count,
            )
            response.status_code = 201 if result.created else 200
            return BankImportResponse(
                id=result.bank_import.id,
                reader_id=result.bank_import.reader_id,
                inserted_count=result.bank_import.inserted_count,
                unchanged_count=result.bank_import.unchanged_count,
                created=result.created,
                imported_at=result.bank_import.imported_at,
                lines=[_line(service, line) for line in result.lines],
                suggestions=[_suggestion(service, row) for row in result.suggestions],
            )
    except ActionError as error:
        raise action_problem(request, error.result) from None
    except BankMatchingError as error:
        raise bank_problem(request, error) from None


@router.get(
    "/suggestions",
    response_model=list[BankSuggestionResponse],
    dependencies=[Depends(require_bank_surface)],
)
def list_suggestions(
    request: Request,
    response: Response,
    person: Annotated[BusinessPerson, Depends(require_business_person)],
    status: Literal["pending", "confirmed", "declined"] | None = None,
) -> list[BankSuggestionResponse]:
    response.headers.update(NO_STORE)
    scope = _scope(request, person)
    service = bank_matching_service()
    if service is None:
        raise unavailable_problem(request)
    try:
        with _bank_access(service, scope, person, "read") as capabilities:
            rows = service.list_suggestions(
                space_id=UUID(scope.owner.space_id),
                capabilities=capabilities,
                status=status,
            )
            answer = [_suggestion(service, row) for row in rows]
    except ActionError as error:
        raise action_problem(request, error.result) from None
    except BankMatchingError as error:
        raise bank_problem(request, error) from None
    return answer


@router.get(
    "/unmatched",
    response_model=UnmatchedChargesResponse,
    dependencies=[Depends(require_bank_surface)],
)
def list_unmatched(
    request: Request,
    response: Response,
    person: Annotated[BusinessPerson, Depends(require_business_person)],
    period_start: date,
    period_end: date,
) -> UnmatchedChargesResponse:
    response.headers.update(NO_STORE)
    if period_end < period_start:
        raise problem(
            request,
            status_code=422,
            code="invalid_period",
            title="Bank matching",
            detail="invalid_period",
            headers=NO_STORE,
        )
    scope = _scope(request, person)
    service = bank_matching_service()
    if service is None:
        raise unavailable_problem(request)
    space_id = UUID(scope.owner.space_id)
    try:
        with _bank_access(service, scope, person, "read") as capabilities:
            service.list_lines(
                space_id=space_id,
                capabilities=capabilities,
                period_start=period_start,
                period_end=period_end,
            )
            lines = service.unmatched_charges(
                space_id=space_id, period_start=period_start, period_end=period_end
            )
            return UnmatchedChargesResponse(
                count=len(lines),
                period_start=period_start,
                period_end=period_end,
                lines=[_line(service, line) for line in lines],
            )
    except ActionError as error:
        raise action_problem(request, error.result) from None
    except BankMatchingError as error:
        raise bank_problem(request, error) from None


def _mapping(
    date_column: str | None,
    description_column: str | None,
    amount_column: str | None,
    sign_column: str | None,
    debit_column: str | None,
    credit_column: str | None,
    currency_column: str | None,
) -> CsvMapping | None:
    named = [
        date_column,
        description_column,
        amount_column,
        sign_column,
        debit_column,
        credit_column,
        currency_column,
    ]
    if all(value is None for value in named):
        return None
    if not date_column or not description_column:
        raise BankMatchingError("invalid_mapping")
    sign_pair = bool(amount_column) and bool(sign_column)
    debit_pair = bool(debit_column) and bool(credit_column)
    if sign_pair == debit_pair:
        raise BankMatchingError("invalid_mapping")
    money: AmountAndSignColumns | DebitAndCreditColumns
    if sign_pair:
        assert amount_column is not None and sign_column is not None
        money = AmountAndSignColumns(amount_column, sign_column)
    else:
        assert debit_column is not None and credit_column is not None
        money = DebitAndCreditColumns(debit_column, credit_column)
    return CsvMapping(
        date_column=date_column,
        description_column=description_column,
        money=money,
        currency_column=currency_column,
    )
