"""Local verification only: seed owned artifacts, use the real receipt pipeline."""
from __future__ import annotations

import json
import os
from pathlib import Path

from argus.api import state
from argus.api.main import app
from argus.api.public_excerpts import create_receipt_for_artifact
from tests.public_excerpt_factories import (
    build_chart, build_conversation, build_run, build_template_artifact,
    generated_card_snapshot, stable_uuid,
)
import uvicorn

OUT = Path(__file__).parent
state.store.reset()
user = state.store.get_or_create_dev_user()
receipts = {}
for index, (template, title) in enumerate([
    ("buy_and_hold", "Apple vs SPY, twelve months"),
    ("dca_accumulation", "Building an Apple position with monthly contributions"),
], start=1):
    # Title is author text; use a period-independent title for the actual fixture.
    if template == "buy_and_hold":
        title = "Apple vs SPY, a historical comparison"
    conversation = build_conversation(conversation_id=stable_uuid(index, prefix=1))
    artifact, card = build_template_artifact(template, title=title, modeled_costs=True)
    chart = build_chart(points=44)
    artifact.id = stable_uuid(index, prefix=3)
    artifact.source_conversation_id = conversation.id
    artifact.source_run_id = stable_uuid(index, prefix=2)
    run = build_run(run_id=artifact.source_run_id, chart=chart)
    run.conversation_id = conversation.id
    run.config_snapshot = generated_card_snapshot(template, modeled_costs=True)
    run.conversation_result_card = card
    for collection, owners, obj in [
        (state.store.conversations, state.store.conversation_owners, conversation),
        (state.store.evidence_artifacts, state.store.evidence_artifact_owners, artifact),
        (state.store.backtest_runs, state.store.backtest_run_owners, run),
    ]:
        collection[obj.id] = obj
        owners[obj.id] = user.id
    snapshot, created = create_receipt_for_artifact(
        user=user, artifact_id=artifact.id,
        owner_note="A historical comparison to help understand this idea.",
    )
    assert created
    receipts[template] = {"url": f"http://127.0.0.1:3317/r/{snapshot.public_id}",
                          "public_id": snapshot.public_id,
                          "payload": snapshot.payload.model_dump(mode="json")}

(OUT / "receipts.json").write_text(json.dumps(receipts, indent=2))
assert os.environ["CUADRAO_MOCK_AUTH"] == "false"
assert state.supabase_gateway is None

@app.middleware("http")
async def record_public_request(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/api/v1/public/"):
        record = {"path": request.url.path, "method": request.method,
                  "authorization_present": "authorization" in request.headers,
                  "cookie_present": "cookie" in request.headers,
                  "status": response.status_code}
        with (OUT / "backend-requests.jsonl").open("a") as stream:
            stream.write(json.dumps(record) + "\n")
    return response

if __name__ == "__main__":
    # Chat runtime startup is unnecessary for receipt reads; real routers and
    # middleware run unchanged, with no provider credentials and memory storage.
    uvicorn.run(app, host="127.0.0.1", port=8317, lifespan="off")
