"""Postgres proof for the supplier fast path against a local registry."""

from __future__ import annotations

import os
from datetime import date, datetime, timezone

import pytest
from argus.domain.business.supplier_fast_path import (
    SupplierFastPath,
    SupplierRegistryHit,
    SupplierRegistryMiss,
    lookup_supplier_fast_path,
)
from faker import Faker

DSN = os.getenv("ARGUS_DISPOSABLE_DATABASE_URL", "").strip()
pytestmark = pytest.mark.skipif(
    not DSN,
    reason="ARGUS_DISPOSABLE_DATABASE_URL is not configured",
)
psycopg = pytest.importorskip("psycopg")

fake = Faker()
Faker.seed(20261018)

REGISTRY = "public.dgii_rnc"
FILE_DATE = date(2026, 10, 1)
CHECKED_AT = datetime(2026, 10, 18, 15, 0, tzinfo=timezone.utc)
NOTICE = (
    "La DGII puede no aceptar el ITBIS de esta factura, por eso quedó fuera del 606. "
    "Si ya lo confirmaste con el suplidor, puedes incluirla."
)
FLAG = "CUADRAO_BUSINESS_SUPPLIER_FAST_PATH_ENABLED"


def _empty(connection) -> None:
    with connection.cursor() as cursor:
        cursor.execute("reset role")
        cursor.execute(f"truncate table {REGISTRY}")


@pytest.fixture()
def connection(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(FLAG, "true")
    with psycopg.connect(DSN, autocommit=True) as conn:
        _empty(conn)
        yield conn
        _empty(conn)


def _insert(connection, rnc: str, status: str) -> str:
    name = fake.company()
    with connection.cursor() as cursor:
        cursor.execute(
            f"insert into {REGISTRY} (rnc, name, trade_name, status, file_date) "
            "values (%s, %s, %s, %s, %s)",
            (rnc, name, None, status, FILE_DATE),
        )
    return name


def _lookup(connection, rnc: str, ncf: str = "B0100000099"):
    return lookup_supplier_fast_path(
        connection,
        rnc=rnc,
        ncf=ncf,
        issue_date=date(2024, 1, 15),
        vencimiento=date(2024, 12, 31),
        checked_at=CHECKED_AT,
    )


def test_activo_lookup_uses_the_registry_row(connection) -> None:
    name = _insert(connection, "109990011", "ACTIVO")

    result = _lookup(connection, "1-09-99001-1")

    assert isinstance(result, SupplierFastPath)
    assert isinstance(result.registry, SupplierRegistryHit)
    assert result.registry.outcome == "found"
    assert result.registry.rnc == "109990011"
    assert result.registry.name == name
    assert result.registry.raw_status == "ACTIVO"
    assert result.registry.mapped.status == "verificado"
    assert result.registry.mapped.label is None
    assert result.registry.mapped.notice is None
    assert result.registry.file_date == FILE_DATE
    assert result.registry.checked_at == CHECKED_AT
    assert result.ncf.valid is True


def test_suspendido_lookup_maps_the_raw_status(connection) -> None:
    name = _insert(connection, "109990012", "SUSPENDIDO")

    result = _lookup(connection, "109990012")

    assert isinstance(result, SupplierFastPath)
    assert isinstance(result.registry, SupplierRegistryHit)
    assert result.registry.name == name
    assert result.registry.raw_status == "SUSPENDIDO"
    assert result.registry.mapped.status == "suspendido"
    assert result.registry.mapped.label == "Suplidor suspendido en la DGII"
    assert result.registry.mapped.notice == NOTICE
    assert result.registry.file_date == FILE_DATE


def test_missing_rnc_is_not_found_when_a_registry_is_loaded(connection) -> None:
    _insert(connection, "109990011", "ACTIVO")

    result = _lookup(connection, "109990099")

    assert isinstance(result, SupplierFastPath)
    assert isinstance(result.registry, SupplierRegistryMiss)
    assert result.registry.outcome == "not_found"
    assert result.registry.rnc == "109990099"
    assert result.registry.checked_at == CHECKED_AT


def test_empty_registry_is_not_loaded(connection) -> None:
    result = _lookup(connection, "109990011")

    assert isinstance(result, SupplierFastPath)
    assert isinstance(result.registry, SupplierRegistryMiss)
    assert result.registry.outcome == "not_loaded"
    assert result.registry.checked_at == CHECKED_AT
