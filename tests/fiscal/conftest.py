from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
from argus.domain.business.contracts.authority import TrustedActor
from argus.domain.business.fiscal_sandbox.config import Settings
from argus.domain.business.fiscal_sandbox.contracts import Case, Observation, digest
from argus.domain.business.fiscal_sandbox.provider import ProviderError
from argus.domain.business.fiscal_sandbox.service import Service
from argus.domain.business.fiscal_sandbox.store import Store
from faker import Faker
from psycopg import Connection
from psycopg_pool import ConnectionPool

from tests import test_financial_accounts_postgres as shared
from tests.test_business_spaces_migration_postgres import space

users = shared.users


@pytest.fixture
def case_factory():
    fake = Faker()

    def create(business_id=None, kind="E32", **changes):
        issuer = fake.numerify("1########")
        number = kind + fake.numerify("##########")
        payload = {
            "idDoc": {
                "encf": number,
                "paymentType": 1,
                "incomeType": 1,
                "taxAmountIndicator": 0,
            },
            "sender": {
                "rnc": issuer,
                "companyName": fake.company(),
                "address": fake.street_address(),
                "stampDate": "24-10-2026",
            },
            "itemDetails": [
                {
                    "itemName": "Synthetic fixture",
                    "lineNumber": 1,
                    "quantityItem": 1,
                    "unitPriceItem": 100,
                    "itemAmount": 100,
                    "billingIndicator": 1,
                    "goodServiceIndicator": 2,
                }
            ],
            "totals": {"totalAmount": 118, "itbisTotal": 18, "totalTaxedAmount": 100},
        }
        if kind == "E31":
            payload["idDoc"]["sequenceDueDate"] = "31-12-2028"
            payload["buyer"] = {
                "rnc": fake.numerify("1########"),
                "companyName": fake.company(),
            }
            payload["totals"] = {
                "i1AmountTaxed": 56.80,
                "totalTaxedAmount": 56.80,
                "itbis1Total": 10.22,
                "itbisS1": 18,
                "itbisTotal": 10.22,
                "totalAmount": 67.02,
            }
            payload["itemDetails"][0].update(
                unitPriceItem=56.80,
                itemAmount=56.80,
                goodServiceIndicator=1,
                itemCodeTable=[{"codeType": "INT", "itemCode": "SYNTHETIC"}],
                otherCurrencyDetail={
                    "amountItemOtherCurrency": 1,
                    "discountOtherCurrency": 0,
                    "priceOtherCurrency": 1,
                    "surchargeAnotherCurrency": 0,
                },
            )
            payload["otherCurrency"] = {
                "amountTaxed1OtherCurrency": 1,
                "currencyType": "USD",
                "exchangeRate": 56.80,
                "itbis1TotalOtherCurrency": 0.18,
                "itbisTotalOtherCurrency": 0.18,
                "totalAmountOtherCurrency": 1.18,
                "totalTaxedAmountOtherCurrency": 1,
            }
        data = dict(
            case_id="local-" + kind.lower(),
            document_key=str(uuid4()),
            business_id=business_id or uuid4(),
            account_key="local-fixture",
            company_id=str(uuid4()),
            issuer=issuer,
            kind=kind,
            number=number,
            fixture_revision="synthetic-v1",
            fixture_digest=digest(payload),
            payload_digest=digest(payload),
            payload=payload,
        )
        data.update(changes)
        return Case(**data)

    return create


class FakeProvider:
    def __init__(self, case):
        self.case = case
        self.calls = 0
        self.reads = 0
        self.provider_id = uuid4().hex[:26].upper()
        self.fail_create = False
        self.response_changes = {}
        self.fail_artifact = False
        self.entered = None
        self.resume = None

    def event(self, source="response", **changes):
        data = dict(
            source=source,
            provider_id=self.provider_id,
            issuer=self.case.issuer,
            number=self.case.number,
            processing="FINISHED",
            legal="ACCEPTED",
            xml="available",
            pdf="available",
            xml_url="https://storage.example.test/fiscal.xml",
            pdf_url="https://storage.example.test/fiscal.pdf",
        )
        data.update(changes)
        return Observation(**data)

    async def create(self, case):
        self.calls += 1
        if self.entered:
            self.entered.set()
            await self.resume.wait()
        if self.fail_create:
            raise ProviderError("http_uncertain")
        return self.event(**self.response_changes)

    async def status(self, case, provider_id):
        self.reads += 1
        return self.event("poll")

    async def artifact(self, case, provider_id, kind, url):
        if self.fail_artifact:
            raise ProviderError("artifact_invalid")
        return b"%PDF-1.7\n%%EOF"


@dataclass
class Lane:
    service: Service
    store: Store
    provider: FakeProvider
    case: Case
    owner: TrustedActor
    member: TrustedActor
    grant: UUID
    member_grant: UUID


@pytest.fixture
def lane(users, case_factory, request):
    if not shared.DSN:
        pytest.skip("Disposable database required")
    with Connection.connect(shared.DSN) as db:
        business = space(db, users["owner"])
        grants = []
        for user, capabilities in (
            (users["owner"], ["read", "prepare", "approve"]),
            (users["other"], ["read", "prepare"]),
        ):
            grants.append(
                db.execute(
                    "insert into public.business_client_grants(space_id,grantee_id,issuer_id,capabilities) values(%s,%s,%s,%s) returning id",
                    (business, user, users["owner"], capabilities),
                ).fetchone()[0]
            )
    with ConnectionPool(shared.DSN, min_size=0, max_size=8) as pool:
        case = case_factory(business, kind=getattr(request, "param", "E32"))
        store, provider = Store(pool), FakeProvider(case)
        settings = Settings(
            enabled=True,
            contact_enabled=True,
            business_id=str(business),
            callback_secret="synthetic-callback-only",
        )
        yield Lane(
            Service(store, provider, settings, {case.case_id: case}),
            store,
            provider,
            case,
            TrustedActor(actor_id=users["owner"], space_id=business, actor_kind="member"),
            TrustedActor(actor_id=users["other"], space_id=business, actor_kind="member"),
            *grants,
        )
