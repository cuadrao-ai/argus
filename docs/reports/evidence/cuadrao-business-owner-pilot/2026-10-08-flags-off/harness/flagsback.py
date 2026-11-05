"""snapshot: A's Business state through the DB and the API. compare: flags back on, same state?
replay: redeliver the delivery S1 refused, now that intake is on again.

usage: flagsback.py snapshot <name> | compare <name> | replay <STATE>
"""

from __future__ import annotations

import json
import sys

from counts import business_links, counts, fingerprint
from rig import HERE, api, code, load_world, token, webhook

world = load_world()
A = world["A"]
RANGE = "from=2026-10-01&to=2026-10-31"


def api_view(t: str) -> dict:
    expenses = api("GET", f"/business/expenses?{RANGE}", t)
    receipts = api("GET", "/business/receipts?view=all", t)
    inbox = api("GET", "/business/receipts?view=inbox", t)
    overview = api("GET", f"/business/overview?{RANGE}", t)
    link = api("GET", "/whatsapp/link", t)
    return {
        "status": {k: code(v) for k, v in (("expenses", expenses), ("receipts", receipts), ("inbox", inbox), ("overview", overview), ("link", link))},
        "expense_receipt_links": sorted((e["id"], e["receipt_id"], e["amount"], e["account_id"]) for e in expenses[1]["items"]),
        "receipts": sorted((r["id"], r["status"], r["channel"]) for r in receipts[1]["items"]),
        "inbox": sorted(r["id"] for r in inbox[1]["items"]),
        "totals": overview[1].get("totals"),
        "link_active": link[1].get("linked", link[1].get("status")),
    }


def snapshot() -> dict:
    links = business_links(A["id"])
    return {"counts": counts(A["id"]), "db_links": links, "db_links_fingerprint": fingerprint(links), "api": api_view(token(A))}


mode, name = sys.argv[1], sys.argv[2]
path = HERE / "results" / f"A-business-{name}.json"
if mode == "snapshot":
    path.write_text(json.dumps(snapshot(), indent=1, default=str))
    print("saved", path.name)
elif mode == "compare":
    before, after = json.loads(path.read_text()), json.loads(json.dumps(snapshot(), default=str))
    diff = {k: (before[k], after[k]) for k in before if before[k] != after[k]}
    (HERE / "results" / f"A-business-{name}-after-flags-on.json").write_text(json.dumps(after, indent=1))
    print(json.dumps({"identical": not diff, "differences": list(diff), "counts": after["counts"],
                      "api": after["api"], "db_links_fingerprint": after["db_links_fingerprint"]}, default=str))
elif mode == "replay":
    raw = (HERE / "results" / f"refused-delivery-{name}.json").read_bytes()
    before = counts(A["id"])
    result = webhook(raw)
    import time

    time.sleep(4)
    after = counts(A["id"])
    t = token(A)
    wa = [r for r in api("GET", "/business/receipts?view=inbox", t)[1]["items"] if r["channel"] == "whatsapp"]
    print(json.dumps({"response": code(result), "changed": {k: (before[k], after[k]) for k in before if before[k] != after[k]},
                      "whatsapp_inbox_items": len(wa)}))
