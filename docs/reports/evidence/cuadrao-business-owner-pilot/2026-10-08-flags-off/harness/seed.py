"""Seed one owner through the real API with every flag on.

usage: seed.py <key> full|bystander
full: Personal account, expense, document and conversation; Business space,
account, a confirmed receipt expense, an unconfirmed Inbox receipt, a WhatsApp
link and one captured WhatsApp receipt. bystander: Personal account, expense and
document; Business space, account, a hand-entered expense and an Inbox receipt.
"""

from __future__ import annotations

import json
import random
import sys

from receipts import make
from rig import api, code, create_user, delivery, idem, load_world, save_world, token, until, webhook

key, role = sys.argv[1], sys.argv[2]
person = create_user(key)
media_id = str(700000000000000 + random.randrange(10**9))
phone = "1555" + str(random.randrange(10**7)).zfill(7)
files = make(key, media_id)
t = token(person)
ids: dict[str, str] = {}
log: dict[str, str] = {}


def step(name, result, pick=None):
    log[name] = str(result[0]) if name == "whatsapp_link_code" else code(result)
    status, body = result
    assert status < 300, (name, status, body)
    if pick:
        ids[name] = pick(body)
    return body


step("personal_account", api("POST", "/financial-accounts", t, headers=idem(),
     body={"type": "checking", "currency": "DOP", "nickname": f"Personal {key}"}), lambda b: b["id"])
expense = {"kind": "expense", "account_id": ids["personal_account"], "amount": "1200.00",
           "occurred_at": "2026-10-06T12:00:00-04:00", "note": f"Supermercado personal {key}", "category_id": "groceries"}
preview = step("personal_expense_preview", api("POST", "/financial-activities/preview", t, body=expense))
step("personal_expense", api("POST", "/financial-activities", t, headers=idem(), body={
    **expense, "expected_versions": preview.get("expected_versions"),
    **({"preview_token": preview["preview_token"]} if preview.get("preview_token") else {})}),
    lambda b: b["activity"]["activity_id"])
step("personal_document", api("POST", "/financial-documents", t, raw=files["personal"],
     headers={"Content-Type": "image/png", "X-Document-Filename": f"personal-{key}.png"}), lambda b: b["connection_id"])
if role == "full":
    step("conversation", api("POST", "/conversations", t, body={"title": f"Personal chat {key}"}), lambda b: b["conversation"]["id"])

step("space", api("POST", "/business/space", t, body={"language": "en"}), lambda b: b["id"])
step("business_account", api("POST", "/business/accounts", t, headers=idem(),
     body={"nickname": f"Operativa {key}", "type": "checking", "currency": "DOP"}), lambda b: b["id"])

if role == "full":
    up = step("receipt_confirmed", api("POST", "/business/receipts", t, raw=files["bizconfirm"], headers={
        "Content-Type": "image/png", "X-Document-Filename": f"ferreteria-{key}.png",
        "X-Extraction-Consent": "true", **idem()}), lambda b: b["id"])
    ready = until(lambda: (lambda r: r[1] if r[1].get("status") == "review_ready" else None)(
        api("GET", f"/business/receipts/{ids['receipt_confirmed']}", t)), 60)
    assert ready, "receipt never review_ready"
    reviewed = step("receipt_confirmed_review", api("PATCH", f"/business/receipts/{ids['receipt_confirmed']}/review", t,
                    body={"version": ready["version"], "fields": {"account_id": ids["business_account"], "category_id": "groceries"}}))
    confirmed = step("receipt_confirmed_confirm", api("POST", f"/business/receipts/{ids['receipt_confirmed']}/confirm", t,
                     headers=idem(), body={"version": reviewed["version"]}))
    ids["business_expense_from_receipt"] = confirmed["expense_id"]
    step("receipt_inbox", api("POST", "/business/receipts", t, raw=files["bizinbox"], headers={
        "Content-Type": "image/png", "X-Document-Filename": f"farmacia-{key}.png", **idem()}), lambda b: b["id"])
    issued = step("whatsapp_link_code", api("POST", "/whatsapp/link-codes", t, body={"language": "en"}))
    log["webhook_link"] = code(webhook(delivery("text_link_code.json", phone, {
        "id": f"wamid.FLAGSOFF-LINK-{key}", "text": {"body": issued["message_text"]}})))
    link = step("whatsapp_link", api("GET", "/whatsapp/link", t))
    assert link.get("linked") or link.get("status") == "active", link
    log["webhook_image"] = code(webhook(delivery("image_message.json", phone, {
        "id": f"wamid.FLAGSOFF-IMAGE-{key}", "type": "image",
        "image": {"caption": "Recibo colmado", "mime_type": "image/png", "sha256": "bG9jYWw=", "id": media_id}})))
    wa = until(lambda: next((i for i in api("GET", "/business/receipts?view=inbox", t)[1]["items"] if i["channel"] == "whatsapp"), None), 30)
    assert wa, "WhatsApp receipt never captured"
    ids["receipt_whatsapp"] = wa["id"]
else:
    step("business_expense_manual", api("POST", "/business/expenses", t, headers=idem(), body={
        "account_id": ids["business_account"], "amount": "300.00", "occurred_on": "2026-10-05",
        "merchant": f"Bystander supplies {key}", "category_id": "groceries"}), lambda b: b["id"])
    step("receipt_inbox", api("POST", "/business/receipts", t, raw=files["bizinbox"], headers={
        "Content-Type": "image/png", "X-Document-Filename": f"farmacia-{key}.png", **idem()}), lambda b: b["id"])

world = load_world()
world[key] = {**person, "role": role, "phone": phone, "media_id": media_id, "ids": ids}
save_world(world)
print(json.dumps({"key": key, "role": role, "calls": log, "ids": sorted(ids)}))
