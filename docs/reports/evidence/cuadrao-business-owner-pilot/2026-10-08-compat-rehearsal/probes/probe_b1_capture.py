"""Build 1 capture onto a row Build 2 stored in Storage: the store-level error."""
import json, os
from pathlib import Path
from psycopg_pool import ConnectionPool
from argus.domain.ingestion.documents.store_postgres import PostgresDocumentStore
state = json.loads(Path(os.environ["COMPAT_HANDOFF"]).read_text())
pool = ConnectionPool(os.environ["ARGUS_DISPOSABLE_DATABASE_URL"], min_size=0, max_size=2, open=True)
store = PostgresDocumentStore(pool)
cid, uid = state["docs"]["a"], state["u"]["id"]
draft = store.draft(user_id=uid, connection_id=cid)
try:
    store.capture(user_id=uid, draft=draft, content=b"%PDF replay")
    print("capture: ok")
except Exception as e:
    print("capture:", type(e).__name__, str(e).splitlines()[0])
