"""The dossier shares one register answer with its review flags and Bandeja."""

from __future__ import annotations

import pytest
from psycopg import Cursor

from tests import test_business_dossier_standing_postgres as standing
from tests import test_business_listos_postgres as listos

pytestmark = listos.pytestmark
people = listos.people
rig = listos.rig
register = standing.register


def _register_reads(monkeypatch) -> list[str]:
    statements = []
    execute = Cursor.execute

    def count(cursor, query, *args, **kwargs):
        if "public.dgii_rnc" in str(query):
            statements.append(query)
        return execute(cursor, query, *args, **kwargs)

    monkeypatch.setattr(Cursor, "execute", count)
    return statements


@pytest.mark.parametrize(
    ("publisher_status", "display", "listed"),
    [
        ("ACTIVO", "verificado", True),
        (" activo ", "verificado", True),
        ("\tACTIVO\t", "desconocido", True),
        ("SUSPENDIDO", "suspendido", True),
        ("DADO DE BAJA", "dado_de_baja", True),
        ("CESE TEMPORAL", "cese_temporal", True),
        ("ANULADO", "anulado", True),
        ("RECHAZADO", "rechazado", True),
        ("EN TRAMITE", "desconocido", True),
        (None, "not_found", False),
        (None, None, False),
    ],
)
def test_one_register_read_serves_both_the_dossier_status_and_the_bandeja_rule(
    rig, register, monkeypatch, publisher_status, display, listed
):
    if listed:
        register(listos.BAD_CHECK_DIGIT, publisher_status)
    elif display == "not_found":
        register(standing.LISTED, "ACTIVO")
    receipt = listos._read(rig, {"rnc": listos.BAD_CHECK_DIGIT})
    group = listos._row(rig, receipt)["bandeja_group"]
    statements = _register_reads(monkeypatch)
    dossier = standing._dossier(rig, group["draft_id"])

    assert dossier["rnc_registry_status"] == display
    assert dossier["bandeja_group"]["reason"] == group["reason"] == (
        None if listed else "invalid_rnc"
    )
    assert {flag["code"] for flag in dossier["review_flags"]} == (
        set() if listed else {"rnc_check_digit"}
    )
    assert len(statements) == 1, statements


def test_a_dossier_with_no_rnc_does_not_read_the_register(rig, monkeypatch):
    receipt = listos._read(rig, {"rnc": None})
    group = listos._row(rig, receipt)["bandeja_group"]
    statements = _register_reads(monkeypatch)
    dossier = standing._dossier(rig, group["draft_id"])

    assert dossier["rnc_registry_status"] is None
    assert dossier["bandeja_group"]["reason"] == group["reason"] == "missing_rnc"
    assert dossier["review_flags"] == []
    assert statements == []
