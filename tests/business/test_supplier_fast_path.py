"""Supplier fast path mapping, receipt-date NCF check, and the off flag."""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
import yaml
from argus.domain.business.supplier_fast_path import (
    SupplierFastPath,
    SupplierFastPathDisabled,
    SupplierRegistryHit,
    lookup_supplier_fast_path,
    map_registry_status,
    ncf_valid_on_issue_date,
    supplier_fast_path_enabled,
)

ROOT = Path(__file__).resolve().parents[2]
FLAG = "CUADRAO_BUSINESS_SUPPLIER_FAST_PATH_ENABLED"
NOTICE = (
    "La DGII puede no aceptar el ITBIS de esta factura, por eso quedó fuera del 606. "
    "Si ya lo confirmaste con el suplidor, puedes incluirla."
)
INVALID = "Este comprobante no es válido. Pide al suplidor uno nuevo."
NO_DUE = "Sin fecha de vencimiento"
EXCLUDED = {
    "suspendido",
    "dado_de_baja",
    "cese_temporal",
    "anulado",
    "rechazado",
}
CHECKED_AT = datetime(2026, 10, 18, 15, 0, tzinfo=timezone.utc)


class _Cursor:
    def __init__(self, lookup_row, loaded: bool) -> None:
        self.lookup_row = lookup_row
        self.loaded = loaded
        self.calls = 0

    def __enter__(self) -> _Cursor:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, query: str, params: tuple | None = None) -> None:
        self.calls += 1
        self._call = self.calls
        self.last_params = params

    def fetchone(self):
        if self._call == 1:
            return self.lookup_row
        return (self.loaded,)


class _Connection:
    def __init__(self, lookup_row=None, loaded: bool = True) -> None:
        self.cursor_obj = _Cursor(lookup_row, loaded)

    def cursor(self) -> _Cursor:
        return self.cursor_obj


class _Exploding:
    def cursor(self):
        raise AssertionError("flag off touched the database")


class _Broken:
    def cursor(self):
        raise RuntimeError("database unavailable")


def _enable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(FLAG, "true")


@pytest.mark.parametrize(
    ("raw", "mapped", "label"),
    [
        ("ACTIVO", "verificado", None),
        (" activo ", "verificado", None),
        ("activo", "verificado", None),
        ("Activo", "verificado", None),
        ("SUSPENDIDO", "suspendido", "Suplidor suspendido en la DGII"),
        (" suspendido ", "suspendido", "Suplidor suspendido en la DGII"),
        ("Suspendido", "suspendido", "Suplidor suspendido en la DGII"),
        ("DADO DE BAJA", "dado_de_baja", "Suplidor dado de baja en la DGII"),
        ("  dado de baja", "dado_de_baja", "Suplidor dado de baja en la DGII"),
        ("CESE TEMPORAL", "cese_temporal", "Suplidor en cese temporal en la DGII"),
        ("cese temporal", "cese_temporal", "Suplidor en cese temporal en la DGII"),
        ("ANULADO", "anulado", "RNC anulado en la DGII"),
        ("Anulado", "anulado", "RNC anulado en la DGII"),
        ("RECHAZADO", "rechazado", "RNC rechazado en la DGII"),
        ("rechazado", "rechazado", "RNC rechazado en la DGII"),
        ("EN TRAMITE", "desconocido", None),
        ("", "desconocido", None),
    ],
)
def test_map_registry_status_keeps_known_rows_and_an_unseen_value(
    raw: str, mapped: str, label: str | None
) -> None:
    info = map_registry_status(raw)

    assert info.status == mapped
    assert info.label == label
    if mapped in EXCLUDED:
        assert info.notice == NOTICE
    else:
        assert info.notice is None


def test_flag_is_default_off_in_the_four_declaration_files() -> None:
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    profile = json.loads(
        (ROOT / ".github" / "private-alpha-release-profile.json").read_text(
            encoding="utf-8"
        )
    )
    manifest = json.loads(
        (ROOT / "scripts" / "ops" / "staging_env_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    render_config = yaml.safe_load((ROOT / "render.yaml").read_text(encoding="utf-8"))
    render_api = next(
        service for service in render_config["services"] if service["name"] == "cuadrao-api"
    )
    render_values = {
        item["key"]: item.get("value") for item in render_api["envVars"]
    }
    manifest_values = {
        entry["name"]: entry["value"]
        for entry in manifest["services"]["api"]["entries"]
        if "value" in entry
    }

    assert re.search(rf"^{FLAG}=false$", env_example, re.M)
    assert profile["services"]["api"]["env"][FLAG] == "false"
    assert render_values[FLAG] == "false"
    assert manifest_values[FLAG] == "false"


def test_flag_off_does_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(FLAG, raising=False)
    monkeypatch.delenv("ARGUS_BUSINESS_SUPPLIER_FAST_PATH_ENABLED", raising=False)

    result = lookup_supplier_fast_path(
        _Exploding(),
        rnc="109990011",
        ncf="not-an-ncf",
        issue_date=date(2024, 1, 15),
        vencimiento=date(2024, 12, 31),
        checked_at=CHECKED_AT,
    )

    assert isinstance(result, SupplierFastPathDisabled)
    assert result.outcome == "disabled"
    assert supplier_fast_path_enabled() is False


def test_unrecognized_flag_value_stays_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(FLAG, "enabled")

    assert supplier_fast_path_enabled() is False


def test_flag_on_returns_raw_status_beside_the_mapping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable(monkeypatch)
    connection = _Connection(
        ("109990011", "Taller Sol", " SUSPENDIDO ", date(2026, 10, 1))
    )

    result = lookup_supplier_fast_path(
        connection,
        rnc="109990011",
        ncf="B0100000099",
        issue_date=date(2024, 1, 15),
        vencimiento=None,
        checked_at=CHECKED_AT,
    )

    assert isinstance(result, SupplierFastPath)
    assert isinstance(result.registry, SupplierRegistryHit)
    assert result.registry.outcome == "found"
    assert result.registry.rnc == "109990011"
    assert result.registry.name == "Taller Sol"
    assert result.registry.raw_status == " SUSPENDIDO "
    assert result.registry.mapped.status == "suspendido"
    assert result.registry.mapped.label == "Suplidor suspendido en la DGII"
    assert result.registry.mapped.notice == NOTICE
    assert result.registry.file_date == date(2026, 10, 1)
    assert result.registry.checked_at == CHECKED_AT
    assert result.ncf.valid is True
    assert result.ncf.note == NO_DUE
    assert connection.cursor_obj.calls == 1


def test_empty_registry_is_not_loaded_and_a_miss_is_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable(monkeypatch)

    empty = lookup_supplier_fast_path(
        _Connection(None, loaded=False),
        rnc="109990099",
        ncf="B0100000099",
        issue_date=date(2024, 1, 15),
        vencimiento=date(2024, 12, 31),
        checked_at=CHECKED_AT,
    )
    missing = lookup_supplier_fast_path(
        _Connection(None, loaded=True),
        rnc="109990099",
        ncf="B0100000099",
        issue_date=date(2024, 1, 15),
        vencimiento=date(2024, 12, 31),
        checked_at=CHECKED_AT,
    )

    assert isinstance(empty, SupplierFastPath)
    assert empty.registry.outcome == "not_loaded"
    assert empty.registry.rnc == "109990099"
    assert empty.registry.checked_at == CHECKED_AT
    assert isinstance(missing, SupplierFastPath)
    assert missing.registry.outcome == "not_found"


def test_database_errors_still_propagate(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable(monkeypatch)

    with pytest.raises(RuntimeError, match="database unavailable"):
        lookup_supplier_fast_path(
            _Broken(),
            rnc="109990011",
            ncf="B0100000099",
            issue_date=date(2024, 1, 15),
            vencimiento=None,
            checked_at=CHECKED_AT,
        )


@pytest.mark.parametrize(
    ("ncf", "issued", "due", "valid", "note"),
    [
        ("nope", date(2024, 1, 15), None, False, INVALID),
        ("", date(2024, 1, 15), None, False, INVALID),
        ("B01", date(2024, 1, 15), None, False, INVALID),
        ("B1600000001", date(2024, 1, 15), None, False, INVALID),
        ("E32", date(2024, 1, 15), None, False, INVALID),
        ("B0100000099", date(2024, 1, 15), date(2024, 6, 1), True, None),
        ("B0100000099", date(2024, 6, 1), date(2024, 6, 1), True, None),
        ("b0100000099", date(2024, 6, 2), date(2024, 6, 1), False, INVALID),
        ("B0100000099", date(2024, 1, 15), None, True, NO_DUE),
        ("E320000001234", date(2020, 1, 1), date(2020, 1, 2), True, NO_DUE),
        ("e320000001234", date(2024, 6, 2), None, True, NO_DUE),
    ],
)
def test_ncf_valid_on_the_receipt_issue_date(
    ncf: str,
    issued: date,
    due: date | None,
    valid: bool,
    note: str | None,
) -> None:
    result = ncf_valid_on_issue_date(ncf, issued, due)

    assert result.valid is valid
    assert result.note == note


def _freeze_clock(monkeypatch: pytest.MonkeyPatch, today: date) -> None:
    real_datetime = datetime

    class FrozenDate(date):
        @classmethod
        def today(cls) -> date:
            return today

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz: timezone | None = None) -> datetime:
            return real_datetime(today.year, today.month, today.day, tzinfo=tz)

    monkeypatch.setattr(
        "argus.domain.business.supplier_fast_path.date",
        FrozenDate,
    )
    monkeypatch.setattr(
        "argus.domain.business.supplier_fast_path.datetime",
        FrozenDateTime,
    )


def test_ncf_check_ignores_a_clock_frozen_far_in_the_future(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _freeze_clock(monkeypatch, date(2099, 6, 1))
    still_valid = ncf_valid_on_issue_date(
        "B0100000099",
        date(2024, 1, 15),
        date(2024, 12, 31),
    )

    _freeze_clock(monkeypatch, date(2020, 1, 1))
    expired_on_issue = ncf_valid_on_issue_date(
        "B0100000099",
        date(2024, 7, 1),
        date(2024, 6, 1),
    )

    assert still_valid.valid is True
    assert still_valid.note is None
    assert expired_on_issue.valid is False
    assert expired_on_issue.note == INVALID
