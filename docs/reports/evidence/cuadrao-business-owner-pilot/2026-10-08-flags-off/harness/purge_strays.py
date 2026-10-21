"""Remove seed users that never reached world.json (a failed seed), and their Storage objects."""
from rig import STACK, db, http, load_world

known = {p["id"] for p in load_world().values()}
admin = {"apikey": STACK["SERVICE_ROLE_KEY"], "Authorization": f"Bearer {STACK['SERVICE_ROLE_KEY']}"}
c = db()
for (uid,) in c.execute("select id::text from auth.users").fetchall():
    if uid in known:
        continue
    names = [r[0] for r in c.execute("select name from storage.objects where bucket_id='financial-document-sources' and starts_with(name, %s)", (uid + "/",)).fetchall()]
    if names:
        http("DELETE", f"{STACK['API_URL']}/storage/v1/object/financial-document-sources", headers=admin, body={"prefixes": names})
    print("purged stray", http("DELETE", f"{STACK['API_URL']}/auth/v1/admin/users/{uid}", headers=admin)[0], len(names), "objects")
