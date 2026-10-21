"""One flag state's checks: separation, what A can read and download, deletion.

usage: probe.py <STATE> [--no-delete]
A is the read-only subject, B the bystander, D<STATE> the owner whose data is
disconnected and then deleted. Writes results/<STATE>.json. Counts and status
codes only; no document content and no secrets.
"""

from __future__ import annotations

import hashlib
import json
import random
import sys
import time
from pathlib import Path

from counts import business_links, counts, fingerprint, link_hashes
from rig import HERE, api, code, db, delivery, http, idem, load_world, token, webhook

STATE = sys.argv[1]
ON = STATE == "ON"
world = load_world()
A, B = world["A"], world["B"]
D = world.get(f"D{STATE}")
ta, tb = token(A), token(B)
checks: list[dict] = []
observations: dict = {}
RANGE = "from=2026-10-01&to=2026-10-31"


def check(cid: str, name: str, ok: bool, detail=None) -> bool:
    checks.append({"id": cid, "name": name, "pass": bool(ok), "detail": detail})
    print(("PASS" if ok else "FAIL"), cid, name, json.dumps(detail, default=str)[:300], flush=True)
    return ok


def hits(body, needles: dict[str, str]) -> list[str]:
    text = json.dumps(body, default=str) if not isinstance(body, bytes) else ""
    return sorted(label for label, needle in needles.items() if needle and needle in text)


def business_needles(owner: dict) -> dict[str, str]:
    i = owner["ids"]
    keys = ("space", "business_account", "receipt_confirmed", "receipt_inbox", "receipt_whatsapp",
            "business_expense_from_receipt", "business_expense_manual")
    found = {f"{owner['label']}.{k}": i[k] for k in keys if k in i}
    found.update({f"{owner['label']}.merchant.{m}": m for m in ("FERRETERIA", "COLMADO", "FARMACIA", "Bystander supplies")})
    found[f"{owner['label']}.business_account_name"] = f"Operativa {owner['label']}"
    return found


def all_needles(owner: dict) -> dict[str, str]:
    return {f"{owner['label']}.{k}": v for k, v in owner["ids"].items()} | {
        f"{owner['label']}.personal_note": f"Supermercado personal {owner['label']}",
        f"{owner['label']}.personal_account_name": f"Personal {owner['label']}"}


def personal_reads(t: str, owner: dict) -> dict:
    i = owner["ids"]
    paths = ["/financial-accounts", "/financial-home", "/financial-activities/purchases", "/financial-activities/options",
             "/financial-documents", "/financial-connections", "/financial-imports", "/financial-imports?state=accepted",
             "/financial-plan", "/conversations", f"/financial-accounts/{i['personal_account']}/activity",
             "/financial-search?q=FERRETERIA", "/financial-search?q=COLMADO", "/financial-search?q=FARMACIA",
             "/financial-search?q=Operativa", "/financial-search?q=Supermercado", "/financial-search?q=1850",
             "/search?q=FERRETERIA"]
    return {p: api("GET", p, t) for p in paths}


def sha(b) -> str | None:
    return hashlib.sha256(b).hexdigest() if isinstance(b, bytes) else None


def business_routes(owner: dict) -> list[tuple[str, str, dict]]:
    i = owner["ids"]
    r = i["receipt_confirmed"]
    return [
        ("GET", "/business/space", {}), ("POST", "/business/space", {"body": {"language": "en"}}),
        ("PATCH", "/business/space", {"body": {"name": "Renamed while off"}}),
        ("GET", "/business/workspace", {}),
        ("POST", "/business/accounts", {"body": {"nickname": "off", "type": "checking", "currency": "DOP"}, "headers": idem()}),
        ("POST", "/business/receipts", {"raw": b"\x89PNG\r\n\x1a\n", "headers": {"Content-Type": "image/png", **idem()}}),
        ("GET", "/business/receipts?view=all", {}), ("GET", "/business/receipts?view=inbox", {}),
        ("GET", f"/business/receipts/{r}", {}), ("GET", f"/business/receipts/{r}/source", {}),
        ("GET", f"/business/receipts/{i['receipt_whatsapp']}/source", {}),
        ("POST", f"/business/receipts/{i['receipt_inbox']}/prepare", {"headers": {"X-Extraction-Consent": "true"}}),
        ("PATCH", f"/business/receipts/{i['receipt_inbox']}/review", {"body": {"version": 0, "fields": {"merchant": "off"}}}),
        ("POST", f"/business/receipts/{i['receipt_inbox']}/confirm", {"body": {"version": 1}, "headers": idem()}),
        ("GET", f"/business/expenses?{RANGE}", {}),
        ("POST", "/business/expenses", {"body": {"account_id": i["business_account"], "amount": "1.00", "occurred_on": "2026-10-07"}, "headers": idem()}),
        ("GET", "/business/search?q=FERRETERIA", {}), ("GET", f"/business/overview?{RANGE}", {}), ("GET", "/business/updates", {}),
        ("POST", "/whatsapp/link-codes", {"body": {"language": "en"}}), ("GET", "/whatsapp/link", {}),
        ("DELETE", "/whatsapp/link", {}),
        ("GET", "/webhooks/whatsapp?hub.mode=subscribe&hub.verify_token=x&hub.challenge=1", {}),
    ]


def snapshot_business(owner: dict, t: str) -> dict:
    links = business_links(owner["id"])
    return {"counts": counts(owner["id"]), "links": links, "links_fingerprint": fingerprint(links)}


# ---------------------------------------------------------------- 1. Separation
reads_a = personal_reads(ta, A)
foreign_for_a = business_needles(A) | all_needles(B) | ({} if D is None else all_needles(D))
leak = {p: {"status": r[0], "business_or_foreign_hits": hits(r[1], foreign_for_a)} for p, r in reads_a.items()}
observations["personal_reads_A"] = leak
gated_404 = {"/financial-documents"} if STATE in ("S3", "S4") else set()
ingestion_paths = {"/financial-documents", "/financial-connections", "/financial-imports", "/financial-imports?state=accepted"}
for p, r in reads_a.items():
    expected = 404 if (STATE == "S4" and p in ingestion_paths) or p in gated_404 else 200
    check("1.1", f"A Personal read {p} shows no Business row and nothing of B or D",
          r[0] == expected and not leak[p]["business_or_foreign_hits"], {"status": r[0], "expected": expected, "hits": leak[p]["business_or_foreign_hits"]})
home = reads_a["/financial-home"][1]
dop = next((c for c in home.get("currencies", []) if c["currency"] == "DOP"), {}) if isinstance(home, dict) else {}
check("1.2", "A Personal home totals are Personal only (1,200.00 DOP purchases; Business 1,850.00 excluded)",
      dop.get("gross_purchases_minor") == "120000" and dop.get("known_accounts", 0) + dop.get("unknown_accounts", 0) == 1,
      {k: dop.get(k) for k in ("gross_purchases_minor", "net_spending_minor", "known_accounts", "unknown_accounts")})
positive = {
    "accounts list has Personal account": A["ids"]["personal_account"] in json.dumps(reads_a["/financial-accounts"][1]),
    "purchases has Personal expense": A["ids"]["personal_expense"] in json.dumps(reads_a["/financial-activities/purchases"][1]),
    "search finds Personal expense": A["ids"]["personal_expense"] in json.dumps(reads_a["/financial-search?q=Supermercado"][1]),
    "conversations has Personal chat": A["ids"]["conversation"] in json.dumps(reads_a["/conversations"][1]),
}
if STATE not in ("S3", "S4"):
    positive["documents list has Personal document"] = A["ids"]["personal_document"] in json.dumps(reads_a["/financial-documents"][1])
check("1.3", "positive control: A's own Personal rows are visible on the same reads", all(positive.values()), positive)

with db() as _c:
    business_event_id = str(_c.execute("select event_id from public.financial_import_observations where connection_id=%s",
                                       (A["ids"]["receipt_confirmed"],)).fetchone()[0])
direct = {
    "GET /financial-accounts/{Business account}": api("GET", f"/financial-accounts/{A['ids']['business_account']}", ta),
    "GET /financial-accounts/{Business account}/activity": api("GET", f"/financial-accounts/{A['ids']['business_account']}/activity", ta),
    "GET /financial-activities/{Business expense}": api("GET", f"/financial-activities/{A['ids']['business_expense_from_receipt']}", ta),
    "GET /financial-activities/{Business expense}/history": api("GET", f"/financial-activities/{A['ids']['business_expense_from_receipt']}/history", ta),
    "GET /financial-documents/{confirmed receipt}": api("GET", f"/financial-documents/{A['ids']['receipt_confirmed']}", ta),
    "GET /financial-documents/{confirmed receipt}/source": api("GET", f"/financial-documents/{A['ids']['receipt_confirmed']}/source", ta),
    "GET /financial-documents/{Inbox receipt}/source": api("GET", f"/financial-documents/{A['ids']['receipt_inbox']}/source", ta),
    "GET /financial-documents/{WhatsApp receipt}/source": api("GET", f"/financial-documents/{A['ids']['receipt_whatsapp']}/source", ta),
    "GET /financial-imports/{Business event}": api("GET", f"/financial-imports/{business_event_id}", ta),
    "POST /financial-activities/preview on the Business account": api("POST", "/financial-activities/preview", ta, body={
        "kind": "expense", "account_id": A["ids"]["business_account"], "amount": "5.00",
        "occurred_at": "2026-10-07T12:00:00-04:00", "note": "cross", "category_id": "groceries"}),
}
observations["direct_personal_routes_on_business_ids"] = {k: code(v) for k, v in direct.items()}
check("1.4", "Personal routes answer 404 for A's Business account, expense, receipts and their originals",
      all(v[0] == 404 for v in direct.values()), observations["direct_personal_routes_on_business_ids"])

routes = [r for r in business_routes(A) if not ON or (r[0] == "GET" and "webhooks" not in r[1])]
route_codes = {}
for who, t in (("A", ta), ("signed out", None)):
    for method, path, kw in routes:
        route_codes[f"{who}: {method} {path.split('?')[0]}"] = code(api(method, path, t, **kw))
observations["business_and_whatsapp_routes"] = route_codes
if ON:
    on_ok = {k: v for k, v in route_codes.items() if k.startswith("A: GET /business")}
    check("1.5", "positive control (flags on): A's Business and WhatsApp GET routes answer 200",
          all(v.startswith("200") for v in on_ok.values()) and route_codes["A: GET /whatsapp/link"].startswith("200"), on_ok)
else:
    check("1.5", "every /api/v1/business/* and WhatsApp route answers 404, signed in and signed out",
          all(v.startswith("404") for v in route_codes.values()), sorted({v for v in route_codes.values()}))

if not ON:
    before = counts(A["id"])
    media_id = str(800000000000000 + random.randrange(10**9))
    (HERE / "media" / f"{media_id}.png").write_bytes((HERE / "receipts" / "A-wa.png").read_bytes())
    raw = delivery("image_message.json", A["phone"], {"id": f"wamid.FLAGSOFF-OFF-{STATE}-{int(time.time())}", "type": "image",
                   "image": {"caption": "off", "mime_type": "image/png", "sha256": "bG9jYWw=", "id": media_id}})
    (HERE / "results" / f"refused-delivery-{STATE}.json").write_bytes(raw)
    result = webhook(raw)
    time.sleep(3)
    after = counts(A["id"])
    observations["webhook_signed_delivery"] = {"response": code(result), "inbound_before": before["whatsapp_inbound_messages_to_owner"],
                                               "inbound_after": after["whatsapp_inbound_messages_to_owner"],
                                               "business_connections_before": before["financial_source_connections.business"],
                                               "business_connections_after": after["financial_source_connections.business"]}
    check("1.6", "a signed WhatsApp delivery is refused with 404 and nothing is captured or recorded",
          result[0] == 404 and before == after, observations["webhook_signed_delivery"])

reads_b = personal_reads(tb, B)
foreign_for_b = all_needles(A) | ({} if D is None else all_needles(D))
leak_b = {p: hits(r[1], foreign_for_b) for p, r in reads_b.items()}
direct_b = {
    "personal account": api("GET", f"/financial-accounts/{A['ids']['personal_account']}", tb),
    "personal expense": api("GET", f"/financial-activities/{A['ids']['personal_expense']}", tb),
    "personal document source": api("GET", f"/financial-documents/{A['ids']['personal_document']}/source", tb),
    "conversation messages": api("GET", f"/conversations/{A['ids']['conversation']}/messages", tb),
    "Business receipt source (Business route)": api("GET", f"/business/receipts/{A['ids']['receipt_confirmed']}/source", tb),
    "Business account (Personal route)": api("GET", f"/financial-accounts/{A['ids']['business_account']}", tb),
}
observations["owner_B"] = {"reads_hits": {p: h for p, h in leak_b.items() if h}, "direct": {k: code(v) for k, v in direct_b.items()}}
check("1.7", "owner B sees nothing of A's (or D's) on B's Personal reads, and A's ids answer 404 to B",
      not any(leak_b.values()) and all(v[0] == 404 for v in direct_b.values()), observations["owner_B"])

# ---------------------------------------------------------------- 2. A reads and downloads
pd = A["ids"]["personal_document"]
doc_get = api("GET", f"/financial-documents/{pd}", ta)
doc_src = api("GET", f"/financial-documents/{pd}/source", ta)
expected_sha = hashlib.sha256((HERE / "receipts" / "A-personal.png").read_bytes()).hexdigest()
biz_src = {k: api("GET", f"/business/receipts/{A['ids'][k]}/source", ta) for k in ("receipt_confirmed", "receipt_inbox", "receipt_whatsapp")}
biz_expected = {k: hashlib.sha256((HERE / "receipts" / f"A-{n}.png").read_bytes()).hexdigest()
                for k, n in (("receipt_confirmed", "bizconfirm"), ("receipt_inbox", "bizinbox"), ("receipt_whatsapp", "wa"))}
matrix = {
    "Personal account": {"read": code(api("GET", f"/financial-accounts/{A['ids']['personal_account']}", ta))},
    "Personal expense": {"read": code(api("GET", f"/financial-activities/{A['ids']['personal_expense']}", ta))},
    "Personal document": {"read": code(doc_get), "download": code(doc_src),
                          "download_sha_matches": sha(doc_src[1]) == expected_sha},
    "Personal conversation": {"read": code(api("GET", f"/conversations/{A['ids']['conversation']}/messages", ta))},
    "Business account": {"personal_route": code(direct["GET /financial-accounts/{Business account}"]),
                         "business_route": route_codes["A: GET /business/workspace"]},
    "Business expense (from receipt)": {"personal_route": code(direct["GET /financial-activities/{Business expense}"]),
                                        "business_route": route_codes["A: GET /business/expenses"]},
}
for k, label in (("receipt_confirmed", "Business receipt, confirmed"), ("receipt_inbox", "Business receipt, Inbox"),
                 ("receipt_whatsapp", "Business receipt, WhatsApp")):
    matrix[label] = {"personal_route_download": code(api("GET", f"/financial-documents/{A['ids'][k]}/source", ta)),
                     "business_route_download": code(biz_src[k]),
                     "download_sha_matches": sha(biz_src[k][1]) == biz_expected[k]}
matrix["WhatsApp link"] = {"read": route_codes["A: GET /whatsapp/link"], "revoke": route_codes.get("A: DELETE /whatsapp/link", "not called with flags on")}
observations["matrix_A"] = matrix
if STATE in ("ON", "S1", "S2"):
    check("2.1", "A can read the Personal document and download its original (sha256 matches)",
          doc_get[0] == 200 and doc_src[0] == 200 and sha(doc_src[1]) == expected_sha, matrix["Personal document"])
else:
    check("2.1", "Personal document read and download are off with the document surface (404), not leaked elsewhere",
          doc_get[0] == 404 and doc_src[0] == 404, matrix["Personal document"])
if not ON:
    check("2.2", "Business receipts cannot be listed or downloaded through any route while Business is off",
          all(v[0] == 404 for v in biz_src.values()) and all(direct[k][0] == 404 for k in direct if "receipt" in k),
          {k: code(v) for k, v in biz_src.items()})
else:
    check("2.2", "positive control (flags on): each Business original downloads with a matching sha256",
          all(v[0] == 200 and sha(v[1]) == biz_expected[k] for k, v in biz_src.items()), {k: code(v) for k, v in biz_src.items()})

# ---------------------------------------------------------------- 3. Deletion on D
if D is not None and "--no-delete" not in sys.argv:
    td = token(D)
    dh = link_hashes(D["id"])
    others_before = {"A": counts(A["id"]), "B": counts(B["id"])}
    d_before = counts(D["id"], dh)
    observations["D_counts_before"] = d_before
    delete_only = "--delete-only" in sys.argv
    cross = {} if delete_only else {
        "POST /financial-connections/{D Business receipt}/disconnect": api("POST", f"/financial-connections/{D['ids']['receipt_confirmed']}/disconnect", td),
        "POST /financial-connections/{D WhatsApp receipt}/disconnect": api("POST", f"/financial-connections/{D['ids']['receipt_whatsapp']}/disconnect", td),
    }
    d_after_cross = counts(D["id"], dh)
    observations["D_personal_route_disconnect_of_business_receipts"] = {k: code(v) for k, v in cross.items()}
    if not delete_only:
      check("3.1", "a Personal-route disconnect of a Business receipt is refused and changes nothing",
          all(v[0] == 404 for v in cross.values()) and d_after_cross == d_before, observations["D_personal_route_disconnect_of_business_receipts"])

    def prefix_count(prefix: str) -> int:
        with db() as c:
            return c.execute("select count(*) from storage.objects where bucket_id='financial-document-sources' and starts_with(name, %s)", (prefix,)).fetchone()[0]

    doc_prefix = f"{D['id']}/{D['ids']['personal_document']}/"
    obj_before = prefix_count(doc_prefix)
    disc = (0, {}) if delete_only else api("POST", f"/financial-connections/{D['ids']['personal_document']}/disconnect", td)
    time.sleep(1)
    obj_after = prefix_count(doc_prefix)
    observations["D_personal_document_disconnect"] = {"response": code(disc), "objects_under_document_prefix_before": obj_before,
                                                      "objects_under_document_prefix_after": obj_after,
                                                      "objects_under_owner_prefix_after": prefix_count(f"{D['id']}/")}
    if delete_only:
        pass
    elif STATE == "S4":
        check("3.2", "S4: Personal document disconnect is unavailable (ingestion surface 404); the object stays until account deletion",
              disc[0] == 404 and obj_before == obj_after == 1, observations["D_personal_document_disconnect"])
    else:
        check("3.2", "Personal document disconnect removes its Storage object (prefix count 1 -> 0)",
              disc[0] == 200 and obj_before == 1 and obj_after == 0, observations["D_personal_document_disconnect"])

    attempts = []
    with db() as c:
        started_at = c.execute("select now()").fetchone()[0]
    t_del = td
    for n in range(8):
        s, b = api("POST", "/account/delete", t_del, body={"confirm": True})
        attempts.append(f"{s} {b.get('status', b.get('code', '')) if isinstance(b, dict) else ''} {b.get('pending', '') if isinstance(b, dict) else ''}".strip())
        if s == 200 or s in (400, 401, 403, 404, 422, 429):
            break
        time.sleep(3)
        try:
            t_del = token(D)
        except AssertionError:
            pass
    d_after = counts(D["id"], dh)
    subject = hashlib.sha256(f"argus:account-deletion:{D['id']}".encode()).hexdigest()
    with db() as c:
        # A finished run drops user_id and subject_hash by design, so it is found by its time window.
        run = c.execute("select status, steps from argus_private.account_deletion_runs where subject_hash=%s"
                        " union all select status, steps from argus_private.account_deletion_runs"
                        " where subject_hash is null and created_at >= %s", (subject, started_at)).fetchone()
    others_after = {"A": counts(A["id"]), "B": counts(B["id"])}
    observations["D_account_deletion"] = {"attempts": attempts, "counts_after": d_after,
                                         "run_status": run[0] if run else None,
                                         "run_steps": {k: v for k, v in (run[1] or {}).items() if k in ("storage", "analytics", "pending", "counts", "pending_since", "last_error")} if run else None}
    check("3.3", "account deletion of a person with Business data finishes while Business is off (run done)",
          attempts and attempts[-1].startswith("200 done") and run and run[0] == "done", {"attempts": attempts, "run": run[0] if run else None})
    nonzero = {k: v for k, v in d_after.items() if v}
    check("3.4", "after deletion: zero rows in every Personal and Business table and zero Storage objects for D", not nonzero, nonzero or "all zero")
    check("3.5", "owners A and B untouched by D's disconnect and deletion", others_before == others_after,
          {k: {f: (others_before[k][f], others_after[k][f]) for f in others_before[k] if others_before[k][f] != others_after[k][f]} for k in others_before})

Path(HERE / "results").mkdir(exist_ok=True)
(HERE / "results" / f"{STATE}{'-delete' if '--delete-only' in sys.argv else ''}.json").write_text(json.dumps({"state": STATE, "checks": checks, "observations": observations}, indent=1, default=str))
print(f"{STATE}: {sum(c['pass'] for c in checks)}/{len(checks)} pass")
