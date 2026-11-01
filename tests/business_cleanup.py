"""Remove synthetic Businesses the way the purge does.

Money rows and their evidence no longer cascade from ``spaces``
(``20261101000100_business_money_rows_restrict.sql``), so a teardown that
deletes a space must take them out first, through the purge's own deleter.
"""

from __future__ import annotations

from typing import Any

from argus.domain.business.purge import delete_money_rows


def delete_spaces(db: Any, where: str, params: tuple = ()) -> None:
    """Delete every space matching ``where`` with its money rows and evidence."""

    db.execute("set constraints all deferred")
    ids = [
        row[0]
        for row in db.execute(
            f"select id::text from public.spaces where {where}", params
        ).fetchall()
    ]
    for space in ids:
        delete_money_rows(db, space)
    db.execute("delete from public.spaces where id=any(%s::uuid[])", (ids,))
