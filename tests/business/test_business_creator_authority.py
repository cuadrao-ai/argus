"""Business permissions come from a live grant. Inventory identity reads in SQL
and comparisons in Python, including comparisons assigned before a later guard.
The inventory names record keys and custody checks by function and expression.
A new comparison in an already reviewed module still needs review.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[2] / "src" / "argus"
FIELDS = re.compile(r"\b(?:created_by|current_owner_id)\b", re.I)
PERMISSION_HELPER = re.compile(
    r"(?:authorize|authorized|can|may|permit|permits|allow|allowed|require|check_access|has_permission)(?:_|$)"
)
SQL_FIELD = re.compile(
    r"\b(?:\w+\.)?(?:created_by|current_owner_id)\b"
    r"(?:\s*(?:=|<>|!=|is\s+not|is)\s*(?:%s|[\w.]+))?",
    re.I,
)
# These receivers belong to the Personal memory and household models, whose
# owner_id is a different field. A Business context in those files is scanned.
OTHER_OWNERS = {
    "memory/contracts.py": {"self.consent_receipt", "self"},
    "memory/conversion.py": {"source_subject", "destination_subject"},
    "memory/index_policy.py": {"receipt", "record", "owner"},
    "memory/postgres_store.py": {"candidate", "owner"},
    "memory/service.py": {"record", "owner"},
    "memory/store.py": {"candidate", "owner"},
    "api/routers/personalization_memory.py": {"ctx.subject"},
    "domain/household/projection.py": {"access"},
    "domain/recording/canonical_groups.py": {"member", "group"},
}

# Each entry names the predicates or projections that use the recorded identity.
RECORD_USES = set(
    # Storage partitions, indexing, provenance and first-grant initialization.
    """
domain/business/access.py:<module> SQL select s.created_by, select s.current_owner_id
domain/business/access.py:ensure_owner_grant SQL select s.current_owner_id, select s.current_owner_id, where s.current_owner_id=%s with (list(legacy_capabilities(BusinessRole.OWNER)), space_id, owner_id)
domain/business/access.py:spaces_for SQL order by s.current_owner_id=%s
domain/business/actions/accepted_edit.py:_lock_account tx.rows('select id from public.financial_accounts where user_id=%s and owner_space_id=%s and id=%s for update', (tx.context.owner_id, tx.context.actor.space_id, account_id))
domain/business/actions/document_ledger.py:set_reversed tx.rows('update public.financial_activity_groups set reversed_at=%s where id=%s and user_id=%s and (reversed_at is null)=%s returning id', (at, activity, tx.context.owner_id, at is not None))
domain/business/actions/document_purge.py:erase SQL select s.created_by with (space_id,)
domain/business/actions/receipts.py:draft_for_receipt tx.rows("select id from public.financial_source_connections where id=%s and user_id=%s and owner_space_id=%s and status<>'disconnected'", (connection_id, tx.context.owner_id, tx.context.actor.space_id))
domain/business/actions/service.py:_attachment_context str(binding.owner_id) != user_id
domain/business/actions/service.py:_checked_attachment BusinessReceiptConsentStore().enabled(str(tx.context.actor.space_id), tx.context.owner_id, draft.business_reading_consent_id, db=tx.connection)
domain/business/actions/sources.py:attach tx.rows("select e.id from public.business_sources s join public.financial_import_observations o on o.connection_id=s.connection_id join public.financial_import_events e on e.id=o.event_id and e.owner_space_id=s.space_id where s.id=%s and s.space_id=%s and e.user_id=%s and e.id<>%s and not (e.resolution ? 'business') limit 1", (source_id, tx.context.actor.space_id, tx.context.owner_id, draft_id))
domain/business/actions/sources.py:record_source tx.rows("select id from public.financial_source_connections where id=%s and owner_space_id=%s and user_id=%s and status<>'disconnected'", (connection_id, tx.context.actor.space_id, tx.context.owner_id))
domain/business/authority.py:authorize SQL select s.created_by, select s.current_owner_id with (actor.space_id, actor.actor_id, grant_id, grant_id)
domain/business/bank/movements_store.py:_documents SQL select created_by with (space_id,)
domain/business/bank/outcomes_store.py:<module> SQL insert created_by
domain/business/export.py:_export_snapshot stored.account.user_id == context.owner_id
domain/business/lifecycle.py:_command SQL select current_owner_id with (space_id,)
domain/business/lifecycle.py:_command SQL where current_owner_id=%s with (connection.execute('select current_owner_id from public.spaces where id=%s', (space_id,)).fetchone()[0], space_id, space_id)
domain/business/lifecycle.py:_export_history SQL select created_by with (space_id,)
domain/business/receipt_consent.py:set SQL select created_by, where created_by=%s with (space_id, owner_id)
domain/business/receipt_consent.py:status_on_connection SQL select created_by, where created_by=%s with (space_id, owner_id)
domain/business/reporting_store.py:_recorded_activities stored.account.user_id == context.owner_id
domain/business/spaces.py:create SQL insert created_by, insert current_owner_id, on current_owner_id, returning created_by with (name, person_id, person_id, country, business_country(country).currency)
domain/business/spaces.py:get SQL select created_by with (space_id,)
domain/business/spaces.py:open_space SQL select created_by with (person_id,)
domain/business/spaces.py:rename SQL returning created_by with (name, space_id)
domain/business/supporting_files.py:_linked_elsewhere tx.rows('select 1 from public.financial_import_observations o join public.financial_import_events e on e.id=o.event_id where o.connection_id=any(%s) and e.owner_space_id=%s and e.user_id=%s and e.id<>%s limit 1', (uploads, tx.context.actor.space_id, tx.context.owner_id, draft_id))
domain/business/transactions.py:transaction user_id != self.context.owner_id
domain/business/transfer.py:_resolve SQL set current_owner_id=%s with (actor_id, command[1])
domain/business/transfer.py:eligibility SQL where s.current_owner_id=g.grantee_id with (grant_id, space_id, owner_id)
domain/business/workspace_postgres.py:create_additional SQL insert created_by, insert current_owner_id with (name, actor_id, actor_id, country, business_country(country).currency)
domain/business/workspace_postgres.py:create_additional SQL where current_owner_id=%s with (actor_id,)
domain/recording/owner_funds_postgres.py:transact SQL where created_by=%s with (row.owner_space_id, row.user_id)
domain/supabase_public_excerpts.py:create_public_excerpt_snapshot self.get_live_public_excerpt_for_artifact(owner_id=snapshot.owner_id, evidence_artifact_id=snapshot.evidence_artifact_id)
domain/supabase_public_excerpts.py:create_public_excerpt_snapshot self.get_live_public_excerpt_for_selection(owner_id=snapshot.owner_id, selection_key=snapshot.selection_key)
""".strip().splitlines()
    # Recheck the storage/ownership snapshot inside the transaction after authorization.
    + """
api/business_drafts.py:record live.context.owner_id != store.context.owner_id
domain/business/activity/queries.py:read_activity live.context.owner_id != context.owner_id
domain/business/bank/movements_store.py:bank_session auth.context.owner_id != context.owner_id
domain/business/export.py:_export_snapshot auth.context.owner_id != context.owner_id
domain/business/export.py:_export_snapshot current.context.owner_id != context.owner_id
domain/business/month_close_store.py:_session auth.context.owner_id != context.owner_id
domain/business/reporting_store.py:_authorized live.context.current_owner_id != context.current_owner_id
domain/business/reporting_store.py:_authorized live.context.owner_id != context.owner_id
domain/business/supporting_files.py:captured live.context.owner_id != context.owner_id
domain/business/transactions.py:transaction live.context.owner_id != context.owner_id
""".strip().splitlines()
    # Retention, deletion blockers, delivery addresses and custody bookkeeping.
    + """
domain/account_deletion/eligibility.py:<module> SQL where s.current_owner_id=%s
domain/account_deletion/service.py:_owned_spaces SQL where created_by = %s with (user_id,)
domain/business/account_deletion.py:retain SQL where created_by=%s with (user_id,)
domain/business/account_deletion.py:retain SQL where current_owner_id=%s with (user_id,)
domain/business/close_mail.py:<module> SQL fragment s.current_owner_id=o.recipient_id
domain/business/close_mail.py:enqueue_purge_reminders SQL select current_owner_id, where current_owner_id is not null with (REMINDER_AFTER, REOPEN_WINDOW)
domain/business/custody_graph.py:_rewrite old.get('owner_id') == user
domain/business/custody_graph.py:detach SQL select created_by, select current_owner_id with (space_id,)
domain/business/custody_graph.py:retained_dependencies SQL fragment created_by=%s, fragment current_owner_id=%s
domain/business/custody_objects.py:_reserve SQL select current_owner_id, where created_by=%s with (space_id, departing_user_id)
domain/business/departures.py:detach SQL select created_by, select current_owner_id, where created_by<>%s with (user_id,)
domain/business/departures.py:detach SQL set current_owner_id=null with (space,)
domain/business/purge.py:_claim SQL select created_by, select current_owner_id with (space, lifecycle.REOPEN_WINDOW)
domain/business/purge.py:_delete_graph SQL select created_by with (space, closed_at, lifecycle.REOPEN_WINDOW)
domain/business/purge.py:_delete_graph SQL where s.created_by, where s.current_owner_id with (space,)
domain/business/purge.py:_erase_objects SQL where created_by=%s with (placeholder,) * 4
""".strip().splitlines()
    # Household and beta invitation rows have their own unrelated created_by.
    + """
domain/household/invites.py:_insert SQL insert created_by with (iid, kind, hash_token(token), user_id, source_label, max_uses, now, expires_at, key, request_hash)
domain/household/invites.py:_quota SQL where created_by=%s with (user_id, user_id, self._clock())
domain/household/invites.py:_replay SQL where created_by=%s with (user_id, key)
domain/household/invites.py:revoke SQL where created_by=%s with (invitation_id, user_id)
domain/household/planning.py:project store.definition(c, b['kind'], b['definition_id'], b['owner_id'], b['retained_revision'])
domain/household/postgres.py:_require_member_row SQL select created_by with (household_id,)
domain/household/postgres.py:close SQL select created_by with (household_id,)
domain/household/postgres.py:create_household SQL insert created_by with (hid, trimmed, user_id, user_id, now)
domain/household/postgres.py:create_invitation SQL insert created_by with (invite_id, household_id, hash_token(token), user_id, now, expires)
""".strip().splitlines()
)
# W4 owns the independent phone-link/Business-role change. These existing
# expressions can disappear without an update here, and allow no new checks.
W4 = set(
    """
api/whatsapp.py:_as_owner str(context.owner_id) != str(owner_id)
api/whatsapp.py:whatsapp_receiving_available scope.acting_as_owner
domain/ingestion/whatsapp/ai_consent.py:_link SQL on s.created_by=l.destination_owner_id with (owner_id,)
domain/ingestion/whatsapp/ai_consent.py:_valid_grant authorize(connection, TrustedActor(actor_id=row['owner_id'], space_id=row['space_id'], actor_kind='member'), row['grant_id'])
domain/ingestion/whatsapp/ai_consent.py:status SQL where created_by=%s with (link[1], owner_id)
""".strip().splitlines()
)


def _reads_identity(node: ast.AST, aliases: set[str], other_owners: set[str]) -> bool:
    for part in ast.walk(node):
        if (
            isinstance(part, ast.Attribute)
            and part.attr == "owner_id"
            and ast.unparse(part.value) in other_owners
        ):
            continue
        if isinstance(part, ast.Attribute) and part.attr in {
            "owner_id",
            "current_owner_id",
            "created_by",
        }:
            return True
        if isinstance(part, ast.Name) and (
            part.id in aliases or FIELDS.fullmatch(part.id)
        ):
            return True
        if isinstance(part, ast.Constant) and part.value in (
            "created_by",
            "current_owner_id",
            "owner_id",
        ):
            return True
    return False


def _uses(source: str, relative: str = "") -> Iterator[tuple[int, str, str]]:
    other_owners = OTHER_OWNERS.get(relative, set())
    tree = ast.parse(source)
    parents = {
        child: parent
        for parent in ast.walk(tree)
        for child in ast.iter_child_nodes(parent)
    }

    def function(part: ast.AST) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
        while part in parents:
            part = parents[part]
            if isinstance(part, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return part
        return None

    def scope(part: ast.AST) -> str:
        func = function(part)
        return func.name if func else "<module>"

    # Follow simple aliases of an identity, including stringified IDs. A SQL
    # result, document, or object fetched using a storage key isn't an alias.
    aliases: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)) or node.value is None:
            continue
        value = node.value
        if (
            isinstance(value, ast.Call)
            and ast.unparse(value.func) in {"str", "UUID"}
            and value.args
        ):
            value = value.args[0]
        names = aliases.setdefault(scope(node), set())
        if isinstance(
            value, (ast.Name, ast.Attribute, ast.Subscript)
        ) and _reads_identity(value, names, other_owners):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names.update(t.id for t in targets if isinstance(t, ast.Name))
    for node in ast.walk(tree):
        name = scope(node)
        if isinstance(node, ast.Attribute) and node.attr == "acting_as_owner":
            yield node.lineno, name, ast.unparse(node)
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if isinstance(parents.get(node), ast.Expr) or not FIELDS.search(node.value):
                continue
            if re.search(r"\s|=", node.value):
                # Include every occurrence, so adding a WHERE predicate to a
                # record-only SELECT changes the signature.
                fields = []
                for match in SQL_FIELD.finditer(node.value):
                    # A write of the ownership pointer is a different use from
                    # a WHERE clause that compares it with the acting person.
                    clauses = re.findall(
                        r"\b(select|where|insert|returning|on|set|order by)\b",
                        node.value[: match.start()],
                        re.I,
                    )
                    clause = clauses[-1].lower() if clauses else "fragment"
                    fields.append(f"{clause} {match.group().lower()}")
                field_uses = ", ".join(fields)
                call = parents.get(node)
                parameters = ""
                if isinstance(call, ast.Call) and len(call.args) > 1:
                    parameters = " with " + ast.unparse(call.args[1])
                yield node.lineno, name, "SQL " + field_uses + parameters
            continue
        if isinstance(node, ast.Call):
            helper = ast.unparse(node.func).rsplit(".", 1)[-1]
            if PERMISSION_HELPER.match(helper) and _reads_identity(
                node, aliases.get(name, set()), other_owners
            ):
                yield node.lineno, name, ast.unparse(node)
        if isinstance(node, ast.Compare):
            if _reads_identity(node, aliases.get(name, set()), other_owners):
                yield node.lineno, name, ast.unparse(node)
        if isinstance(node, (ast.If, ast.IfExp, ast.While, ast.Assert)):
            predicate = node.test
        elif isinstance(node, ast.BoolOp):
            predicate = node
        elif isinstance(node, ast.Return) and node.value is not None:
            func = function(node)
            if (
                func is None
                or func.returns is None
                or ast.unparse(func.returns) != "bool"
            ):
                continue
            predicate = node.value
        else:
            continue
        for condition in _terms(predicate):
            if not isinstance(condition, ast.Compare) and _reads_identity(
                condition, aliases.get(name, set()), other_owners
            ):
                yield condition.lineno, name, ast.unparse(condition)


def _terms(node: ast.expr) -> Iterator[ast.expr]:
    if (
        isinstance(node, ast.Call)
        and ast.unparse(node.func) == "bool"
        and len(node.args) == 1
    ):
        yield from _terms(node.args[0])
    elif isinstance(node, ast.BoolOp):
        for value in node.values:
            yield from _terms(value)
    elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        yield from _terms(node.operand)
    else:
        yield node


def test_business_creator_never_decides_a_permission() -> None:
    unexpected = []
    w4_sites = W4.copy()
    for path in sorted(SOURCE.rglob("*.py")):
        source = path.read_text()
        if not re.search(r"owner_id|created_by|acting_as_owner", source, re.I):
            continue
        relative = path.relative_to(SOURCE).as_posix()
        for line, name, use in sorted(set(_uses(source, relative))):
            site = f"{relative}:{name} {use}"
            if site in w4_sites:
                w4_sites.remove(site)
            elif site not in RECORD_USES:
                unexpected.append(f"{relative}:{line} {name}  {use}")
    assert not unexpected, "\n" + "\n".join(unexpected)


@pytest.mark.parametrize(
    "body",
    [
        "return actor == str(context.owner_id)",
        "creator = actor.owner_id\n    if user == creator: return True",
        "if allowed(row['created_by']): return True",
        "if scope.current_owner_id: return True",
        "return getattr(context, 'owner_id') == str(actor)",
        "creator: str = str(ctx.owner_id)\n    original = creator\n    return original == actor",
        "return actor == created_by",
        "require_permission(actor, ctx.owner_id)",
        "allowed = can_approve(row['created_by'])\n    return allowed",
        "return has_access(getattr(ctx, 'owner_id'))",
        """return db.execute("select 1 from public.spaces where created_by=%s", (actor,))""",
    ],
)
def test_scan_identifies_creator_checks(body: str) -> None:
    assert list(_uses(f"def check() -> bool:\n    {body}"))
