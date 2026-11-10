"""Inventory every object the migration history creates and name who reads it.

Run against a local database built from the full migration history:

    python3 docs/reports/evidence/1890-baseline/inventory.py <database-url>

It writes inventory.md and inventory.json next to itself. Each table, view,
function and type in `public` and `argus_private` gets one class:

- kept: Cuadrao Business code reads or writes it (file:line), or a kept object
  needs it (foreign key, trigger, policy, default, check, or a call or table
  named in a kept function's body);
- unsure: no Business feature uses it, but old chat, memory, household, guest
  or private-alpha code still names it, or only the Business code that sweeps
  rows when a Business or account ends does (that code's own business_* and
  account_deletion_* tables are kept). Dropping it means editing that code
  first, so it stays in the baseline;
- removed: no code outside tests and docs names it, and nothing kept or unsure
  needs it.

Triggers, policies, indexes and constraints belong to their table.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections import defaultdict, deque
from collections.abc import Iterable
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
HISTORY_DIRS = (ROOT / "supabase/migrations_archive", ROOT / "supabase/migrations")

CODE_PATHS = (
    "src", "workflows", "scripts", "web", "marketing", "native", ".github", "supabase/seed.sql",
    ":!scripts/**/tests/**", ":!web/__tests__/**", ":!web/e2e/**", ":!**/*.test.ts",
    ":!**/*.test.tsx", ":!**/*.md", ":!web/test-fixtures/**", ":!scripts/ci/timings/**",
    ":!native/**/Tests/**", ":!web/public/locales/**",
)  # fmt: skip

BUSINESS_CODE = re.compile(
    r"^(src/argus/domain/business/"
    r"|src/argus/api/business"
    r"|src/argus/api/routers/business"
    r"|src/argus/agent_runtime/business/"
    r"|src/argus/domain/ingestion/(documents|email_intake|whatsapp)/"
    r"|src/argus/domain/ingestion/receipt_review\.py"
    r"|src/argus/api/(whatsapp|email_intake|documents)"
    r"|src/argus/api/routers/(whatsapp|email_intake|financial_documents|account|feedback)\.py"
    r"|src/argus/api/(auth_sessions|account_deletion_[a-z_]+|profile_images|age_confirmation)\.py"
    r"|src/argus/domain/account_deletion/"
    r"|src/argus/domain/profile_images/"
    r"|scripts/ops/(dgii_rnc_[a-z_]+|check_whatsapp_pilot|resume_account_deletions"
    r"|force_account_deletion_step)\."
    r"|workflows/document_"
    r"|web/)"
)

# Business code that moves or deletes rows when a Business or account ends.
# It keeps its own bookkeeping tables live; any other table it names is only swept.
LIFECYCLE_CODE = re.compile(
    r"^(src/argus/domain/business/"
    r"(custody_graph|custody_objects|purge|account_deletion|departures)\.py"
    r"|src/argus/domain/account_deletion/)"
)
LIFECYCLE_OWN = re.compile(r"^(business_|account_deletion_)")

CATALOG_SQL = """
with owned as (select oid from pg_namespace where nspname in ('public', 'argus_private')),
members as (select objid from pg_depend where deptype = 'e'),
own_funcs as (select oid from pg_proc where pronamespace in (select oid from owned))
select json_build_object(
  'relations', (select json_agg(json_build_object('oid', c.oid, 'schema', n.nspname,
      'name', c.relname, 'kind', case c.relkind when 'v' then 'view'
      when 'm' then 'materialized view' else 'table' end))
    from pg_class c join pg_namespace n on n.oid = c.relnamespace
    where c.relnamespace in (select oid from owned) and c.relkind in ('r', 'p', 'v', 'm')
      and c.oid not in (select objid from members)),
  'functions', (select json_agg(json_build_object('oid', p.oid, 'schema', n.nspname,
      'name', p.proname, 'args', pg_get_function_identity_arguments(p.oid), 'body', p.prosrc))
    from pg_proc p join pg_namespace n on n.oid = p.pronamespace
    where p.oid in (select oid from own_funcs) and p.oid not in (select objid from members)),
  'types', (select json_agg(json_build_object('oid', t.oid, 'schema', n.nspname,
      'name', t.typname, 'kind', 'type'))
    from pg_type t join pg_namespace n on n.oid = t.typnamespace
    where t.typnamespace in (select oid from owned) and t.typtype in ('e', 'd')
      and t.oid not in (select objid from members)),
  'triggers', (select json_agg(json_build_object('table', t.tgrelid, 'function', t.tgfoid))
    from pg_trigger t join pg_class c on c.oid = t.tgrelid
    where not t.tgisinternal
      and (c.relnamespace in (select oid from owned) or t.tgfoid in (select oid from own_funcs))),
  'policies', (select json_agg(json_build_object('table', p.polrelid,
      'text', coalesce(pg_get_expr(p.polqual, p.polrelid), '') || ' '
              || coalesce(pg_get_expr(p.polwithcheck, p.polrelid), '')))
    from pg_policy p join pg_class c on c.oid = p.polrelid
    where c.relnamespace in (select oid from owned)),
  'event_triggers', (select json_agg(json_build_object('name', e.evtname, 'function', e.evtfoid))
    from pg_event_trigger e where e.evtfoid in (select oid from own_funcs)),
  'depends', (select json_agg(json_build_object(
      'from', coalesce(con.conrelid, ad.adrelid, ix.indrelid, rw.ev_class, d.objid),
      'to', d.refobjid, 'how', case when con.contype = 'f' then 'foreign key'
        when con.oid is not null then 'constraint' when ad.oid is not null then 'default'
        when ix.indexrelid is not null then 'index' when rw.oid is not null then 'view'
        else 'type' end))
    from pg_depend d
    left join pg_constraint con on d.classid = 'pg_constraint'::regclass and con.oid = d.objid
    left join pg_attrdef ad on d.classid = 'pg_attrdef'::regclass and ad.oid = d.objid
    left join pg_index ix on d.classid = 'pg_class'::regclass and ix.indexrelid = d.objid
    left join pg_rewrite rw on d.classid = 'pg_rewrite'::regclass and rw.oid = d.objid
    where d.deptype = 'n'
      and d.refclassid in ('pg_class'::regclass, 'pg_proc'::regclass, 'pg_type'::regclass)),
  'extensions', (select json_agg(extname order by extname) from pg_extension where extname <> 'plpgsql'),
  'buckets', (select json_agg(id order by id) from storage.buckets),
  'cron_jobs', (select coalesce(json_agg(jobname), '[]') from cron.job)
)
"""

# Tables a library creates and reads by itself, so no repository line names them.
LIBRARY_OWNED = {
    "public.checkpoint_migrations": ["src/argus/api/app_setup.py:63 (LangGraph checkpointer setup)"],
}

PYTHON_IMPORT = re.compile(r"^\s*(from\s+\S+\s+)?import\s")


def catalog(url: str) -> dict:
    out = subprocess.run(
        ["psql", url, "-XAtc", CATALOG_SQL], check=True, capture_output=True, text=True
    ).stdout
    return json.loads(out)


def grep_pattern(name: str) -> str:
    end = "([^A-Za-z0-9_]|$)"
    if "_" in name:
        return f"(^|[^A-Za-z0-9_]){name}{end}"
    # One-word names (messages, profiles, spaces) also appear as plain words and
    # dictionary keys, so they count only in a SQL or client-call position.
    return (
        f"((public|argus_private)\\.{name}{end}"
        f"|(table|from_|rpc)\\([[:space:]]*[\"']{name}[\"']"
        f"|(from|join|into|update|truncate)[[:space:]]+{name}{end})"
    )


def code_refs(name: str) -> list[str]:
    out = subprocess.run(
        ["git", "grep", "-n", "-I", "-i", "-E", "-e", grep_pattern(name), "--", *CODE_PATHS],
        cwd=ROOT, capture_output=True, text=True,
    ).stdout  # fmt: skip
    refs = []
    for line in out.splitlines():
        path, number, text = line.split(":", 2)
        if "_" not in name and PYTHON_IMPORT.match(text):
            continue
        refs.append(f"{path}:{number}")
    return refs


def mentions(text: str, name: str) -> bool:
    return re.search(rf"(?<![A-Za-z0-9_]){re.escape(name)}(?![A-Za-z0-9_])", text) is not None


HISTORY = [
    (path.name.split("_", 1)[0], path.read_text())
    for path in sorted(
        (p for d in HISTORY_DIRS if d.is_dir() for p in d.glob("*.sql")), key=lambda p: p.name
    )
]


def created_in(obj: dict) -> str:
    keyword = "function" if obj["kind"] == "function" else "(table|view|type|domain)"
    name = re.escape(obj["name"])
    pattern = re.compile(
        rf"create\s+(or\s+replace\s+)?{keyword}\s+(if\s+not\s+exists\s+)?"
        rf"({obj['schema']}\.)?\"?{name}\"?[\s(]|rename\s+to\s+{name}\b",
        re.IGNORECASE,
    )
    return next((version for version, text in HISTORY if pattern.search(text)), "?")


def classify(cat: dict) -> dict[int, dict]:
    objects: dict[int, dict] = {}
    for group in ("relations", "functions", "types"):
        for row in cat[group] or []:
            row["kind"] = row.get("kind") or "function"
            row["key"] = f"{row['schema']}.{row['name']}" + (
                f"({row['args']})" if row["kind"] == "function" else ""
            )
            objects[row["oid"]] = row

    needs: dict[int, dict[int, str]] = defaultdict(dict)

    def edge(src: int, dst: int, how: str) -> None:
        if src in objects and dst in objects and src != dst:
            needs[src][dst] = min(how, needs[src].get(dst, how))

    for dep in cat["depends"] or []:
        edge(dep["from"], dep["to"], dep["how"])
    for trigger in cat["triggers"] or []:
        edge(trigger["table"], trigger["function"], "trigger")
    for policy in cat["policies"] or []:
        for oid, obj in objects.items():
            if mentions(policy["text"], obj["name"]):
                edge(policy["table"], oid, "policy")
    for src in objects.values():
        if src["kind"] == "function":
            for oid, obj in objects.items():
                if mentions(src["body"], obj["name"]):
                    edge(src["oid"], oid, "function body")

    # Functions fired by triggers on auth tables or by event triggers have no
    # caller in code. The guest ones belong to removed guest mode.
    platform = {t["function"] for t in cat["triggers"] or [] if t["table"] not in objects}
    platform |= {e["function"] for e in cat["event_triggers"] or []}
    for obj in objects.values():
        refs = code_refs(obj["name"]) + LIBRARY_OWNED.get(obj["key"], [])
        swept_only = LIFECYCLE_OWN.match(obj["name"]) is None
        obj["business_refs"] = [
            r for r in refs if BUSINESS_CODE.match(r) and not (swept_only and LIFECYCLE_CODE.match(r))
        ]
        obj["other_refs"] = [r for r in refs if r not in obj["business_refs"]]
        if obj["oid"] in platform:
            target = "other_refs" if "guest" in obj["name"] else "business_refs"
            obj[target] = obj[target] or ["fired by a trigger on an auth table or an event trigger"]

    def by_key(oids: Iterable[int]) -> list[int]:
        return sorted(oids, key=lambda oid: objects[oid]["key"])

    def closure(roots: set[int]) -> dict[int, tuple[int, str]]:
        """Breadth first in name order, so each owner chain is the shortest and stable across builds."""
        reached = {oid: (oid, "") for oid in roots}
        queue = deque(by_key(roots))
        while queue:
            current = queue.popleft()
            for nxt in by_key(needs[current]):
                if nxt not in reached:
                    reached[nxt] = (current, needs[current][nxt])
                    queue.append(nxt)
        return reached

    kept = closure({oid for oid, o in objects.items() if o["business_refs"]})
    named = closure({oid for oid, o in objects.items() if o["business_refs"] or o["other_refs"]})
    for oid, obj in objects.items():
        obj["created"] = created_in(obj)
        if oid in kept:
            obj["class"], (via, how), refs = "kept", kept[oid], obj["business_refs"]
        elif oid in named:
            obj["class"], (via, how), refs = "unsure", named[oid], obj["other_refs"]
        else:
            obj["class"], via, how, refs = "removed", oid, "", []
        if via != oid:
            obj["owner"] = f"needed by `{objects[via]['key']}` ({how})"
        else:
            obj["owner"] = refs[0] if refs else "no live owner"
    return objects


def write(objects: dict[int, dict], cat: dict) -> None:
    ordered = sorted(objects.values(), key=lambda o: (o["class"], o["kind"], o["key"]))
    counts: dict[tuple[str, str], int] = defaultdict(int)
    for obj in ordered:
        counts[(obj["class"], obj["kind"])] += 1
    lines = [
        "# Migration history inventory (#1890)",
        "",
        "Generated by `inventory.py` from a local database built from every file in",
        "`supabase/migrations_archive/`. Rerun the script; do not edit by hand.",
        "",
        "- **kept**: Cuadrao Business code reads or writes it, or a kept object needs it.",
        "- **unsure**: no Business feature uses it, but old chat, memory, household, guest",
        "  or private-alpha code, or only the Business code that sweeps rows when a Business",
        "  or account ends, still names it. It stays in the baseline until that code changes.",
        "- **removed**: nothing outside tests and docs names it. The baseline leaves it out.",
        "",
        "Triggers, policies, indexes and constraints belong to their table. `Created` is",
        "the version of the first file that creates the object.",
        "",
        "| Class | Kind | Count |",
        "| --- | --- | ---: |",
        *[f"| {c} | {k} | {n} |" for (c, k), n in sorted(counts.items())],
        "",
        f"Extensions: {', '.join(cat['extensions'])}.",
        f"Storage buckets: {', '.join(cat['buckets'] or [])}.",
        f"Cron jobs: {', '.join(cat['cron_jobs']) or 'none'}.",
        f"Event triggers: {', '.join(e['name'] for e in cat['event_triggers'] or [])}.",
        "",
        "| Class | Kind | Object | Created | Owner (file:line) | Other code naming it |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for obj in ordered:
        others = [r for r in obj["other_refs"] if r != obj["owner"]]
        shown = ", ".join(others[:3]) + (" ..." if len(others) > 3 else "")
        lines.append(
            f"| {obj['class']} | {obj['kind']} | `{obj['key']}` | {obj['created']} "
            f"| {obj['owner']} | {shown} |"
        )
    (HERE / "inventory.md").write_text("\n".join(lines) + "\n")
    classes = {obj["key"]: {"class": obj["class"], "kind": obj["kind"]} for obj in ordered}
    (HERE / "inventory.json").write_text(json.dumps(classes, indent=1, sort_keys=True) + "\n")


def main() -> None:
    cat = catalog(sys.argv[1])
    write(classify(cat), cat)


if __name__ == "__main__":
    main()
