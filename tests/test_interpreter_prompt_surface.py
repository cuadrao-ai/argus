import json
from pathlib import Path

import pytest
from argus.agent_runtime.business.interpretation import business_interpretation_prompt
from argus.domain.business.tools.declarations import get_business_declarations

from tests.interpreter_prompt_surface import (
    BUSINESS_DECLARATION_OWNER,
    model_facing_surface,
)


def _write(root: Path, name: str, source: str) -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")


def test_inline_readout_system_prompt_changes_its_fingerprint(tmp_path: Path) -> None:
    owner = "src/argus/agent_runtime/stages/explain.py"
    source = 'messages = [{"role": "system", "content": "Explain the ride."}]'
    _write(tmp_path, owner, source)
    first = model_facing_surface(tmp_path)
    assert owner in first
    _write(tmp_path, owner, source.replace("ride", "drawdown"))
    assert model_facing_surface(tmp_path)[owner] != first[owner]


def test_breakdown_prompt_and_schema_are_covered_without_other_api_prose(
    tmp_path: Path,
) -> None:
    owner = "src/argus/api/chat/breakdown.py"
    source = """
def messages():
    return [{"role": "system", "content": "Explain the stored result."}]
class Draft:
    text = Field(description="Complete grounded explanation.")
"""
    _write(tmp_path, owner, source)
    _write(tmp_path, "src/argus/api/chat/unrelated.py", source)
    first = model_facing_surface(tmp_path)
    assert set(first) == {owner}
    assert first[owner]["entries"] == 2
    _write(tmp_path, owner, source.replace("Complete grounded", "Concise grounded"))
    assert model_facing_surface(tmp_path)[owner] != first[owner]


def test_unrelated_inline_runtime_dictionary_does_not_expand_fingerprint(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "src/argus/agent_runtime/unrelated.py",
        'data = {"role": "system", "content": "Not a readout owner."}',
    )
    assert model_facing_surface(tmp_path) == {}


def test_shared_readout_instruction_constant_is_fingerprinted(tmp_path: Path) -> None:
    owner = "src/argus/domain/result_readout_grounding.py"
    source = 'READOUT_GROUNDING_INSTRUCTIONS = "Use stored figures only."'
    _write(tmp_path, owner, source)
    first = model_facing_surface(tmp_path)
    assert owner in first
    _write(tmp_path, owner, source.replace("stored figures", "supplied numbers"))
    assert model_facing_surface(tmp_path)[owner] != first[owner]


@pytest.mark.parametrize(
    "owner,name",
    [
        (
            "src/argus/domain/result_readout_grounding.py",
            "READOUT_RUN_GROUNDING_INSTRUCTIONS",
        ),
        (
            "src/argus/domain/result_readout_grounding.py",
            "READOUT_GROUNDING_INSTRUCTIONS",
        ),
        ("src/argus/domain/result_readout_sources.py", "BREAKDOWN_SOURCE_INSTRUCTIONS"),
    ],
)
def test_each_readout_instruction_fragment_remains_measured(
    tmp_path: Path, owner: str, name: str
) -> None:
    source = f'{name} = SHARED_TEXT + "Keep run and source figures separate."'
    _write(tmp_path, owner, source)
    first = model_facing_surface(tmp_path)
    assert owner in first
    _write(tmp_path, owner, source.replace("separate", "distinct"))
    assert model_facing_surface(tmp_path)[owner] != first[owner]


@pytest.mark.parametrize(
    "owner",
    [
        "src/argus/domain/result_readout_fact_sheet.py",
        "src/argus/domain/result_readout_fact_definitions.py",
    ],
)
def test_readout_fact_meanings_are_measured_but_docstrings_are_not(
    tmp_path: Path, owner: str
) -> None:
    source = '''"""Internal implementation notes."""
FACT_DEFINITIONS = {"executed_fills": ("count", "Executed fills, not closed trades.")}
def build():
    """Implementation detail."""
    return {"meaning": "Annualized volatility."}
'''
    _write(tmp_path, owner, source)
    first = model_facing_surface(tmp_path)
    assert owner in first
    _write(tmp_path, owner, source.replace("Annualized volatility", "Daily volatility"))
    assert model_facing_surface(tmp_path)[owner] != first[owner]
    _write(tmp_path, owner, source.replace("Implementation detail", "Private helper"))
    assert model_facing_surface(tmp_path)[owner] == first[owner]


def _business_declaration_source() -> str:
    root = Path(__file__).resolve().parents[1]
    return (root / BUSINESS_DECLARATION_OWNER).read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "description",
    [declaration.description for declaration in get_business_declarations()],
)
def test_each_business_tool_description_changes_its_fingerprint(
    tmp_path: Path, description: str
) -> None:
    source = _business_declaration_source()
    literal = json.dumps(description)
    assert source.count(literal) == 1
    _write(tmp_path, BUSINESS_DECLARATION_OWNER, source)
    first = model_facing_surface(tmp_path)
    assert first[BUSINESS_DECLARATION_OWNER]["entries"] == 7
    changed = source.replace(literal, json.dumps(description + " Changed wording."))
    _write(tmp_path, BUSINESS_DECLARATION_OWNER, changed)
    assert (
        model_facing_surface(tmp_path)[BUSINESS_DECLARATION_OWNER]
        != first[BUSINESS_DECLARATION_OWNER]
    )


@pytest.mark.parametrize(
    "unmeasured", ["business_context_required", "business.action", "business_action"]
)
def test_business_handler_and_card_text_do_not_change_prompt_fingerprint(
    tmp_path: Path, unmeasured: str
) -> None:
    source = _business_declaration_source()
    literal = json.dumps(unmeasured)
    assert literal in source
    _write(tmp_path, BUSINESS_DECLARATION_OWNER, source)
    first = model_facing_surface(tmp_path)
    _write(
        tmp_path,
        BUSINESS_DECLARATION_OWNER,
        source.replace(literal, json.dumps(unmeasured + "_changed")),
    )
    assert model_facing_surface(tmp_path) == first


def test_measured_business_descriptions_reach_the_actual_prompt(tmp_path: Path) -> None:
    declarations = get_business_declarations()
    assert len(declarations) == 7
    prompt = business_interpretation_prompt({})[0]["content"]
    assert all(declaration.description in prompt for declaration in declarations)
    _write(tmp_path, BUSINESS_DECLARATION_OWNER, _business_declaration_source())
    assert model_facing_surface(tmp_path)[BUSINESS_DECLARATION_OWNER]["entries"] == len(
        declarations
    )
