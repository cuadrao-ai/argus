from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from psycopg import sql
from psycopg.rows import dict_row

from argus.api.chat.legacy_onboarding_markers import (
    legacy_onboarding_sql_filters,
)
from argus.api.schemas import SearchAssetRollup
from argus.domain.owner_scope import (
    SCOPE_PARAMETER,
    OwnerScope,
    space_id,
    sql_named_join_predicate,
)
from argus.domain.search_sql_text import (
    normalizer_expression,
    symbol_index_expression,
)
from argus.domain.search_text import (
    normalize_search_symbol,
    normalize_search_text,
    search_has_indexable_token,
    search_query_is_indexable,
)

_SEARCH_ACQUIRE_TIMEOUT_SECONDS = 2.0
# Every public.conversations read keeps one side: Personal or one Business space.
_CONVERSATION_IN_SCOPE_TEXT = sql_named_join_predicate("conversation.owner_space_id")
_CONVERSATION_IN_SCOPE = sql.SQL(_CONVERSATION_IN_SCOPE_TEXT)
_CONVERSATION_MATCH_OVERSAMPLE = 10
_MAX_CONVERSATION_MATCHES_PER_SOURCE = 1_010
_DECISION_STATES = ("promising", "watching", "rejected", "revisit_later")
_ROW_GROUP_BY_SOURCE = {
    "conversation": "conversations",
    "chat": "conversations",
    "strategy": "strategies",
    "collection": "collections",
    "run": "runs",
    "idea": "ideas",
    "evidence": "evidence",
    "decision": "decisions",
    "asset_rollup": "asset_rollups",
}
_CONVERSATION_ROW_GROUPS = tuple(
    dict.fromkeys(
        group
        for source, group in _ROW_GROUP_BY_SOURCE.items()
        if source != "asset_rollup"
    )
) + ("messages",)


class SearchCursorError(ValueError):
    """Raised when a scoped Search cursor pivot cannot be resolved exactly."""


@dataclass(frozen=True)
class SearchReadResult:
    rows: dict[str, list[dict[str, Any]]]
    ledger_counts: dict[str, int] | None = None
    asset_rollup: SearchAssetRollup | None = None


def _normalized(expression: str) -> sql.Composed:
    return normalizer_expression(sql.SQL(expression))


def _conversation_match_limit(source_limit: int) -> int:
    return min(
        source_limit * _CONVERSATION_MATCH_OVERSAMPLE,
        _MAX_CONVERSATION_MATCHES_PER_SOURCE,
    )


def _symbol_prefix_end(prefix: str | None) -> str | None:
    """Return the exclusive C-collation upper bound for one text prefix."""
    if not prefix:
        return None
    codepoints = [ord(character) for character in prefix]
    for index in range(len(codepoints) - 1, -1, -1):
        codepoint = codepoints[index]
        if codepoint >= 0x10FFFF:
            continue
        successor = codepoint + 1
        if 0xD800 <= successor <= 0xDFFF:
            successor = 0xE000
        return "".join(chr(value) for value in (*codepoints[:index], successor))
    return None


def _all_token_recheck(
    normalized_haystack: sql.Composable,
) -> sql.Composed:
    return sql.SQL(
        """
        not exists (
            select 1
            from unnest(%(token_patterns)s::text[]) as required(pattern)
            where not coalesce(
                {normalized_haystack} like required.pattern,
                false
            )
        )
        """
    ).format(normalized_haystack=normalized_haystack)


def _token_match_predicate(
    *,
    normalized_haystack: sql.Composable,
    normalized_index_haystack: sql.Composable | None,
    has_anchor: bool,
) -> sql.Composed:
    predicates: list[sql.Composable] = []
    if has_anchor and normalized_index_haystack is not None:
        predicates.append(
            sql.SQL("{} like %(anchor_pattern)s").format(
                normalized_index_haystack,
            )
        )
    predicates.append(_all_token_recheck(normalized_haystack))
    return sql.SQL(" and ").join(predicates)


_RUN_INDEX_HAYSTACK = """
    coalesce(run.conversation_result_card->>'title', '') || ' '
    || coalesce(run.conversation_result_card->'symbols', '[]'::jsonb)::text || ' '
    || coalesce(run.conversation_result_card->>'strategy_label', '') || ' '
    || coalesce(run.benchmark_symbol, '')
"""


_EVIDENCE_INDEX_HAYSTACK = """
    evidence.title || ' ' || coalesce(evidence.digest, '') || ' '
    || coalesce(
        evidence.payload#>'{result_card,symbols}',
        '[]'::jsonb
    )::text
"""
_DECISION_INDEX_HAYSTACK = """
    decision.decision_state || ' ' || coalesce(decision.note, '')
"""


@dataclass(frozen=True)
class _DecisionAttachment:
    """One owner a decision can attach to, and the text it carries."""

    alias: str
    table: str
    decision_key: str
    conversation_column: str
    text: str
    index_text: str


# A decision attaches to exactly one owner: the evidence artifact of a
# backtest, or the assistant message that carried a computed answer. Every
# decision-level read derives its joins, its searchable text, and its anchor
# discovery from this tuple, so an attachment is added here and nowhere else.
# Run-scoped counts (decided runs, asset rollups) stay on evidence lineage by
# contract: a run is decided only through its artifact.
_DECISION_ATTACHMENTS = (
    _DecisionAttachment(
        alias="evidence",
        table="public.evidence_artifacts",
        decision_key="evidence_artifact_id",
        conversation_column="source_conversation_id",
        text="concat_ws(' ', nullif(evidence.title, ''), nullif(evidence.digest, ''))",
        index_text=_EVIDENCE_INDEX_HAYSTACK,
    ),
    _DecisionAttachment(
        alias="decision_message",
        table="public.messages",
        decision_key="source_message_id",
        conversation_column="conversation_id",
        text="nullif(decision_message.content, '')",
        index_text="decision_message.content",
    ),
)


def _decision_attachment_joins(
    *, user_expression: str, exclude: str | None = None
) -> str:
    """Left joins to every attachment a decision may carry."""
    return "\n".join(
        f"""
        left join {attachment.table} as {attachment.alias}
          on {attachment.alias}.id = decision.{attachment.decision_key}
         and {attachment.alias}.user_id = {user_expression}
         and {attachment.alias}.{attachment.conversation_column}
             = decision.source_conversation_id
        """
        for attachment in _DECISION_ATTACHMENTS
        if attachment.alias != exclude
    )


def _decision_attachment_text() -> str:
    """The searchable text a decision carries through its attachment."""
    return "concat_ws(' ', " + ", ".join(a.text for a in _DECISION_ATTACHMENTS) + ")"


def _decision_haystack_text() -> str:
    return f"{_DECISION_INDEX_HAYSTACK} || ' ' || {_decision_attachment_text()}"


def _decision_matched_text() -> str:
    return (
        "concat_ws(' ', nullif(decision.note, ''), decision.decision_state, "
        + ", ".join(a.text for a in _DECISION_ATTACHMENTS)
        + ")"
    )


def _decision_match_sources(
    *,
    has_anchor: bool,
    select_list: sql.Composable,
    conversation_join: sql.Composable,
    all_tokens: sql.Composable,
) -> list[sql.Composed]:
    """One decision-match source per index a decision is discovered through.

    Without an anchor there is one scan over decisions with every attachment
    left-joined. With an anchor, the decision's own note and state and each
    attachment's indexed text discover candidates independently, and every
    branch still left-joins the other attachments so the token recheck sees
    the whole haystack.
    """
    body = sql.SQL(
        """
        select {select_list}
        from input
        {discovery}
        {conversation_join}
        where input.text_search_enabled
          and input.normalized_query <> ''
          and ({all_tokens})
        """
    )

    def source(discovery: sql.Composable) -> sql.Composed:
        return body.format(
            select_list=select_list,
            discovery=discovery,
            conversation_join=conversation_join,
            all_tokens=all_tokens,
        )

    decision_scan = sql.SQL(
        """
        join public.decision_notes as decision
          on decision.user_id = input.user_id
        """
    )
    every_attachment = sql.SQL(
        _decision_attachment_joins(user_expression="input.user_id")
    )
    if not has_anchor:
        return [source(sql.SQL("\n").join([decision_scan, every_attachment]))]
    sources = [
        source(
            sql.SQL("\n").join(
                [
                    sql.SQL(
                        """
        join public.decision_notes as decision
          on decision.user_id = input.user_id
         and {decision_index} like %(anchor_pattern)s
        """
                    ).format(decision_index=_normalized(_DECISION_INDEX_HAYSTACK)),
                    every_attachment,
                ]
            )
        )
    ]
    for attachment in _DECISION_ATTACHMENTS:
        discovery = sql.SQL(
            f"""
        join {attachment.table} as {attachment.alias}
          on {attachment.alias}.user_id = input.user_id
         and {{index_text}} like %(anchor_pattern)s
        join public.decision_notes as decision
          on decision.{attachment.decision_key} = {attachment.alias}.id
         and decision.user_id = input.user_id
         and decision.source_conversation_id
             = {attachment.alias}.{attachment.conversation_column}
        """
        ).format(index_text=_normalized(attachment.index_text))
        sources.append(
            source(
                sql.SQL("\n").join(
                    [
                        discovery,
                        sql.SQL(
                            _decision_attachment_joins(
                                user_expression="input.user_id",
                                exclude=attachment.alias,
                            )
                        ),
                    ]
                )
            )
        )
    return sources


_CONVERSATION_INPUT_CTE = sql.SQL(
    """
    input as (
        select
            %(user_id)s::uuid as user_id,
            %(normalized_query)s::text as normalized_query,
            %(symbol_query)s::text as symbol_query,
            %(symbol_prefix_end)s::text as symbol_prefix_end,
            %(source_limit)s::integer as source_limit,
            %(match_limit)s::integer as match_limit,
            %(asset_symbol_limit)s::integer as asset_symbol_limit,
            %(text_search_enabled)s::boolean as text_search_enabled,
            %(has_cursor)s::boolean as has_cursor,
            %(cursor_pinned_rank)s::integer as cursor_pinned_rank,
            %(cursor_exact_rank)s::integer as cursor_exact_rank,
            %(cursor_symbol_rank)s::integer as cursor_symbol_rank,
            %(cursor_layer_rank)s::integer as cursor_layer_rank,
            %(cursor_updated_at)s::timestamptz as cursor_updated_at,
            %(cursor_text_rank)s::integer as cursor_text_rank,
            %(cursor_id)s::uuid as cursor_id,
            %(decision_state)s::text as decision_state,
            %(guest_scope)s::boolean as guest_scope,
            %(guest_conversation_id)s::uuid as guest_conversation_id
    )
    """
)


_CONVERSATION_LEDGER_INPUT_CTE = sql.SQL(
    """
    input as (
        select
            %(user_id)s::uuid as user_id,
            %(normalized_query)s::text as normalized_query,
            %(symbol_query)s::text as symbol_query,
            %(text_search_enabled)s::boolean as text_search_enabled
    )
    """
)


_CONVERSATION_DECISION_FILTER = sql.SQL(
    """
    and (
        input.decision_state is null
        or exists (
            select 1
            from public.decision_notes as source_decision
            where source_decision.user_id = input.user_id
              and source_decision.source_conversation_id = conversation.id
              and source_decision.decision_state = input.decision_state
        )
    )
    """
)


def _run_symbol_slot(run_alias: sql.Composable, slot: int) -> sql.Composed:
    return sql.SQL("btrim({})").format(
        symbol_index_expression(
            sql.SQL("{}.symbols[{}]").format(run_alias, sql.Literal(slot))
        )
    )


def _exact_run_symbol_predicate(run_alias: sql.Composable) -> sql.Composed:
    return sql.SQL("\n or \n").join(
        sql.SQL(
            """
            (
                {run_alias}.symbols[{slot}] is not null
                and input.symbol_query collate "C"
                    = {normalized_symbol} collate "C"
            )
            """
        ).format(
            run_alias=run_alias,
            slot=sql.Literal(slot),
            normalized_symbol=_run_symbol_slot(run_alias, slot),
        )
        for slot in range(1, 6)
    )


def _conversation_match_ctes(
    *,
    has_anchor: bool,
    has_cursor: bool = False,
) -> sql.Composed:
    chat_title_haystack = _normalized("conversation.title")
    chat_preview_haystack = _normalized("coalesce(conversation.last_message_preview, '')")
    chat_index_haystack = _normalized(
        "conversation.title || ' ' " "|| coalesce(conversation.last_message_preview, '')"
    )
    message_haystack = _normalized("message.content")
    run_haystack = _normalized(
        "coalesce(run.conversation_result_card->>'title', '') || ' ' "
        "|| coalesce(array_to_string(run.symbols, ' '), '') || ' ' "
        "|| coalesce(run.config_snapshot->>'template', '') || ' ' "
        "|| coalesce(run.conversation_result_card->>'strategy_label', '')"
    )
    run_symbol_predicate = _exact_run_symbol_predicate(sql.SQL("run"))
    idea_haystack = _normalized("idea.title || ' ' || coalesce(idea.summary, '')")
    evidence_haystack = _normalized(
        "evidence.title || ' ' || coalesce(evidence.digest, '')"
    )
    decision_haystack = _normalized(_decision_haystack_text())
    decision_all_tokens = _all_token_recheck(decision_haystack)
    conversation_exact_rank = sql.SQL(
        """
        (
            input.normalized_query <> ''
            and input.normalized_query = {normalized_title}
        )::integer
        """
    ).format(normalized_title=_normalized("conversation.title"))
    conversation_symbol_rank = sql.SQL(
        """
        exists (
            select 1
            from public.backtest_runs as symbol_run
            where symbol_run.user_id = input.user_id
              and symbol_run.conversation_id = conversation.id
              and symbol_run.status = 'completed'
              and ({symbol_predicate})
        )::integer
        """
    ).format(
        symbol_predicate=_exact_run_symbol_predicate(sql.SQL("symbol_run")),
    )
    conversation_activity_query = sql.SQL(
        """
        select max(source_activity.activity_at) as activity_at
        from (
            select conversation.updated_at as activity_at
            union all
            select max(coalesce(run.updated_at, run.created_at))
            from public.backtest_runs as run
            where run.user_id = input.user_id
              and run.conversation_id = conversation.id
            union all
            select max(message.created_at)
            from public.messages as message
            where message.user_id = input.user_id
              and message.conversation_id = conversation.id
            union all
            select max(idea.updated_at)
            from public.ideas as idea
            where idea.user_id = input.user_id
              and idea.source_conversation_id = conversation.id
            union all
            select max(evidence.updated_at)
            from public.evidence_artifacts as evidence
            where evidence.user_id = input.user_id
              and evidence.source_conversation_id = conversation.id
            union all
            select max(decision.updated_at)
            from public.decision_notes as decision
            where decision.user_id = input.user_id
              and decision.source_conversation_id = conversation.id
        ) as source_activity
        """
    )
    conversation_activity_sql = sql.SQL("({activity_query})").format(
        activity_query=conversation_activity_query
    )

    def conversation_text_rank(matched_text_sql: sql.Composable) -> sql.Composed:
        return sql.SQL(
            """
            (
                case
                    when input.normalized_query <> ''
                     and strpos(
                         {normalized_title},
                         input.normalized_query
                     ) > 0
                        then 100
                    else 0
                end
                +
                case
                    when input.normalized_query <> ''
                     and strpos(
                         {normalized_matched},
                         input.normalized_query
                     ) > 0
                        then 50
                    else 0
                end
            )::integer
            """
        ).format(
            normalized_title=_normalized("conversation.title"),
            normalized_matched=normalizer_expression(matched_text_sql),
        )

    def token_predicate(
        haystack: sql.Composable,
        index_haystack: sql.Composable,
    ) -> sql.Composed:
        return _token_match_predicate(
            normalized_haystack=haystack,
            normalized_index_haystack=index_haystack,
            has_anchor=has_anchor,
        )

    def bounded_source_window(
        *,
        source_sql: sql.Composable,
        cursor_relative: bool,
    ) -> sql.Composed:
        text_rank_sql = conversation_text_rank(sql.SQL("source_winner.matched_text"))
        cursor_predicate = (
            sql.SQL(
                """
                where input.has_cursor
                and (
                    conversation.id = input.cursor_id
                    or row(
                        conversation.pinned::integer,
                        {exact_rank_sql},
                        {symbol_rank_sql},
                        source_winner.layer_rank,
                        {activity_sql},
                        {text_rank_sql},
                        conversation.id
                    ) <= row(
                        input.cursor_pinned_rank,
                        input.cursor_exact_rank,
                        input.cursor_symbol_rank,
                        input.cursor_layer_rank,
                        input.cursor_updated_at,
                        input.cursor_text_rank,
                        input.cursor_id
                    )
                )
                """
            ).format(
                activity_sql=conversation_activity_sql,
                exact_rank_sql=conversation_exact_rank,
                symbol_rank_sql=conversation_symbol_rank,
                text_rank_sql=text_rank_sql,
            )
            if cursor_relative
            else sql.SQL("")
        )
        window_order_sql = sql.SQL(
            """
            conversation.pinned::integer desc,
            {exact_rank_sql} desc,
            {symbol_rank_sql} desc,
            source_winner.layer_rank desc,
            {activity_sql} desc,
            {text_rank_sql} desc,
            conversation.id desc,
            source_winner.source_id desc
            """
        ).format(
            exact_rank_sql=conversation_exact_rank,
            symbol_rank_sql=conversation_symbol_rank,
            activity_sql=conversation_activity_sql,
            text_rank_sql=text_rank_sql,
        )
        return sql.SQL(
            """
            (
            select
                source_winner.conversation_id,
                source_winner.source_id,
                source_winner.candidate_at,
                source_winner.matched_text,
                source_winner.layer_rank,
                source_winner.layer,
                source_winner.match_count
            from (
                select ranked_source.*
                from (
                    select
                        source_match.*,
                        count(*) over (
                            partition by source_match.conversation_id
                        )::integer as match_count,
                        row_number() over (
                            partition by source_match.conversation_id
                            order by
                                source_match.candidate_at desc,
                                source_match.matched_text
                                    collate "und-x-icu" desc,
                                source_match.source_id desc
                        ) as source_conversation_rank
                    from (
                        {source_sql}
                    ) as source_match
                ) as ranked_source
                where ranked_source.source_conversation_rank = 1
            ) as source_winner
            cross join input
            join public.conversations as conversation
              on conversation.id = source_winner.conversation_id
             and conversation.user_id = input.user_id
             and {conversation_in_scope}
             and conversation.deleted_at is null
             and (
                 not input.guest_scope
                 or conversation.id = input.guest_conversation_id
             )
            {cursor_predicate}
            order by {window_order_sql}
            limit (select match_limit from input)
            )
            """
        ).format(
            conversation_in_scope=_CONVERSATION_IN_SCOPE,
            source_sql=source_sql,
            cursor_predicate=cursor_predicate,
            window_order_sql=window_order_sql,
        )

    chat_title_predicate = token_predicate(
        chat_title_haystack,
        chat_index_haystack,
    )
    chat_preview_predicate = token_predicate(
        chat_preview_haystack,
        chat_index_haystack,
    )
    message_predicate = token_predicate(message_haystack, message_haystack)
    run_predicate = token_predicate(
        run_haystack,
        _normalized(_RUN_INDEX_HAYSTACK),
    )
    idea_predicate = token_predicate(idea_haystack, idea_haystack)
    evidence_predicate = token_predicate(
        evidence_haystack,
        _normalized(_EVIDENCE_INDEX_HAYSTACK),
    )
    conversation_matched_text = sql.SQL(
        """
        case
            when input.normalized_query = ''
              or ({chat_title_predicate})
                then conversation.title
            when ({chat_preview_predicate})
                then conversation.last_message_preview
        end
        """
    ).format(
        chat_title_predicate=chat_title_predicate,
        chat_preview_predicate=chat_preview_predicate,
    )
    run_matched_text = sql.SQL(
        """
        concat_ws(
            ' ',
            nullif(run.conversation_result_card->>'title', ''),
            nullif(array_to_string(run.symbols, ' '), ''),
            nullif(run.config_snapshot->>'template', ''),
            nullif(run.conversation_result_card->>'strategy_label', '')
        )
        """
    )
    idea_matched_text = sql.SQL("concat_ws(' ', idea.title, nullif(idea.summary, ''))")
    evidence_matched_text = sql.SQL(
        "concat_ws(' ', evidence.title, nullif(evidence.digest, ''))"
    )
    decision_matched_text = sql.SQL(_decision_matched_text())

    conversation_source = sql.SQL(
        """
        select
            conversation.id as conversation_id,
            conversation.id as source_id,
            conversation.updated_at as candidate_at,
            {matched_text_sql} as matched_text,
            1::integer as layer_rank,
            'conversation'::text as layer
        from input
        join public.conversations as conversation
          on conversation.user_id = input.user_id
         and {conversation_in_scope}
         and conversation.deleted_at is null
         and (
             not input.guest_scope
             or conversation.id = input.guest_conversation_id
         )
         {decision_filter}
        where (
            input.normalized_query = ''
            or (
                input.text_search_enabled
                and (
                    ({chat_title_predicate})
                    or ({chat_preview_predicate})
                )
            )
        )
        """
    ).format(
        conversation_in_scope=_CONVERSATION_IN_SCOPE,
        matched_text_sql=conversation_matched_text,
        chat_title_predicate=chat_title_predicate,
        chat_preview_predicate=chat_preview_predicate,
        decision_filter=_CONVERSATION_DECISION_FILTER,
    )
    message_source = sql.SQL(
        """
        select
            conversation.id as conversation_id,
            message.id as source_id,
            message.created_at as candidate_at,
            message.content as matched_text,
            2::integer as layer_rank,
            'message'::text as layer
        from input
        join public.messages as message
          on message.user_id = input.user_id
         and message.role = 'user'
         and message.content <> %(legacy_skip_message)s
         and message.content not like %(legacy_goal_pattern)s escape '\\'
        join public.conversations as conversation
          on conversation.id = message.conversation_id
         and conversation.user_id = input.user_id
         and {conversation_in_scope}
         and conversation.deleted_at is null
         and (
             not input.guest_scope
             or conversation.id = input.guest_conversation_id
         )
         {decision_filter}
        where input.text_search_enabled
          and input.normalized_query <> ''
          and ({message_predicate})
        """
    ).format(
        conversation_in_scope=_CONVERSATION_IN_SCOPE,
        message_predicate=message_predicate,
        decision_filter=_CONVERSATION_DECISION_FILTER,
    )
    run_source = sql.SQL(
        """
        select
            conversation.id as conversation_id,
            run.id as source_id,
            coalesce(run.updated_at, run.created_at) as candidate_at,
            {matched_text_sql} as matched_text,
            3::integer as layer_rank,
            'run'::text as layer
        from input
        join public.backtest_runs as run
          on run.user_id = input.user_id
         and run.status = 'completed'
        join public.conversations as conversation
          on conversation.id = run.conversation_id
         and conversation.user_id = input.user_id
         and {conversation_in_scope}
         and conversation.deleted_at is null
         and (
             not input.guest_scope
             or conversation.id = input.guest_conversation_id
         )
         {decision_filter}
        where input.normalized_query <> ''
          and (
              (input.text_search_enabled and ({run_predicate}))
              or (
                  not input.text_search_enabled
                  and input.symbol_query is not null
                  and ({run_symbol_predicate})
              )
          )
        """
    ).format(
        conversation_in_scope=_CONVERSATION_IN_SCOPE,
        matched_text_sql=run_matched_text,
        run_predicate=run_predicate,
        run_symbol_predicate=run_symbol_predicate,
        decision_filter=_CONVERSATION_DECISION_FILTER,
    )
    idea_source = sql.SQL(
        """
        select
            conversation.id as conversation_id,
            idea.id as source_id,
            idea.updated_at as candidate_at,
            {matched_text_sql} as matched_text,
            4::integer as layer_rank,
            'idea'::text as layer
        from input
        join public.ideas as idea
          on idea.user_id = input.user_id
        join public.conversations as conversation
          on conversation.id = idea.source_conversation_id
         and conversation.user_id = input.user_id
         and {conversation_in_scope}
         and conversation.deleted_at is null
         and (
             not input.guest_scope
             or conversation.id = input.guest_conversation_id
         )
         {decision_filter}
        where input.text_search_enabled
          and input.normalized_query <> ''
          and ({idea_predicate})
        """
    ).format(
        conversation_in_scope=_CONVERSATION_IN_SCOPE,
        matched_text_sql=idea_matched_text,
        idea_predicate=idea_predicate,
        decision_filter=_CONVERSATION_DECISION_FILTER,
    )
    evidence_source = sql.SQL(
        """
        select
            conversation.id as conversation_id,
            evidence.id as source_id,
            evidence.updated_at as candidate_at,
            {matched_text_sql} as matched_text,
            5::integer as layer_rank,
            'evidence'::text as layer
        from input
        join public.evidence_artifacts as evidence
          on evidence.user_id = input.user_id
        join public.conversations as conversation
          on conversation.id = evidence.source_conversation_id
         and conversation.user_id = input.user_id
         and {conversation_in_scope}
         and conversation.deleted_at is null
         and (
             not input.guest_scope
             or conversation.id = input.guest_conversation_id
         )
         {decision_filter}
        where input.text_search_enabled
          and input.normalized_query <> ''
          and ({evidence_predicate})
        """
    ).format(
        conversation_in_scope=_CONVERSATION_IN_SCOPE,
        matched_text_sql=evidence_matched_text,
        evidence_predicate=evidence_predicate,
        decision_filter=_CONVERSATION_DECISION_FILTER,
    )

    decision_sources = _decision_match_sources(
        has_anchor=has_anchor,
        select_list=sql.SQL(
            """
            conversation.id as conversation_id,
            decision.id as source_id,
            decision.updated_at as candidate_at,
            {matched_text_sql} as matched_text,
            6::integer as layer_rank,
            'decision'::text as layer
            """
        ).format(matched_text_sql=decision_matched_text),
        conversation_join=sql.SQL(
            """
            join public.conversations as conversation
              on conversation.id = decision.source_conversation_id
             and conversation.user_id = input.user_id
             and {conversation_in_scope}
             and conversation.deleted_at is null
             and (
                 not input.guest_scope
                 or conversation.id = input.guest_conversation_id
             )
             {decision_filter}
            """
        ).format(
            decision_filter=_CONVERSATION_DECISION_FILTER,
            conversation_in_scope=_CONVERSATION_IN_SCOPE,
        ),
        all_tokens=decision_all_tokens,
    )
    decision_candidates = (
        sql.SQL(
            """
            decision_candidates as (
                select
                    deduplicated.conversation_id,
                    deduplicated.source_id,
                    deduplicated.candidate_at,
                    deduplicated.matched_text,
                    deduplicated.layer_rank,
                    deduplicated.layer
                from (
                    select distinct on (candidate.source_id)
                        candidate.*
                    from (
                        {candidate_sources}
                    ) as candidate
                    order by
                        candidate.source_id,
                        candidate.candidate_at desc,
                        candidate.matched_text collate "und-x-icu" desc,
                        candidate.conversation_id desc
                ) as deduplicated
            )
            """
        ).format(
            candidate_sources=sql.SQL("\nunion all\n").join(decision_sources),
        )
        if len(decision_sources) > 1
        else sql.SQL(
            """
            decision_candidates as (
                {decision_source}
            )
            """
        ).format(decision_source=decision_sources[0])
    )
    decision_candidate_source = sql.SQL(
        """
        select
            decision_candidate.conversation_id,
            decision_candidate.source_id,
            decision_candidate.candidate_at,
            decision_candidate.matched_text,
            decision_candidate.layer_rank,
            decision_candidate.layer
        from decision_candidates as decision_candidate
        """
    )
    source_specs = (
        conversation_source,
        message_source,
        run_source,
        idea_source,
        evidence_source,
        decision_candidate_source,
    )

    def source_windows(*, cursor_relative: bool) -> sql.Composed:
        return sql.SQL("\nunion all\n").join(
            bounded_source_window(
                source_sql=source,
                cursor_relative=cursor_relative,
            )
            for source in source_specs
        )

    match_window_ctes = (
        sql.SQL(
            """
            {decision_candidates},
            base_matches as (
                {base_matches}
            ),
            cursor_matches as (
                {cursor_matches}
            ),
            matches as (
                select * from base_matches
                union
                select * from cursor_matches
            )
            """
        ).format(
            decision_candidates=decision_candidates,
            base_matches=source_windows(cursor_relative=False),
            cursor_matches=source_windows(cursor_relative=True),
        )
        if has_cursor
        else sql.SQL(
            """
            {decision_candidates},
            matches as (
                {base_matches}
            )
            """
        ).format(
            decision_candidates=decision_candidates,
            base_matches=source_windows(cursor_relative=False),
        )
    )
    return sql.SQL(
        """
        {match_window_ctes},
        winning_matches as (
            select *
            from (
                select
                    matches.*,
                    row_number() over (
                        partition by matches.conversation_id
                        order by
                            matches.layer_rank desc,
                            matches.candidate_at desc,
                            matches.matched_text collate "und-x-icu" desc,
                            matches.source_id desc
                    ) as conversation_rank
                from matches
            ) as ranked_matches
            where conversation_rank = 1
        ),
        ranked_conversations as (
            select
                conversation.id as conversation_id,
                conversation.title,
                conversation.last_message_preview,
                conversation.pinned,
                conversation.archived,
                conversation.created_at,
                conversation.updated_at,
                winning.matched_text,
                winning.layer_rank,
                winning.layer,
                winning.match_count,
                case
                    when winning.layer = 'message' then winning.source_id
                    else null
                end as message_id,
                activity.activity_at,
                conversation.pinned::integer as pinned_rank,
                {exact_rank_sql} as exact_rank,
                {symbol_rank_sql} as symbol_rank,
                {text_rank_sql} as text_rank
            from winning_matches as winning
            cross join input
            join public.conversations as conversation
              on conversation.id = winning.conversation_id
             and conversation.user_id = input.user_id
             and {conversation_in_scope}
             and conversation.deleted_at is null
            cross join lateral ({activity_query}) as activity
        )
        """
    ).format(
        conversation_in_scope=_CONVERSATION_IN_SCOPE,
        match_window_ctes=match_window_ctes,
        exact_rank_sql=conversation_exact_rank,
        symbol_rank_sql=conversation_symbol_rank,
        text_rank_sql=conversation_text_rank(sql.SQL("winning.matched_text")),
        activity_query=conversation_activity_query,
    )


def _asset_symbol_slot(slot: int) -> sql.Composed:
    return _run_symbol_slot(sql.SQL("run"), slot)


def _asset_symbol_candidate_branch(slot: int) -> sql.Composed:
    normalized_symbol = _asset_symbol_slot(slot)
    raw_symbol = sql.SQL("run.symbols[{}]").format(sql.Literal(slot))
    return sql.SQL(
        """
        (
            select
                {normalized_symbol} as normalized_symbol,
                (
                    array_agg(
                        {raw_symbol}
                        order by
                            coalesce(run.updated_at, run.created_at) desc,
                            run.id desc
                    )
                )[1] as symbol,
                max(coalesce(run.updated_at, run.created_at)) as last_seen_at
            from input
            join public.backtest_runs as run
              on run.user_id = input.user_id
             and run.status = 'completed'
            join public.conversations as conversation
              on conversation.id = run.conversation_id
             and conversation.user_id = input.user_id
             and {conversation_in_scope}
             and conversation.deleted_at is null
             and (
                 not input.guest_scope
                 or conversation.id = input.guest_conversation_id
             )
            where input.symbol_query is not null
              and input.symbol_prefix_end is not null
              and {raw_symbol} is not null
              and {normalized_symbol} collate "C"
                    >= input.symbol_query collate "C"
              and {normalized_symbol} collate "C"
                    < input.symbol_prefix_end collate "C"
            group by {normalized_symbol}
            order by {normalized_symbol} collate "C"
            limit (select asset_symbol_limit from input)
        )
        """
    ).format(
        conversation_in_scope=_CONVERSATION_IN_SCOPE,
        normalized_symbol=normalized_symbol,
        raw_symbol=raw_symbol,
    )


def _asset_rollup_ctes() -> sql.Composed:
    candidate_branches = sql.SQL("\nunion all\n").join(
        _asset_symbol_candidate_branch(slot) for slot in range(1, 6)
    )
    matching_slot_predicates = sql.SQL("\n or \n").join(
        sql.SQL(
            """
            (
                run.symbols[{slot}] is not null
                and {normalized_symbol} collate "C"
                    = selected.normalized_symbol collate "C"
            )
            """
        ).format(
            slot=sql.Literal(slot),
            normalized_symbol=_asset_symbol_slot(slot),
        )
        for slot in range(1, 6)
    )
    return sql.SQL(
        """
        asset_symbol_candidates as (
            {candidate_branches}
        ),
        asset_symbol_stats as (
            select
                candidate.normalized_symbol,
                (
                    array_agg(
                        candidate.symbol
                        order by
                            candidate.last_seen_at desc,
                            candidate.symbol
                    )
                )[1] as symbol,
                max(candidate.last_seen_at) as last_seen_at
            from asset_symbol_candidates as candidate
            group by candidate.normalized_symbol
        ),
        asset_symbol_resolution as (
            select
                stats.*,
                count(*) over () as matching_symbol_count,
                bool_or(
                    stats.normalized_symbol = input.symbol_query
                ) over () as exact_present
            from asset_symbol_stats as stats
            cross join input
        ),
        asset_selected_symbol as (
            select resolution.*
            from asset_symbol_resolution as resolution
            cross join input
            where resolution.normalized_symbol = input.symbol_query
               or (
                   not resolution.exact_present
                   and resolution.matching_symbol_count = 1
               )
            order by
                (
                    resolution.normalized_symbol = input.symbol_query
                ) desc,
                resolution.last_seen_at desc,
                resolution.symbol
            limit 1
        ),
        asset_matching_runs as materialized (
            select run.*
            from input
            join public.backtest_runs as run
              on run.user_id = input.user_id
             and run.status = 'completed'
            join public.conversations as conversation
              on conversation.id = run.conversation_id
             and conversation.user_id = input.user_id
             and {conversation_in_scope}
             and conversation.deleted_at is null
             and (
                 not input.guest_scope
                 or conversation.id = input.guest_conversation_id
             )
            cross join asset_selected_symbol as selected
            where ({matching_slot_predicates})
        ),
        asset_run_lineage as (
            select
                run.id as run_id,
                selected.symbol,
                selected.normalized_symbol,
                coalesce(run.updated_at, run.created_at) as run_touched_at,
                evidence_touch.updated_at as evidence_touched_at,
                latest_decision.decision_state,
                latest_decision.updated_at as decision_touched_at
            from input
            cross join asset_selected_symbol as selected
            cross join asset_matching_runs as run
            left join lateral (
                select max(evidence.updated_at) as updated_at
                from public.evidence_artifacts as evidence
                where evidence.user_id = input.user_id
                  and evidence.source_conversation_id = run.conversation_id
                  and evidence.source_run_id = run.id
            ) as evidence_touch
              on true
            left join lateral (
                select
                    decision.decision_state,
                    decision.updated_at
                from public.evidence_artifacts as evidence
                join public.decision_notes as decision
                  on decision.evidence_artifact_id = evidence.id
                 and decision.user_id = input.user_id
                 and decision.source_conversation_id = run.conversation_id
                where evidence.user_id = input.user_id
                  and evidence.source_conversation_id = run.conversation_id
                  and evidence.source_run_id = run.id
                order by decision.updated_at desc, decision.id desc
                limit 1
            ) as latest_decision
              on true
        ),
        asset_rollup as (
            select
                lineage.normalized_symbol,
                lineage.symbol,
                count(distinct lineage.run_id)::integer as run_count,
                count(distinct lineage.run_id) filter (
                    where lineage.decision_state = 'promising'
                )::integer as promising_count,
                count(distinct lineage.run_id) filter (
                    where lineage.decision_state = 'watching'
                )::integer as watching_count,
                count(distinct lineage.run_id) filter (
                    where lineage.decision_state = 'rejected'
                )::integer as rejected_count,
                count(distinct lineage.run_id) filter (
                    where lineage.decision_state = 'revisit_later'
                )::integer as revisit_later_count,
                max(
                    greatest(
                        lineage.run_touched_at,
                        coalesce(
                            lineage.evidence_touched_at,
                            lineage.run_touched_at
                        ),
                        coalesce(
                            lineage.decision_touched_at,
                            lineage.run_touched_at
                        )
                    )
                ) as last_touched_at
            from asset_run_lineage as lineage
            group by lineage.normalized_symbol, lineage.symbol
        )
        """
    ).format(
        conversation_in_scope=_CONVERSATION_IN_SCOPE,
        candidate_branches=candidate_branches,
        matching_slot_predicates=matching_slot_predicates,
    )


def _asset_rollup_rows_sql() -> sql.SQL:
    return sql.SQL(
        """
        select
            'asset_rollup'::text as source_type,
            0::integer as pinned_rank,
            0::integer as exact_rank,
            0::integer as symbol_rank,
            0::integer as layer_rank,
            0::integer as text_rank,
            jsonb_build_object(
                'type', 'asset_rollup',
                'symbol', asset.symbol,
                'run_count', asset.run_count,
                'decision_counts', jsonb_build_object(
                    'promising', asset.promising_count,
                    'watching', asset.watching_count,
                    'rejected', asset.rejected_count,
                    'revisit_later', asset.revisit_later_count
                ),
                'last_touched_at', asset.last_touched_at
            ) as payload
        from asset_rollup as asset
        """
    )


def _asset_rollup_search_sql() -> sql.Composed:
    """Build the symbol-only path without transcript/object search relations."""
    return sql.SQL(
        """
        with {input_cte},
        {asset_rollup_ctes}
        {asset_rollup_rows}
        """
    ).format(
        input_cte=_CONVERSATION_INPUT_CTE,
        asset_rollup_ctes=_asset_rollup_ctes(),
        asset_rollup_rows=_asset_rollup_rows_sql(),
    )


def _conversation_search_sql(
    *,
    has_anchor: bool,
    has_cursor: bool = False,
    pivot_only: bool = False,
) -> sql.Composed:
    terminal_predicate = (
        sql.SQL(
            """
            ranked.conversation_id = input.cursor_id
            and ranked.activity_at = input.cursor_updated_at
            """
        )
        if pivot_only
        else sql.SQL(
            """
            not input.has_cursor
            or row(
                ranked.pinned_rank,
                ranked.exact_rank,
                ranked.symbol_rank,
                ranked.layer_rank,
                ranked.activity_at,
                ranked.text_rank,
                ranked.conversation_id
            ) < row(
                input.cursor_pinned_rank,
                input.cursor_exact_rank,
                input.cursor_symbol_rank,
                input.cursor_layer_rank,
                input.cursor_updated_at,
                input.cursor_text_rank,
                input.cursor_id
            )
            """
        )
    )
    conversation_rows = sql.SQL(
        """
        select
            'conversation'::text as source_type,
            ranked.pinned_rank,
            ranked.exact_rank,
            ranked.symbol_rank,
            ranked.layer_rank,
            ranked.text_rank,
            jsonb_build_object(
                'id', ranked.conversation_id,
                'title', ranked.title,
                'last_message_preview', ranked.last_message_preview,
                'pinned', ranked.pinned,
                'archived', ranked.archived,
                'created_at', ranked.created_at,
                'updated_at', ranked.updated_at,
                'deleted_at', null,
                '_recall_match', jsonb_build_object(
                    'matched_text', ranked.matched_text,
                    'layer_rank', ranked.layer_rank,
                    'layer', ranked.layer,
                    'match_count', ranked.match_count,
                    'message_id', ranked.message_id,
                    'symbol_exact_match', ranked.symbol_rank = 1,
                    'activity_at', ranked.activity_at
                )
            ) as payload
        from ranked_conversations as ranked
        cross join input
        where {terminal_predicate}
        order by
            ranked.pinned_rank desc,
            ranked.exact_rank desc,
            ranked.symbol_rank desc,
            ranked.layer_rank desc,
            ranked.activity_at desc,
            ranked.text_rank desc,
            ranked.conversation_id desc
        """
    ).format(
        terminal_predicate=terminal_predicate,
    )
    if pivot_only:
        return sql.SQL(
            """
            with {input_cte},
            {match_ctes}
            {conversation_rows}
            """
        ).format(
            input_cte=_CONVERSATION_INPUT_CTE,
            match_ctes=_conversation_match_ctes(
                has_anchor=has_anchor,
                has_cursor=has_cursor,
            ),
            conversation_rows=conversation_rows,
        )

    return sql.SQL(
        """
        with {input_cte},
        {match_ctes},
        {asset_rollup_ctes},
        conversation_page as (
            {conversation_rows}
            limit (select source_limit from input)
        )
        select
            source_type,
            pinned_rank,
            exact_rank,
            symbol_rank,
            layer_rank,
            text_rank,
            payload
        from conversation_page

        union all

        {asset_rollup_rows}
        """
    ).format(
        input_cte=_CONVERSATION_INPUT_CTE,
        match_ctes=_conversation_match_ctes(
            has_anchor=has_anchor,
            has_cursor=has_cursor,
        ),
        asset_rollup_ctes=_asset_rollup_ctes(),
        asset_rollup_rows=_asset_rollup_rows_sql(),
        conversation_rows=conversation_rows,
    )


def _conversation_ledger_sql(*, has_anchor: bool) -> sql.Composed:
    chat_title_haystack = _normalized("conversation.title")
    chat_preview_haystack = _normalized("coalesce(conversation.last_message_preview, '')")
    chat_index_haystack = _normalized(
        "conversation.title || ' ' " "|| coalesce(conversation.last_message_preview, '')"
    )
    message_haystack = _normalized("message.content")
    run_haystack = _normalized(
        "coalesce(run.conversation_result_card->>'title', '') || ' ' "
        "|| coalesce(array_to_string(run.symbols, ' '), '') || ' ' "
        "|| coalesce(run.config_snapshot->>'template', '') || ' ' "
        "|| coalesce(run.conversation_result_card->>'strategy_label', '')"
    )
    run_symbol_predicate = _exact_run_symbol_predicate(sql.SQL("run"))
    idea_haystack = _normalized("idea.title || ' ' || coalesce(idea.summary, '')")
    evidence_haystack = _normalized(
        "evidence.title || ' ' || coalesce(evidence.digest, '')"
    )
    decision_haystack = _normalized(_decision_haystack_text())

    def token_predicate(
        haystack: sql.Composable,
        index_haystack: sql.Composable,
    ) -> sql.Composed:
        return _token_match_predicate(
            normalized_haystack=haystack,
            normalized_index_haystack=index_haystack,
            has_anchor=has_anchor,
        )

    decision_all_tokens = _all_token_recheck(decision_haystack)
    decision_matches = sql.SQL(
        """
        decision_matching_conversations as (
            {sources}
        )
        """
    ).format(
        sources=sql.SQL("\nunion\n").join(
            sql.SQL("({})").format(source)
            for source in _decision_match_sources(
                has_anchor=has_anchor,
                select_list=sql.SQL("conversation.id as conversation_id"),
                conversation_join=sql.SQL(
                    """
                    join public.conversations as conversation
                      on conversation.id = decision.source_conversation_id
                     and conversation.user_id = input.user_id
                     and {conversation_in_scope}
                     and conversation.deleted_at is null
                    """
                ).format(conversation_in_scope=_CONVERSATION_IN_SCOPE),
                all_tokens=decision_all_tokens,
            )
        )
    )

    return sql.SQL(
        """
        with {input_cte},
        {decision_matches},
        matching_conversations as (
            select conversation.id as conversation_id
            from input
            join public.conversations as conversation
              on conversation.user_id = input.user_id
             and {conversation_in_scope}
             and conversation.deleted_at is null
            where (
                input.normalized_query = ''
                or (
                    input.text_search_enabled
                    and (
                        ({chat_title_predicate})
                        or ({chat_preview_predicate})
                    )
                )
            )

            union

            select conversation.id
            from input
            join public.messages as message
              on message.user_id = input.user_id
             and message.role = 'user'
             and message.content <> %(legacy_skip_message)s
             and message.content not like %(legacy_goal_pattern)s escape '\\'
            join public.conversations as conversation
              on conversation.id = message.conversation_id
             and conversation.user_id = input.user_id
             and {conversation_in_scope}
             and conversation.deleted_at is null
            where input.text_search_enabled
              and input.normalized_query <> ''
              and ({message_predicate})

            union

            select conversation.id
            from input
            join public.backtest_runs as run
              on run.user_id = input.user_id
             and run.status = 'completed'
            join public.conversations as conversation
              on conversation.id = run.conversation_id
             and conversation.user_id = input.user_id
             and {conversation_in_scope}
             and conversation.deleted_at is null
            where input.normalized_query <> ''
              and (
                  (input.text_search_enabled and ({run_predicate}))
                  or (
                      not input.text_search_enabled
                      and input.symbol_query is not null
                      and ({run_symbol_predicate})
                  )
              )

            union

            select conversation.id
            from input
            join public.ideas as idea
              on idea.user_id = input.user_id
            join public.conversations as conversation
              on conversation.id = idea.source_conversation_id
             and conversation.user_id = input.user_id
             and {conversation_in_scope}
             and conversation.deleted_at is null
            where input.text_search_enabled
              and input.normalized_query <> ''
              and ({idea_predicate})

            union

            select conversation.id
            from input
            join public.evidence_artifacts as evidence
              on evidence.user_id = input.user_id
            join public.conversations as conversation
              on conversation.id = evidence.source_conversation_id
             and conversation.user_id = input.user_id
             and {conversation_in_scope}
             and conversation.deleted_at is null
            where input.text_search_enabled
              and input.normalized_query <> ''
              and ({evidence_predicate})

            union

            select conversation_id
            from decision_matching_conversations
        ),
        conversation_states as (
            select distinct
                decision.source_conversation_id as conversation_id,
                decision.decision_state
            from input
            join public.decision_notes as decision
              on decision.user_id = input.user_id
            join matching_conversations as matching
              on matching.conversation_id = decision.source_conversation_id
        )
        select
            decision_state,
            count(distinct conversation_id)::integer as count
        from conversation_states
        group by decision_state
        """
    ).format(
        conversation_in_scope=_CONVERSATION_IN_SCOPE,
        input_cte=_CONVERSATION_LEDGER_INPUT_CTE,
        decision_matches=decision_matches,
        chat_title_predicate=token_predicate(
            chat_title_haystack,
            chat_index_haystack,
        ),
        chat_preview_predicate=token_predicate(
            chat_preview_haystack,
            chat_index_haystack,
        ),
        message_predicate=token_predicate(message_haystack, message_haystack),
        run_predicate=token_predicate(
            run_haystack,
            _normalized(_RUN_INDEX_HAYSTACK),
        ),
        run_symbol_predicate=run_symbol_predicate,
        idea_predicate=token_predicate(idea_haystack, idea_haystack),
        evidence_predicate=token_predicate(
            evidence_haystack,
            _normalized(_EVIDENCE_INDEX_HAYSTACK),
        ),
    )


_CONVERSATION_HYDRATION_TEMPLATE = """
select
    jsonb_build_object(
        'id', conversation.id,
        'title', conversation.title,
        'last_message_preview', conversation.last_message_preview,
        'pinned', conversation.pinned,
        'archived', conversation.archived,
        'created_at', conversation.created_at,
        'updated_at', conversation.updated_at,
        'deleted_at', conversation.deleted_at,
        '_recall_summary', jsonb_build_object(
            'run_count', coalesce(run_summary.run_count, 0),
            'total_runs', coalesce(run_summary.run_count, 0),
            'decided_runs', coalesce(run_summary.decided_runs, 0),
            'symbols', coalesce(run_summary.symbols, array[]::text[]),
            'strategy_families',
                coalesce(run_summary.strategy_families, array[]::text[]),
            'start_date', run_summary.start_date,
            'end_date', run_summary.end_date,
            'decision_states',
                coalesce(decision_summary.decision_states, array[]::text[]),
            'latest_run_decided',
                coalesce(latest_run.latest_run_decided, false),
            'latest_suggestion_untaken',
                coalesce(latest_suggestion.untaken, false),
            'latest_activity', activity.activity_at
        )
    ) as conversation_payload,
    latest_run.payload as latest_run_payload,
    latest_evidence.payload as latest_evidence_payload,
    latest_run_decision.payload as latest_run_decision_payload,
    latest_recall_decision.payload as latest_recall_decision_payload,
    latest_result_message.payload as latest_result_message_payload
from public.conversations as conversation
left join lateral (
    select
        count(*)::integer as run_count,
        count(*) filter (
            where exists (
                select 1
                from public.evidence_artifacts as decided_evidence
                join public.decision_notes as decided
                  on decided.evidence_artifact_id = decided_evidence.id
                 and decided.user_id = %(user_id)s
                where decided_evidence.user_id = %(user_id)s
                  and decided_evidence.source_conversation_id = conversation.id
                  and decided_evidence.source_run_id = run.id
                  and decided.source_conversation_id = conversation.id
            )
        )::integer as decided_runs,
        (
            select (array_agg(symbol order by last_used desc, symbol))[1:5]
            from (
                select symbol, max(coalesce(run.updated_at, run.created_at)) as last_used
                from public.backtest_runs as run
                cross join unnest(run.symbols) as symbol
                where run.user_id = %(user_id)s
                  and run.conversation_id = conversation.id
                  and run.status = 'completed'
                group by symbol
            ) as distinct_symbols
        ) as symbols,
        (
            select (array_agg(family order by last_used desc, family))[1:5]
            from (
                select
                    coalesce(
                        nullif(run.config_snapshot->>'template', ''),
                        nullif(
                            run.conversation_result_card->>'strategy_label',
                            ''
                        )
                    ) as family,
                    max(coalesce(run.updated_at, run.created_at)) as last_used
                from public.backtest_runs as run
                where run.user_id = %(user_id)s
                  and run.conversation_id = conversation.id
                  and run.status = 'completed'
                group by family
            ) as distinct_families
            where family is not null
        ) as strategy_families,
        min(
            case
                when coalesce(
                    run.config_snapshot->>'start_date',
                    run.conversation_result_card#>>'{date_range,start}'
                ) ~ '^\\d{4}-\\d{2}-\\d{2}$'
                    then coalesce(
                        run.config_snapshot->>'start_date',
                        run.conversation_result_card#>>'{date_range,start}'
                    )::date
            end
        ) as start_date,
        max(
            case
                when coalesce(
                    run.config_snapshot->>'end_date',
                    run.conversation_result_card#>>'{date_range,end}'
                ) ~ '^\\d{4}-\\d{2}-\\d{2}$'
                    then coalesce(
                        run.config_snapshot->>'end_date',
                        run.conversation_result_card#>>'{date_range,end}'
                    )::date
            end
        ) as end_date
    from public.backtest_runs as run
    where run.user_id = %(user_id)s
      and run.conversation_id = conversation.id
      and run.status = 'completed'
      and exists (
          select 1
          from public.evidence_artifacts as eligible_evidence
          where eligible_evidence.user_id = %(user_id)s
            and eligible_evidence.source_conversation_id = conversation.id
            and eligible_evidence.source_run_id = run.id
      )
) as run_summary on true
left join lateral (
    select array_agg(
        states.decision_state
        order by case states.decision_state
            when 'promising' then 1
            when 'watching' then 2
            when 'rejected' then 3
            when 'revisit_later' then 4
            else 5
        end
    ) as decision_states
    from (
        select distinct decision.decision_state
        from public.decision_notes as decision
        where decision.user_id = %(user_id)s
          and decision.source_conversation_id = conversation.id
    ) as states
) as decision_summary on true
left join lateral (
    select
        jsonb_build_object(
            'id', run.id,
            'conversation_id', run.conversation_id,
            'status', run.status,
            'asset_class', run.asset_class,
            'symbols', run.symbols,
            'benchmark_symbol', run.benchmark_symbol,
            'config_snapshot', run.config_snapshot,
            'conversation_result_card', run.conversation_result_card,
            'created_at', run.created_at,
            'updated_at', run.updated_at,
            'completed_at', coalesce(run.updated_at, run.created_at)
        ) as payload,
        run.id,
        exists (
            select 1
            from public.decision_notes as decision
            join public.evidence_artifacts as evidence
              on evidence.id = decision.evidence_artifact_id
             and evidence.user_id = %(user_id)s
            where decision.user_id = %(user_id)s
              and decision.source_conversation_id = conversation.id
              and evidence.source_run_id = run.id
        ) as latest_run_decided
    from public.backtest_runs as run
    where run.user_id = %(user_id)s
      and run.conversation_id = conversation.id
      and run.status = 'completed'
      and exists (
          select 1
          from public.evidence_artifacts as eligible_evidence
          where eligible_evidence.user_id = %(user_id)s
            and eligible_evidence.source_conversation_id = conversation.id
            and eligible_evidence.source_run_id = run.id
      )
    order by coalesce(run.updated_at, run.created_at) desc, run.id desc
    limit 1
) as latest_run on true
left join lateral (
    select not exists (
        select 1
        from public.messages as later_message
        where later_message.user_id = %(user_id)s
          and later_message.conversation_id = conversation.id
          and later_message.role = 'user'
          and (later_message.created_at, later_message.id)
              > (offer.created_at, offer.id)
    ) as untaken
    from public.messages as offer
    where offer.user_id = %(user_id)s
      and offer.conversation_id = conversation.id
      and offer.role = 'assistant'
      and offer.metadata->>'result_run_id' = latest_run.id::text
      and offer.metadata#>>'{next_experiments,version}'
          = 'argus_next_experiments/v1'
      and jsonb_array_length(
          case
              when jsonb_typeof(offer.metadata#>'{next_experiments,rows}')
                  = 'array'
                  then offer.metadata#>'{next_experiments,rows}'
              else '[]'::jsonb
          end
      ) > 0
    order by offer.created_at desc, offer.id desc
    limit 1
) as latest_suggestion on true
left join lateral (
    select jsonb_build_object(
        'id', decision.id,
        'idea_id', decision.idea_id,
        'idea_version_id', decision.idea_version_id,
        'evidence_artifact_id', decision.evidence_artifact_id,
        'source_conversation_id', decision.source_conversation_id,
        'decision_state', decision.decision_state,
        'note', decision.note,
        'created_at', decision.created_at,
        'updated_at', decision.updated_at,
        'source_run_id', evidence.source_run_id,
        'artifact_title', evidence.title,
        'artifact_digest', evidence.digest,
        'artifact_payload', evidence.payload,
        'source_message_id', decision.source_message_id,
        'computation', decision.computation,
        'attachment_text', __DECISION_ATTACHMENT_TEXT__
    ) as payload
    from public.decision_notes as decision
    __DECISION_ATTACHMENT_JOINS__
    where decision.user_id = %(user_id)s
      and decision.source_conversation_id = conversation.id
    order by decision.updated_at desc, decision.id desc
    limit 1
) as latest_recall_decision on true
left join lateral (
    select jsonb_build_object(
        'id', evidence.id,
        'idea_id', evidence.idea_id,
        'idea_version_id', evidence.idea_version_id,
        'source_conversation_id', evidence.source_conversation_id,
        'source_run_id', evidence.source_run_id,
        'artifact_type', evidence.artifact_type,
        'lifecycle', evidence.lifecycle,
        'title', evidence.title,
        'digest', evidence.digest,
        'payload', evidence.payload,
        'created_at', evidence.created_at,
        'updated_at', evidence.updated_at
    ) as payload
    from public.evidence_artifacts as evidence
    where evidence.user_id = %(user_id)s
      and evidence.source_conversation_id = conversation.id
      and evidence.source_run_id = latest_run.id
    order by evidence.updated_at desc, evidence.id desc
    limit 1
) as latest_evidence on true
left join lateral (
    select jsonb_build_object(
        'id', decision.id,
        'idea_id', decision.idea_id,
        'idea_version_id', decision.idea_version_id,
        'evidence_artifact_id', decision.evidence_artifact_id,
        'source_conversation_id', decision.source_conversation_id,
        'decision_state', decision.decision_state,
        'note', decision.note,
        'created_at', decision.created_at,
        'updated_at', decision.updated_at
    ) as payload
    from public.decision_notes as decision
    where decision.user_id = %(user_id)s
      and decision.source_conversation_id = conversation.id
      and decision.evidence_artifact_id = (
          latest_evidence.payload->>'id'
      )::uuid
    order by decision.updated_at desc, decision.id desc
    limit 1
) as latest_run_decision on true
left join lateral (
    select jsonb_build_object(
        'id', message.id,
        'conversation_id', message.conversation_id,
        'role', message.role,
        'content', message.content,
        'metadata', message.metadata,
        'created_at', message.created_at
    ) as payload
    from public.messages as message
    where message.user_id = %(user_id)s
      and message.conversation_id = conversation.id
      and message.role = 'assistant'
      and (
          message.metadata->>'result_run_id' = latest_run.id::text
          or message.metadata->>'latest_run_id' = latest_run.id::text
      )
    order by
        case
            when jsonb_typeof(message.metadata->'result_card') = 'object'
             and message.metadata->'result_card' <> '{}'::jsonb
                then 0
            else 1
        end,
        message.created_at desc,
        message.id desc
    limit 1
) as latest_result_message on true
cross join lateral (
    select max(source_activity.activity_at) as activity_at
    from (
        select conversation.updated_at as activity_at
        union all
        select max(coalesce(run.updated_at, run.created_at))
        from public.backtest_runs as run
        where run.user_id = %(user_id)s
          and run.conversation_id = conversation.id
        union all
        select max(message.created_at)
        from public.messages as message
        where message.user_id = %(user_id)s
          and message.conversation_id = conversation.id
        union all
        select max(idea.updated_at)
        from public.ideas as idea
        where idea.user_id = %(user_id)s
          and idea.source_conversation_id = conversation.id
        union all
        select max(evidence.updated_at)
        from public.evidence_artifacts as evidence
        where evidence.user_id = %(user_id)s
          and evidence.source_conversation_id = conversation.id
        union all
        select max(decision.updated_at)
        from public.decision_notes as decision
        where decision.user_id = %(user_id)s
          and decision.source_conversation_id = conversation.id
    ) as source_activity
) as activity
where conversation.user_id = %(user_id)s
  and __CONVERSATION_IN_SCOPE__
  and conversation.deleted_at is null
  and conversation.id = any(%(conversation_ids)s::uuid[])
order by array_position(%(conversation_ids)s::uuid[], conversation.id)
"""
# The decision block derives its joins and text from the attachment
# declaration; a plain replace keeps the jsonb braces in the template intact.
_CONVERSATION_HYDRATION_SQL = (
    _CONVERSATION_HYDRATION_TEMPLATE.replace(
        "__CONVERSATION_IN_SCOPE__", _CONVERSATION_IN_SCOPE_TEXT
    )
    .replace(
        "__DECISION_ATTACHMENT_JOINS__",
        _decision_attachment_joins(user_expression="%(user_id)s"),
    )
    .replace(
        "__DECISION_ATTACHMENT_TEXT__",
        _decision_attachment_text(),
    )
)


@dataclass(frozen=True)
class PostgresSearchReader:
    pool: Any

    def search_rows(
        self,
        *,
        user_id: str,
        scope: OwnerScope,
        query: str,
        source_limit: int,
        cursor_updated_at: datetime | None = None,
        cursor_id: str | None = None,
        decision_state: str | None = None,
        include_ledger_groups: bool = False,
        guest_scope: bool = False,
        guest_conversation_id: str | None = None,
        conversation_ids: list[str] | None = None,
    ) -> SearchReadResult:
        if source_limit < 1:
            raise ValueError("Search source limit must be positive.")
        try:
            owner_id = UUID(user_id)
        except (TypeError, ValueError) as exc:
            raise ValueError("Search owner id must be a UUID.") from exc

        has_cursor = cursor_updated_at is not None or cursor_id is not None
        if has_cursor and (cursor_updated_at is None or cursor_id is None):
            raise SearchCursorError("Search cursor is incomplete.")
        if cursor_updated_at is not None and (
            cursor_updated_at.tzinfo is None or cursor_updated_at.utcoffset() is None
        ):
            raise SearchCursorError("Search cursor timestamp must include a timezone.")
        try:
            pivot_id = UUID(cursor_id) if cursor_id is not None else None
        except (TypeError, ValueError) as exc:
            raise SearchCursorError("Search cursor id is invalid.") from exc
        if cursor_id is not None and str(pivot_id) != cursor_id:
            raise SearchCursorError("Search cursor id is not canonical.")
        try:
            workspace_id = (
                UUID(guest_conversation_id) if guest_conversation_id is not None else None
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("Guest workspace conversation id is invalid.") from exc
        requested_conversation_ids: list[UUID] = []
        for raw_conversation_id in dict.fromkeys(conversation_ids or ()):
            try:
                requested_conversation_ids.append(UUID(raw_conversation_id))
            except (TypeError, ValueError) as exc:
                raise ValueError("Visible conversation id is invalid.") from exc
        if len(requested_conversation_ids) > 50:
            raise ValueError("Visible conversation recall accepts at most 50 ids.")
        if len(requested_conversation_ids) > source_limit:
            raise ValueError("Visible conversation recall exceeds its source limit.")
        if requested_conversation_ids and (
            query.strip() or has_cursor or decision_state is not None
        ):
            raise ValueError(
                "Visible conversation recall cannot use ranked search controls."
            )

        normalized_query = normalize_search_text(query)
        normalized_tokens = tuple(dict.fromkeys(normalized_query.split()))
        symbol_query = normalize_search_symbol(query)
        text_search_enabled = not normalized_query or search_has_indexable_token(query)
        conversation_search_enabled = text_search_enabled or symbol_query is not None
        anchor_token = max(
            (token for token in normalized_tokens if len(token) >= 3),
            key=len,
            default=None,
        )
        if query.strip() and not search_query_is_indexable(query):
            if has_cursor:
                raise SearchCursorError(
                    "Deferred short search cannot continue from a cursor."
                )
            return SearchReadResult(
                rows=_group_candidates([], source_limit=source_limit),
                ledger_counts=(
                    {state: 0 for state in _DECISION_STATES}
                    if include_ledger_groups and not guest_scope
                    else None
                ),
            )
        if has_cursor and not conversation_search_enabled:
            raise SearchCursorError(
                "Deferred search cannot continue from a conversation cursor."
            )
        legacy_skip_message, legacy_goal_pattern = legacy_onboarding_sql_filters()
        params: dict[str, Any] = {
            "user_id": owner_id,
            SCOPE_PARAMETER: space_id(scope),
            "normalized_query": normalized_query,
            # PostgreSQL text cannot represent NUL. Normalized matching remains
            # exact, while raw symbol equality must be false for such a query
            # because stored Postgres symbols cannot contain NUL either.
            "symbol_query": (symbol_query if "\x00" not in query else None),
            "symbol_prefix_end": (
                _symbol_prefix_end(symbol_query) if "\x00" not in query else None
            ),
            "source_limit": source_limit,
            "match_limit": _conversation_match_limit(source_limit),
            "asset_symbol_limit": 2,
            "text_search_enabled": text_search_enabled,
            "has_cursor": has_cursor,
            "cursor_pinned_rank": 0,
            "cursor_exact_rank": 0,
            "cursor_symbol_rank": 0,
            "cursor_type_rank": 0,
            "cursor_layer_rank": 0,
            "cursor_updated_at": cursor_updated_at,
            "cursor_text_rank": 0,
            "cursor_id": pivot_id,
            "decision_state": decision_state,
            "ledger_browse": include_ledger_groups and not normalized_query,
            "ideas_only": False,
            "guest_scope": guest_scope,
            "guest_conversation_id": workspace_id,
            "token_patterns": [f"%{token}%" for token in normalized_tokens],
            "anchor_pattern": (f"%{anchor_token}%" if anchor_token is not None else None),
            "legacy_skip_message": legacy_skip_message,
            "legacy_goal_pattern": legacy_goal_pattern,
        }
        with self.pool.connection(timeout=_SEARCH_ACQUIRE_TIMEOUT_SECONDS) as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                if requested_conversation_ids:
                    grouped = {group: [] for group in _CONVERSATION_ROW_GROUPS}
                    grouped["conversations"] = [
                        {"id": str(conversation_id)}
                        for conversation_id in requested_conversation_ids
                    ]
                    asset_rollup = None
                    grouped = _hydrate_conversation_recall(
                        cursor=cursor,
                        owner_id=owner_id,
                        scope=scope,
                        grouped=grouped,
                        guest_conversation_id=(workspace_id if guest_scope else None),
                    )
                elif has_cursor:
                    cursor.execute(
                        _conversation_search_sql(
                            has_anchor=anchor_token is not None,
                            has_cursor=True,
                            pivot_only=True,
                        ),
                        params,
                    )
                    pivots = cursor.fetchall()
                    if len(pivots) != 1:
                        raise SearchCursorError(
                            "Search cursor pivot is missing or ambiguous."
                        )
                    pivot = pivots[0]
                    params.update(
                        cursor_pinned_rank=int(pivot["pinned_rank"]),
                        cursor_exact_rank=int(pivot["exact_rank"]),
                        cursor_symbol_rank=int(pivot["symbol_rank"]),
                        cursor_layer_rank=int(pivot["layer_rank"]),
                        cursor_text_rank=int(pivot["text_rank"]),
                    )

                if not requested_conversation_ids:
                    search_sql = (
                        _conversation_search_sql(
                            has_anchor=anchor_token is not None,
                            has_cursor=has_cursor,
                        )
                        if conversation_search_enabled
                        else _asset_rollup_search_sql()
                    )
                    cursor.execute(search_sql, params)
                    candidate_rows = cursor.fetchall()
                    grouped = _group_candidates(
                        candidate_rows,
                        source_limit=source_limit,
                    )
                    asset_rows = grouped.pop("asset_rollups", [])
                    asset_rollup = (
                        SearchAssetRollup.model_validate(asset_rows[0])
                        if asset_rows
                        else None
                    )
                    grouped = _hydrate_conversation_recall(
                        cursor=cursor,
                        owner_id=owner_id,
                        scope=scope,
                        grouped=grouped,
                        guest_conversation_id=(workspace_id if guest_scope else None),
                    )
                ledger_counts = None
                if include_ledger_groups and not guest_scope:
                    ledger_counts = {state: 0 for state in _DECISION_STATES}
                    if conversation_search_enabled:
                        ledger_params = {
                            **params,
                            "decision_state": None,
                            "has_cursor": False,
                            "cursor_id": None,
                            "cursor_updated_at": None,
                        }
                        cursor.execute(
                            _conversation_ledger_sql(has_anchor=anchor_token is not None),
                            ledger_params,
                        )
                        for row in cursor.fetchall():
                            state = str(row.get("decision_state") or "")
                            if state in ledger_counts:
                                ledger_counts[state] = int(row.get("count") or 0)

        return SearchReadResult(
            rows=grouped,
            ledger_counts=ledger_counts,
            asset_rollup=asset_rollup,
        )


def _hydrate_conversation_recall(
    *,
    cursor: Any,
    owner_id: UUID,
    scope: OwnerScope,
    grouped: dict[str, list[dict[str, Any]]],
    guest_conversation_id: UUID | None,
) -> dict[str, list[dict[str, Any]]]:
    """Hydrate exact full-lineage aggregates and only selected child facts."""
    candidate_conversations = {
        str(row["id"]): row
        for row in grouped["conversations"]
        if row.get("id") is not None
    }
    unique_ids = list(candidate_conversations)
    if guest_conversation_id is not None:
        unique_ids = [
            value for value in unique_ids if value == str(guest_conversation_id)
        ]
    if not unique_ids:
        return {group: [] for group in _CONVERSATION_ROW_GROUPS}

    params = {
        "user_id": owner_id,
        SCOPE_PARAMETER: space_id(scope),
        "conversation_ids": unique_ids,
    }
    hydrated: dict[str, list[dict[str, Any]]] = {
        group: [] for group in _CONVERSATION_ROW_GROUPS
    }
    cursor.execute(_CONVERSATION_HYDRATION_SQL, params)
    for row in cursor.fetchall():
        conversation_payload = row.get("conversation_payload")
        if not isinstance(conversation_payload, dict):
            continue
        conversation_id = str(conversation_payload.get("id") or "")
        candidate = candidate_conversations.get(conversation_id, {})
        recall_match = candidate.get("_recall_match")
        if isinstance(recall_match, dict):
            conversation_payload["_recall_match"] = recall_match
        hydrated["conversations"].append(conversation_payload)

        latest_run = row.get("latest_run_payload")
        if isinstance(latest_run, dict):
            hydrated["runs"].append(latest_run)
        latest_evidence = row.get("latest_evidence_payload")
        if isinstance(latest_evidence, dict):
            hydrated["evidence"].append(latest_evidence)
        seen_decision_ids: set[str] = set()
        for key in (
            "latest_recall_decision_payload",
            "latest_run_decision_payload",
        ):
            latest_decision = row.get(key)
            if not isinstance(latest_decision, dict):
                continue
            decision_id = str(latest_decision.get("id") or "")
            if not decision_id or decision_id in seen_decision_ids:
                continue
            seen_decision_ids.add(decision_id)
            hydrated["decisions"].append(latest_decision)
        latest_result_message = row.get("latest_result_message_payload")
        if isinstance(latest_result_message, dict):
            hydrated["messages"].append(latest_result_message)
    return hydrated


def _group_candidates(
    candidates: list[dict[str, Any]],
    *,
    source_limit: int,
) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {
        group: [] for group in _ROW_GROUP_BY_SOURCE.values()
    }
    for candidate in candidates:
        group = _ROW_GROUP_BY_SOURCE.get(str(candidate.get("source_type")))
        payload = candidate.get("payload")
        if group is None or not isinstance(payload, dict):
            continue
        if len(grouped[group]) < source_limit:
            grouped[group].append(payload)
    return grouped
