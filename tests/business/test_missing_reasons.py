"""One vocabulary names what a document still needs.

Registros (`readiness()`) and the Bandeja (`ListoGap`) both take their codes
from the registry, and the locales hold words for exactly the reasons the
server can send.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date
from typing import get_args

import pytest
from argus.domain.business import missing_reasons
from argus.domain.business.accepted_dates import reader_date_reason
from argus.domain.business.bandeja_group import ListoGap
from argus.domain.business.contracts.facts import Unknown
from argus.domain.business.dgii_606_rules import RULES
from argus.domain.business.dgii_export import line_assessments
from argus.domain.business.dgii_line import ISSUE_REASON
from argus.domain.business.missing_reasons import (
    DETAIL_MISSING,
    REASONS,
    REGISTROS_WORDS,
)
from argus.domain.business.reporting_projection import (
    BLOCKER_REASON,
    with_export_verdicts,
)
from argus.domain.business.reporting_query import ReportRecord

from scripts import generate_records_file_words
from tests.dgii import test_606_rule_table as table

LOCALES = ("es-419", "en")


def locale(language: str) -> dict:
    path = generate_records_file_words.LOCALES / language / "common.json"
    return json.loads(path.read_text(encoding="utf-8"))


def words_at(language: str, path: str):
    value = locale(language)
    for part in path.split("."):
        value = value.get(part) if isinstance(value, dict) else None
    return value


def registros_codes() -> set[str]:
    return {
        code
        for code, reason in REASONS.items()
        if reason.words == f"{REGISTROS_WORDS}.{code}"
    }


def judged(records, *, blockers: tuple[str, ...] = ()) -> ReportRecord:
    """The first record's Registros row, through the live readiness path."""

    verdicts = line_assessments(records, rnc=table.FILER, captured_on=table.TODAY)
    rows = tuple(
        ReportRecord(
            row_id=f"activity:{subject.activity_id}",
            linked_activity_ids=(subject.activity_id,),
            revision=1,
            report_date=subject.occurred_on,
            date_basis="document_issue",
            family="purchase",
            stage="ready_for_export",
            currency="DOP",
            gross_amount=subject.amount,
            money_kind=subject.kind,
            workflow_blockers=blockers,
        )
        for subject in records
    )
    return with_export_verdicts(rows, verdicts, frozenset())[0]


def without(subject, name: str):
    return replace(
        subject, declaration=subject.declaration.model_copy(update={name: None})
    )


def unread(subject, name: str):
    facts = subject.facts
    if name == "occurred_on":
        return replace(subject, facts=facts.model_copy(update={name: Unknown()}))
    fiscal = facts.fiscal.model_copy(update={name: Unknown()})
    return replace(subject, facts=facts.model_copy(update={"fiscal": fiscal}))


#: A record that makes the server send each word the rule table's cases do not.
SENT = {
    "expense_type_missing": lambda: judged((without(table.record(), "category"),)),
    "payment_method_missing": lambda: judged(
        (without(table.record(), "payment_method"),)
    ),
    "missing_rnc": lambda: judged((table.record(party=None),)),
    "invalid_rnc": lambda: judged((table.record(party="101000021"),)),
    "missing_ncf": lambda: judged((unread(table.record(), "ncf"),)),
    "missing_date": lambda: judged((unread(table.record(), "occurred_on"),)),
    "duplicate": lambda: judged((table.record(),), blockers=("possible_duplicate",)),
}


def sent_by_the_server() -> set[str]:
    cases = table.HELD + table.NAMED + table.BEYOND_A_CELL
    found = {code for case in cases for code in judged(case.records).missing}
    for code, row in SENT.items():
        missing = row().missing
        assert code in missing, (code, missing)
        found.update(missing)
    return found


class TestTheRegistry:
    def test_every_reason_readiness_can_send_is_registered(self):
        emitted = (
            set(ISSUE_REASON.values())
            | {rule.message_key for rule in RULES}
            | set(BLOCKER_REASON.values())
            | {DETAIL_MISSING}
        )
        assert emitted <= registros_codes()

    def test_a_code_outside_the_registry_is_refused(self):
        with pytest.raises(KeyError):
            missing_reasons.registered(["not_a_reason"])

    def test_every_listo_gap_is_a_registered_reason(self):
        assert set(get_args(ListoGap)) <= set(REASONS)

    @pytest.mark.parametrize("language", LOCALES)
    def test_every_reason_has_words(self, language):
        wordless = [
            code
            for code, reason in REASONS.items()
            if not isinstance(words_at(language, reason.words), str)
        ]
        assert wordless == []

    @pytest.mark.parametrize("language", LOCALES)
    def test_the_registros_words_hold_no_reason_the_registry_lacks(self, language):
        assert set(words_at(language, REGISTROS_WORDS)) == registros_codes()

    def test_every_registros_word_is_one_the_server_sends(self):
        assert sent_by_the_server() == registros_codes()

    def test_a_606_rule_and_its_reason_name_the_same_field(self):
        apart = [
            rule.id for rule in RULES if REASONS[rule.message_key].field != rule.field
        ]
        assert apart == []

    def test_the_server_reads_the_words_the_locale_holds(self):
        assert missing_reasons.words("missing_rnc", "es-419") == "Falta el RNC"
        assert missing_reasons.words("missing_rnc", "en") == "RNC is missing"


class TestADateTheBusinessAcceptsCanBeTooOldForItsNcf:
    def test_a_b_series_invoice_dated_before_the_series_is_held(self):
        subject = table.record(occurred=date(2018, 4, 30))
        assert reader_date_reason(subject.occurred_on) is None
        assert judged((subject,)).missing == ("date_too_old",)


class TestAPersonalRow:
    """The 606 leaves a Personal purchase out, so its fiscal gaps are not
    Faltan datos. Only a blocker makes it so."""

    def personal(self):
        bare = without(without(table.record(party=None), "category"), "payment_method")
        return replace(unread(bare, "ncf"), personal=True, include_606=False)

    def test_fiscal_gaps_do_not_make_it_faltan_datos(self):
        row = judged((self.personal(),))
        assert (row.ready, row.missing) == (True, ())

    def test_a_blocker_makes_it_faltan_datos(self):
        row = judged((self.personal(),), blockers=("possible_duplicate",))
        assert (row.ready, row.missing) == (False, ("duplicate",))
