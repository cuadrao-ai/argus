import json
from pathlib import Path

import pytest
from argus.domain.business.phone import PhoneRefused, display_phone, national_phone
from argus.domain.business.phone_area_codes import PHONE_AREA_CODES

CASES = json.loads(Path(__file__).with_name("phone_rule_cases.json").read_text())


@pytest.mark.parametrize("case", CASES, ids=lambda case: repr(case["input"]))
def test_the_phone_rule_answers_each_agreed_case(case):
    try:
        answer = {"result": "valid", "display": display_phone(case["input"])}
    except PhoneRefused as refused:
        answer = {"result": refused.reason}
    assert answer == {key: case[key] for key in case if key != "input"}


def test_the_agreed_cases_cover_every_answer():
    assert {case["result"] for case in CASES} == {
        "valid",
        "empty",
        "length",
        "format",
        "region",
    }


def test_a_valid_number_is_its_ten_national_digits():
    assert national_phone("+1 (809) 555-0142") == "8095550142"
    assert national_phone("1-212-555-0100") == "2125550100"


def test_area_codes_are_dominican_and_united_states_only():
    assert {"809", "829", "849", "212", "787"} <= PHONE_AREA_CODES
    assert PHONE_AREA_CODES.isdisjoint({"416", "876", "800", "211"})
    assert all(len(code) == 3 and code.isdecimal() for code in PHONE_AREA_CODES)
