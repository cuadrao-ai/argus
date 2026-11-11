from __future__ import annotations

import psycopg
from controls import URL, refuse


def main() -> None:
    with psycopg.connect(URL, autocommit=True) as db:
        db.execute('create schema reset_protected_probe')
        db.execute('create view reset_protected_probe.external_view as select id from public.reset_legacy_extra')
    refuse('protected external view', 'collateral')
    with psycopg.connect(URL, autocommit=True) as db:
        db.execute('drop view reset_protected_probe.external_view')
        db.execute('create table reset_protected_probe.external_fk '
                   '(id int references public.reset_legacy_extra(id))')
    refuse('protected automatic foreign key', 'collateral')
    with psycopg.connect(URL, autocommit=True) as db:
        db.execute('drop table reset_protected_probe.external_fk')
        db.execute('drop schema reset_protected_probe')


if __name__ == '__main__':
    main()
