"""Every public.conversations read in the search reader carries the scope fragment.

A new join that forgets it would show Business chats in Personal search, or the
reverse. The test reads the module source, lists each occurrence and fails on
the first one whose own join condition (or, for the one ``from``, whose own
``where``) lacks the fragment.
"""

from __future__ import annotations

import re
from pathlib import Path

from argus.domain import postgres_search_reader as reader
from argus.domain.owner_scope import sql_named_join_predicate

SOURCE = Path(reader.__file__).read_text(encoding="utf-8")
OCCURRENCE = re.compile(r"\b(join|from) public\.conversations as (\w+)")
ANY_READ = re.compile(r"public\.conversations\b")
# A join condition ends where the next join, where clause or template begins.
JOIN_END = re.compile(
    r"\n\s*(?:join |left join |cross join |where |\"\"\"|\)|select )",
)


def _occurrences() -> list[tuple[int, str, str]]:
    return [
        (SOURCE.count("\n", 0, match.start()) + 1, match.group(1), match.group(2))
        for match in OCCURRENCE.finditer(SOURCE)
    ]


def test_the_fragment_is_the_owner_scope_rule() -> None:
    assert reader._CONVERSATION_IN_SCOPE_TEXT == sql_named_join_predicate(
        "conversation.owner_space_id"
    )
    assert reader._CONVERSATION_IN_SCOPE.as_string() == (
        "conversation.owner_space_id is not distinct from %(owner_space_id)s::uuid"
    )


def test_every_conversations_read_names_the_fragment() -> None:
    occurrences = _occurrences()
    # Every read, in any spelling, must be one the checks below understand.
    code = "\n".join(
        line for line in SOURCE.splitlines() if not line.lstrip().startswith("#")
    )
    assert len(ANY_READ.findall(code)) == len(occurrences) == 17
    assert {alias for _, _, alias in occurrences} == {"conversation"}
    missing = []
    for match in OCCURRENCE.finditer(SOURCE):
        line = SOURCE.count("\n", 0, match.start()) + 1
        rest = SOURCE[match.end() :]
        if match.group(1) == "join":
            end = JOIN_END.search(rest)
            condition = rest[: end.start() if end else len(rest)]
            if "{conversation_in_scope}" not in condition:
                missing.append(line)
        elif not re.search(
            r"\nwhere conversation\.user_id = %\(user_id\)s\n"
            r"\s*and __CONVERSATION_IN_SCOPE__\n",
            rest,
        ):
            missing.append(line)
    assert missing == []


def test_the_rendered_hydration_sql_carries_the_rule() -> None:
    assert "__CONVERSATION_IN_SCOPE__" not in reader._CONVERSATION_HYDRATION_SQL
    assert reader._CONVERSATION_IN_SCOPE_TEXT in reader._CONVERSATION_HYDRATION_SQL
