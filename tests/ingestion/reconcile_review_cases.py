"""Reconciliation regressions found in review, shared by the in-memory and
real-Postgres stores (split from ``reconcile_cases`` to keep each module small).
"""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from argus.domain.ingestion.reconcile.model import (
    ReconcileError,
    StaleEvent,
)
from argus.domain.owner_scope import PERSONAL
from argus.domain.recording.money_schemas import MoneyRequest
from argus.domain.recording.money_service import MoneyService
from psycopg.errors import UniqueViolation

from tests.ingestion.reconcile_cases import (
    DAY,
    NOW,
    accept,
    activities,
    cand,
    link_accounts,
    new_account,
    only,
    plaid,
    submit,
    tap,
)

# --- Review regressions (#772 review) ------------------------------------


def _open(world, source=None, external_id=None):
    events = world.recon.list(user_id=world.user, states=("open",), scope=PERSONAL)
    return [
        e
        for e in events
        if (source is None or e["observations"][0]["source"] == source)
        and (external_id is None or e["observations"][0]["external_id"] == external_id)
    ]


def test_reconnected_source_cannot_record_an_accepted_purchase_again(world):
    card = new_account(world)
    bank = world.connect("plaid")
    submit(world, bank, plaid(bank, "txn-1", status="posted"))
    event = only(world)
    event = world.recon.resolve(
        user_id=world.user,
        event_id=event["id"],
        version=event["version"],
        changes={"account_id": card},
        scope=PERSONAL,
    )
    accepted = accept(world, event)["activity"]["activity_id"]
    world.disconnect(bank)
    world.recon.forget_connection(user_id=world.user, connection_id=bank, scope=PERSONAL)
    again = world.connect("plaid")
    submit(world, again, plaid(again, "txn-1", status="posted"))
    [draft] = _open(world)
    assert draft["possible_duplicates"] == [event["id"]]
    flagged = world.recon.detail(user_id=world.user, event_id=event["id"], scope=PERSONAL)
    assert flagged["possible_duplicates"] == [draft["id"]]
    result = world.recon.accept_batch(
        user_id=world.user,
        items=[(draft["id"], draft["version"])],
        idempotency_key="b1",
        scope=PERSONAL,
    )
    assert result[0]["outcome"] == "needs_review"
    assert [a["activity_id"] for a in activities(world)] == [accepted]
    merged = world.recon.merge(
        user_id=world.user,
        event_id=draft["id"],
        into_event_id=event["id"],
        version=draft["version"],
        into_version=world.recon.detail(
            user_id=world.user, event_id=event["id"], scope=PERSONAL
        )["version"],
        scope=PERSONAL,
    )
    assert merged["id"] == event["id"] and merged["state"] == "accepted"


def test_possible_duplicates_are_flagged_on_both_events(world):
    card = new_account(world)
    gmail, bank = world.connect("gmail"), world.connect("plaid")
    link_accounts(world, card, (bank, plaid(bank, "seed", amount="1")))
    submit(
        world,
        gmail,
        cand(
            gmail,
            "m1",
            source="gmail",
            amount="12.50",
            currency="USD",
            occurred_on=DAY,
            account={"mask": "4321"},
        ),
    )
    [first] = _open(world, "gmail")
    submit(world, bank, plaid(bank, "t1", status="posted"))
    [second] = _open(world, "plaid", "t1")
    first = world.recon.detail(user_id=world.user, event_id=first["id"], scope=PERSONAL)
    assert second["possible_duplicates"] == [first["id"]]
    assert first["possible_duplicates"] == [second["id"]]
    assert first["attention"] == second["attention"] == "possible_duplicate"
    accept(world, second, key="k-b")
    first = world.recon.detail(user_id=world.user, event_id=first["id"], scope=PERSONAL)
    result = world.recon.accept_batch(
        user_id=world.user,
        items=[(first["id"], first["version"])],
        idempotency_key="b2",
        scope=PERSONAL,
    )
    assert result[0]["outcome"] == "needs_review"
    # The person says they are different purchases: both sides clear.
    cleared = world.recon.acknowledge(
        user_id=world.user, event_id=first["id"], version=first["version"], scope=PERSONAL
    )
    assert cleared["possible_duplicates"] == [] and cleared["attention"] is None
    second = world.recon.detail(user_id=world.user, event_id=second["id"], scope=PERSONAL)
    assert second["possible_duplicates"] == []


def test_match_window_follows_the_date_a_person_supplies(world):
    card = new_account(world)
    gmail, bank = world.connect("gmail"), world.connect("plaid")
    link_accounts(world, card, (bank, plaid(bank, "seed", amount="1")))
    submit(
        world,
        gmail,
        cand(
            gmail,
            "m1",
            source="gmail",
            amount="12.50",
            currency="USD",
            direction="outflow",
            account={"mask": "4321"},
        ),
    )
    [email] = _open(world, "gmail")
    world.recon.resolve(
        user_id=world.user,
        event_id=email["id"],
        version=email["version"],
        changes={"occurred_on": DAY.isoformat(), "account_id": card},
        scope=PERSONAL,
    )
    submit(world, bank, plaid(bank, "t1", status="posted"))
    [posted] = [
        e
        for e in world.recon.list(user_id=world.user, states=("open",), scope=PERSONAL)
        if e["observations"][0]["external_id"] in ("t1", "m1")
        and len(e["observations"]) == 2
    ] or [None]
    if posted is None:  # not auto-linked: it must at least be flagged both ways
        [bank_event] = _open(world, "plaid", "t1")
        assert bank_event["possible_duplicates"] == [email["id"]]


def test_removed_then_replaced_evidence_comes_back(world):
    bank = world.connect("plaid")
    submit(world, bank, plaid(bank, "pend"))
    submit(world, bank, cand(bank, "pend", source="plaid", status="removed"))
    assert _open(world) == []
    submit(world, bank, plaid(bank, "post", status="posted", replaces="pend"))
    [back] = _open(world)
    states = {o["external_id"]: o["live"] for o in back["observations"]}
    assert states == {"pend": False, "post": True}


def test_source_removed_warning_clears_when_evidence_returns(world):
    card = new_account(world)
    bank = world.connect("plaid")
    submit(world, bank, plaid(bank, "pend"))
    event = only(world)
    event = world.recon.resolve(
        user_id=world.user,
        event_id=event["id"],
        version=event["version"],
        changes={"account_id": card},
        scope=PERSONAL,
    )
    accept(world, event)
    submit(world, bank, cand(bank, "pend", source="plaid", status="removed"))
    assert only(world, "accepted")["attention"] == "source_removed"
    submit(world, bank, plaid(bank, "post", status="posted", replaces="pend"))
    assert only(world, "accepted")["attention"] is None


def test_batch_returns_money_refusals_per_item(world):
    card = new_account(world)
    bank = world.connect("plaid")
    link_accounts(world, card, (bank, plaid(bank, "seed", amount="1")))
    submit(
        world,
        bank,
        plaid(bank, "pay", kind_hint="card_payment", direction="inflow"),
        plaid(bank, "ok", amount="40"),
    )
    payment = next(e for e in _open(world) if e["facts"]["kind"] == "card_payment")
    # Seen on the card (inflow): the card is the destination; the person
    # still has to say which account paid it.
    assert "source_account_id" in payment["unresolved"]
    items = [(e["id"], e["version"]) for e in _open(world)]
    results = world.recon.accept_batch(
        user_id=world.user, items=items, idempotency_key="b1", scope=PERSONAL
    )
    assert sorted(r["outcome"] for r in results) == ["accepted", "needs_review"]


def test_invalid_resolution_is_refused_before_it_is_stored(world):
    bank = world.connect("plaid")
    submit(world, bank, plaid(bank, "t1"))
    event = only(world)
    for changes, code in (
        ({"kind": "bogus"}, "kind_invalid"),
        ({"category_id": "nope"}, "category_unknown"),
        ({"time_zone": "Mars/Base"}, "time_zone_unknown"),
    ):
        with pytest.raises(ReconcileError) as caught:
            world.recon.resolve(
                user_id=world.user,
                event_id=event["id"],
                version=event["version"],
                changes=changes,
                scope=PERSONAL,
            )
        assert caught.value.code == code


def test_evidence_arriving_after_disconnect_is_ignored(world):
    shortcuts = world.connect("shortcuts")
    submit(world, shortcuts, tap(shortcuts))
    world.disconnect(shortcuts)
    world.recon.forget_connection(
        user_id=world.user, connection_id=shortcuts, scope=PERSONAL
    )
    late = submit(world, shortcuts, tap(shortcuts, "tap-late"))
    assert late.recorded == 0 and late.ignored == 1
    assert _open(world) == []


def test_merge_refuses_dismissed_events_and_checks_both_versions(world):
    shortcuts, bank = world.connect("shortcuts"), world.connect("plaid")
    submit(world, shortcuts, tap(shortcuts))
    submit(world, bank, plaid(bank, "t1"))
    tap_event, bank_event = _open(world, "shortcuts")[0], _open(world, "plaid")[0]
    with pytest.raises(StaleEvent):
        world.recon.merge(
            user_id=world.user,
            event_id=tap_event["id"],
            into_event_id=bank_event["id"],
            version=tap_event["version"],
            into_version=bank_event["version"] + 3,
            scope=PERSONAL,
        )
    dismissed = world.recon.dismiss(
        user_id=world.user,
        event_id=bank_event["id"],
        version=world.recon.detail(
            user_id=world.user, event_id=bank_event["id"], scope=PERSONAL
        )["version"],
        scope=PERSONAL,
    )
    tap_event = world.recon.detail(
        user_id=world.user, event_id=tap_event["id"], scope=PERSONAL
    )
    with pytest.raises(ReconcileError) as caught:
        world.recon.merge(
            user_id=world.user,
            event_id=tap_event["id"],
            into_event_id=bank_event["id"],
            version=tap_event["version"],
            into_version=dismissed["version"],
            scope=PERSONAL,
        )
    assert caught.value.code == "import_dismissed"


def test_interrupted_acceptance_resumes_without_a_second_record(world, monkeypatch):
    card = new_account(world)
    bank = world.connect("plaid")
    submit(world, bank, plaid(bank, "t1"))
    event = only(world)
    event = world.recon.resolve(
        user_id=world.user,
        event_id=event["id"],
        version=event["version"],
        changes={"account_id": card},
        scope=PERSONAL,
    )
    preview = world.recon.preview(
        user_id=world.user, event_id=event["id"], scope=PERSONAL
    )["preview"]
    request = MoneyRequest.model_validate(preview["reviewed_request"]).model_copy(
        update={"preview_token": preview["preview_token"]}
    )
    real_write = world.recon.money.write

    def committed_then_lost(**kwargs):
        real_write(**kwargs)
        raise ConnectionError("response lost after commit")

    monkeypatch.setattr(world.recon.money, "write", committed_then_lost)
    with pytest.raises(ConnectionError):
        world.recon.accept(
            user_id=world.user,
            event_id=event["id"],
            idempotency_key="k1",
            version=event["version"],
            request=request,
            scope=PERSONAL,
        )
    monkeypatch.setattr(world.recon.money, "write", real_write)
    assert (
        world.recon.detail(user_id=world.user, event_id=event["id"], scope=PERSONAL)[
            "state"
        ]
        == "accepting"
    )
    # A different key cannot record again; it completes the original instead.
    with pytest.raises(ReconcileError) as caught:
        world.recon.accept(
            user_id=world.user,
            event_id=event["id"],
            idempotency_key="k2",
            version=event["version"],
            request=request,
            scope=PERSONAL,
        )
    assert caught.value.code == "import_already_accepted"
    assert only(world, "accepted")["activity_id"]
    assert len(activities(world)) == 1


def test_linking_waits_while_an_import_is_being_recorded(world):
    card = new_account(world)
    money = MoneyService(world.accounts)
    request = MoneyRequest(
        kind="expense",
        account_id=card,
        amount="40",
        occurred_at=datetime(2026, 9, 18, 15, tzinfo=timezone.utc),
    )
    preview = money.preview(user_id=world.user, request=request, scope=PERSONAL)
    manual = money.write(
        user_id=world.user,
        request=MoneyRequest.model_validate(preview["reviewed_request"]).model_copy(
            update={"preview_token": preview["preview_token"]}
        ),
        idempotency_key="manual-40",
        scope=PERSONAL,
    )["activity"]["activity_id"]
    bank = world.connect("plaid")
    submit(world, bank, plaid(bank, "t1"), plaid(bank, "t2", amount="40"))
    first, second = sorted(_open(world), key=lambda e: e["facts"]["amount"])
    from dataclasses import replace

    with world.recon.store.transaction(world.user, scope=PERSONAL) as tx:
        tx.put_event(replace(tx.event(first["id"]), state="accepting", accept_key="k"))
    with pytest.raises(ReconcileError) as caught:
        world.recon.link_activity(
            user_id=world.user,
            event_id=second["id"],
            activity_id=manual,
            version=second["version"],
            scope=PERSONAL,
        )
    assert caught.value.code == "import_accept_in_progress"


def test_deleted_events_leave_no_dangling_duplicate_references(world):
    shortcuts, bank = world.connect("shortcuts"), world.connect("plaid")
    submit(world, shortcuts, tap(shortcuts))
    submit(world, bank, plaid(bank, "t1"))
    tap_event = _open(world, "shortcuts")[0]
    bank_event = _open(world, "plaid")[0]
    assert bank_event["possible_duplicates"] == [tap_event["id"]]
    world.disconnect(shortcuts)
    world.recon.forget_connection(
        user_id=world.user, connection_id=shortcuts, scope=PERSONAL
    )
    bank_event = world.recon.detail(
        user_id=world.user, event_id=bank_event["id"], scope=PERSONAL
    )
    assert bank_event["possible_duplicates"] == [] and bank_event["attention"] is None


# --- Second review regressions (#772 fix review) -------------------------


def _accepted(world, bank, eid="t1", **changes):
    card = new_account(world)
    submit(world, bank, plaid(bank, eid))
    event = only(world)
    event = world.recon.resolve(
        user_id=world.user,
        event_id=event["id"],
        version=event["version"],
        changes={"account_id": card, **changes},
        scope=PERSONAL,
    )
    accept(world, event)
    return only(world, "accepted")


def test_a_person_correction_is_not_reported_as_a_source_change(world):
    bank = world.connect("plaid")
    _accepted(world, bank, amount="15")  # evidence says 12.50
    submit(world, bank, plaid(bank, "t1", status="posted"))  # status-only revision
    assert only(world, "accepted")["attention"] is None


def test_an_acknowledged_source_change_stays_acknowledged(world):
    bank = world.connect("plaid")
    _accepted(world, bank)
    submit(world, bank, plaid(bank, "t1", amount="15"))
    flagged = only(world, "accepted")
    assert flagged["attention"] == "source_changed"
    world.recon.acknowledge(
        user_id=world.user,
        event_id=flagged["id"],
        version=flagged["version"],
        scope=PERSONAL,
    )
    submit(world, bank, plaid(bank, "t1", amount="15", status="posted"))
    assert only(world, "accepted")["attention"] is None


def test_warning_raised_while_recording_survives_completion(world, monkeypatch):
    card = new_account(world)
    bank = world.connect("plaid")
    submit(world, bank, plaid(bank, "t1"))
    event = only(world)
    event = world.recon.resolve(
        user_id=world.user,
        event_id=event["id"],
        version=event["version"],
        changes={"account_id": card},
        scope=PERSONAL,
    )
    preview = world.recon.preview(
        user_id=world.user, event_id=event["id"], scope=PERSONAL
    )["preview"]
    request = MoneyRequest.model_validate(preview["reviewed_request"]).model_copy(
        update={"preview_token": preview["preview_token"]}
    )
    real_write = world.recon.money.write

    def lost(**kwargs):
        real_write(**kwargs)
        raise ConnectionError("lost")

    monkeypatch.setattr(world.recon.money, "write", lost)
    with pytest.raises(ConnectionError):
        world.recon.accept(
            user_id=world.user,
            event_id=event["id"],
            idempotency_key="k1",
            version=event["version"],
            request=request,
            scope=PERSONAL,
        )
    monkeypatch.setattr(world.recon.money, "write", real_write)
    submit(world, bank, cand(bank, "t1", source="plaid", status="removed"))
    done = world.recon.accept(
        user_id=world.user,
        event_id=event["id"],
        idempotency_key="k1",
        version=event["version"],
        request=request,
        scope=PERSONAL,
    )
    assert done["event"]["state"] == "accepted"
    assert done["event"]["attention"] == "source_removed"


def test_a_note_edit_does_not_reraise_an_answered_duplicate_question(world):
    shortcuts, bank = world.connect("shortcuts"), world.connect("plaid")
    submit(world, shortcuts, tap(shortcuts))
    submit(world, bank, plaid(bank, "t1"))
    flagged = _open(world, "plaid")[0]
    assert flagged["possible_duplicates"]
    cleared = world.recon.acknowledge(
        user_id=world.user,
        event_id=flagged["id"],
        version=flagged["version"],
        scope=PERSONAL,
    )
    edited = world.recon.resolve(
        user_id=world.user,
        event_id=flagged["id"],
        version=cleared["version"],
        changes={"note": "Café con Ana"},
        scope=PERSONAL,
    )
    assert edited["possible_duplicates"] == [] and edited["attention"] is None
    assert _open(world, "shortcuts")[0]["possible_duplicates"] == []


@pytest.mark.parametrize("how", ["person", "source"])
def test_dismissal_clears_the_partner_events_duplicate_flag(world, how):
    shortcuts, bank = world.connect("shortcuts"), world.connect("plaid")
    submit(world, shortcuts, tap(shortcuts))
    submit(world, bank, plaid(bank, "t1"))
    tap_event = _open(world, "shortcuts")[0]
    assert tap_event["possible_duplicates"]
    bank_event = _open(world, "plaid")[0]
    if how == "person":
        world.recon.dismiss(
            user_id=world.user,
            event_id=bank_event["id"],
            version=bank_event["version"],
            scope=PERSONAL,
        )
    else:
        submit(world, bank, cand(bank, "t1", source="plaid", status="removed"))
    tap_event = world.recon.detail(
        user_id=world.user, event_id=tap_event["id"], scope=PERSONAL
    )
    assert tap_event["possible_duplicates"] == [] and tap_event["attention"] is None


def test_retry_under_the_claiming_key_replays_the_claimed_request(world, monkeypatch):
    card = new_account(world)
    bank = world.connect("plaid")
    submit(world, bank, plaid(bank, "t1"))
    event = only(world)
    event = world.recon.resolve(
        user_id=world.user,
        event_id=event["id"],
        version=event["version"],
        changes={"account_id": card},
        scope=PERSONAL,
    )
    preview = world.recon.preview(
        user_id=world.user, event_id=event["id"], scope=PERSONAL
    )["preview"]
    request = MoneyRequest.model_validate(preview["reviewed_request"]).model_copy(
        update={"preview_token": preview["preview_token"]}
    )

    def down(**_kwargs):
        raise ConnectionError("before commit")

    monkeypatch.setattr(world.recon.money, "write", down)
    with pytest.raises(ConnectionError):
        world.recon.accept(
            user_id=world.user,
            event_id=event["id"],
            idempotency_key="k1",
            version=event["version"],
            request=request,
            scope=PERSONAL,
        )
    monkeypatch.undo()
    different = request.model_copy(update={"note": "other body"})
    done = world.recon.accept(
        user_id=world.user,
        event_id=event["id"],
        idempotency_key="k1",
        version=event["version"],
        request=different,
        scope=PERSONAL,
    )
    assert done["activity"]["note"] == request.note


def test_an_unreadable_claim_is_released_not_stuck(world):
    bank = world.connect("plaid")
    submit(world, bank, plaid(bank, "t1"))
    event = only(world)
    from dataclasses import replace as dc_replace

    with world.recon.store.transaction(world.user, scope=PERSONAL) as tx:
        current = tx.event(event["id"])
        tx.put_event(
            dc_replace(
                current,
                state="accepting",
                accept_key="k",
                resolution={"pending_request": {"kind": "bogus"}},
            )
        )
    with pytest.raises(ReconcileError):
        world.recon.accept(
            user_id=world.user,
            event_id=event["id"],
            idempotency_key="other",
            version=1,
            request=MoneyRequest(
                kind="expense", amount="1", occurred_at=NOW, account_id=str(uuid4())
            ),
            scope=PERSONAL,
        )
    assert (
        world.recon.detail(user_id=world.user, event_id=event["id"], scope=PERSONAL)[
            "state"
        ]
        == "open"
    )


def test_store_refuses_two_imports_for_one_activity(world):
    bank = world.connect("plaid")
    submit(world, bank, plaid(bank, "a"), plaid(bank, "b", amount="40"))
    first, second = _open(world)
    from dataclasses import replace as dc_replace

    activity = str(uuid4())
    # Memory raises ValueError; Postgres's unique index raises UniqueViolation.
    with pytest.raises((ValueError, UniqueViolation)):
        with world.recon.store.transaction(world.user, scope=PERSONAL) as tx:
            tx.put_event(
                dc_replace(tx.event(first["id"]), state="accepted", activity_id=activity)
            )
            tx.put_event(
                dc_replace(tx.event(second["id"]), state="accepted", activity_id=activity)
            )
    assert len(_open(world)) == 2


# --- Third review regressions (#772 Codex review of f740158) ---------------


@pytest.mark.parametrize("seen_on", ["card", "checking"])
def test_a_card_payment_puts_the_observed_account_on_its_own_leg(world, seen_on):
    card = new_account(world)
    checking = new_account(world, kind="checking")
    observed, other = (card, checking) if seen_on == "card" else (checking, card)
    bank = world.connect("plaid")
    link_accounts(world, observed, (bank, plaid(bank, "seed", amount="1")))
    direction = "inflow" if seen_on == "card" else "outflow"
    submit(
        world,
        bank,
        plaid(bank, "pay", amount="40", kind_hint="card_payment", direction=direction),
    )
    event = only(world)
    other_leg = "source_account_id" if seen_on == "card" else "destination_account_id"
    assert event["unresolved"] == [other_leg]
    world.recon.resolve(
        user_id=world.user,
        event_id=event["id"],
        version=event["version"],
        changes={other_leg: other},
        scope=PERSONAL,
    )
    accept(
        world,
        world.recon.detail(user_id=world.user, event_id=event["id"], scope=PERSONAL),
    )
    (activity,) = [a for a in activities(world) if a["kind"] == "card_payment"]
    legs = {leg["account_id"]: leg for leg in activity["legs"]}
    assert set(legs) == {card, checking}


def test_disconnecting_one_source_versions_the_event_others_still_back(world):
    card = new_account(world)
    wallet, bank = world.connect("shortcuts"), world.connect("plaid")
    link_accounts(
        world,
        card,
        (bank, plaid(bank, "seed", amount="1")),
        (wallet, tap(wallet, "seed-tap", amount="1")),
    )
    submit(world, wallet, tap(wallet))
    submit(world, bank, plaid(bank, "t1", status="posted"))
    event = only(world)
    assert {o["source"] for o in event["observations"]} == {"shortcuts", "plaid"}
    world.recon.forget_connection(user_id=world.user, connection_id=bank, scope=PERSONAL)
    after = only(world)
    assert after["id"] == event["id"]
    assert [o["source"] for o in after["observations"]] == ["shortcuts"]
    # A review based on the removed evidence is refused as stale.
    assert after["version"] > event["version"]
    with pytest.raises(StaleEvent):
        world.recon.resolve(
            user_id=world.user,
            event_id=event["id"],
            version=event["version"],
            changes={"note": "lunch"},
            scope=PERSONAL,
        )


def test_a_source_revision_that_now_matches_flags_both_events(world):
    card = new_account(world)
    gmail, bank = world.connect("gmail"), world.connect("plaid")
    link_accounts(world, card, (bank, plaid(bank, "seed", amount="1")))
    email = cand(
        gmail,
        "m1",
        source="gmail",
        amount="12.50",
        currency="USD",
        occurred_on=DAY,
        account={"mask": "4321"},
    )
    submit(world, gmail, email)
    submit(world, bank, plaid(bank, "t1", amount="99", status="posted"))
    [first] = _open(world, "gmail")
    [second] = _open(world, "plaid", "t1")
    assert first["possible_duplicates"] == second["possible_duplicates"] == []
    # The bank corrects the amount: now it may be the emailed purchase.
    submit(world, bank, plaid(bank, "t1", amount="12.50", status="posted"))
    first = world.recon.detail(user_id=world.user, event_id=first["id"], scope=PERSONAL)
    second = world.recon.detail(user_id=world.user, event_id=second["id"], scope=PERSONAL)
    assert second["possible_duplicates"] == [first["id"]]
    assert first["possible_duplicates"] == [second["id"]]
    assert first["attention"] == second["attention"] == "possible_duplicate"
    # And a revision that moves away again clears both sides.
    submit(world, bank, plaid(bank, "t1", amount="70", status="posted"))
    first = world.recon.detail(user_id=world.user, event_id=first["id"], scope=PERSONAL)
    assert first["possible_duplicates"] == [] and first["attention"] is None
