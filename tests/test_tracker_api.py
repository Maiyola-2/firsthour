import os, sys, tempfile
tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{tmp}/test.db"
os.environ.pop("FIRSTHOUR_API_KEY", None)
sys.path.insert(0, "backend")
from datetime import timedelta
from fastapi.testclient import TestClient
import tracker
from main import app

c = TestClient(app)
def ok(label, cond):
    print(("PASS " if cond else "FAIL ") + label)
    if not cond: raise SystemExit(1)

ok("old endpoints still work", c.get("/cases?lang=sw").status_code == 200 and c.post("/evidence/pdf", json={"lang": "en"}).status_code == 200)

r = c.post("/tracker/follow-ups", json={"chat_id": 5_000_000_000, "case_id": "sent_money", "plan_id": "plan_safaricom",
                                         "institution": "mobile_money", "reference": "  REF123 ", "days": 7, "lang": "sw"})
ok("create follow-up (64-bit chat id)", r.status_code == 200 and r.json()["reference"] == "REF123" and r.json()["status"] == "waiting")
fid = r.json()["id"]
from datetime import datetime as _dt
_gap = _dt.fromisoformat(r.json()["follow_up_at"]) - _dt.fromisoformat(r.json()["created_at"])
ok("follow-up date is exactly 7 days after creation", _gap == timedelta(days=7))

ok("list own follow-ups", len(c.get("/tracker/follow-ups?chat_id=5000000000").json()) == 1)
ok("others see nothing", c.get("/tracker/follow-ups?chat_id=42").json() == [])
ok("cannot read someone else's item", c.get(f"/tracker/follow-ups/{fid}?chat_id=42").status_code == 404)
ok("cannot resolve someone else's item", c.post(f"/tracker/follow-ups/{fid}/resolve", json={"chat_id": 42}).status_code == 404)
ok("not due yet", c.get("/tracker/due").json() == [])

# make it due by moving the date into the past
with tracker.SessionLocal() as db:
    row = db.get(tracker.FollowUp, fid); row.follow_up_at = tracker.utcnow() - timedelta(hours=1); db.commit()
due = c.get("/tracker/due").json()
ok("due after date passes", len(due) == 1 and due[0]["id"] == fid and due[0]["chat_id"] == 5_000_000_000)
c.post(f"/tracker/follow-ups/{fid}/reminded")
ok("not due again once reminded", c.get("/tracker/due").json() == [])

r = c.post(f"/tracker/follow-ups/{fid}/snooze", json={"chat_id": 5_000_000_000, "days": 3})
ok("snooze resets reminder", r.json()["reminded"] is False and r.json()["status"] == "waiting")
r = c.post(f"/tracker/follow-ups/{fid}/resolve", json={"chat_id": 5_000_000_000})
ok("resolve", r.json()["status"] == "resolved")
with tracker.SessionLocal() as db:
    row = db.get(tracker.FollowUp, fid); row.follow_up_at = tracker.utcnow() - timedelta(hours=1); row.reminded = False; db.commit()
ok("resolved items are never due", c.get("/tracker/due").json() == [])

for inst in tracker.INSTITUTIONS:
    for lang in ("en", "sw"):
        e = c.get(f"/tracker/escalation/{inst}?lang={lang}").json()
        assert e["steps"] and all(isinstance(x, str) for x in e["steps"]) and isinstance(e["label"], str) and isinstance(e["wait_note"], str)
ok("escalation for all institutions in both languages", True)
ok("bad institution rejected", c.get("/tracker/escalation/pirate").status_code == 422)
ok("validation: days out of range", c.post("/tracker/follow-ups", json={"chat_id": 1, "case_id": "x", "institution": "bank", "days": 999}).status_code == 422)
ok("validation: bad institution", c.post("/tracker/follow-ups", json={"chat_id": 1, "case_id": "x", "institution": "pirate"}).status_code == 422)

c.post("/tracker/follow-ups", json={"chat_id": 7, "case_id": "sent_money", "institution": "bank"})
c.post("/tracker/follow-ups", json={"chat_id": 7, "case_id": "sent_money", "institution": "police"})
ok("erase my data", c.delete("/tracker/chats/7").json() == {"deleted": 2} and c.get("/tracker/follow-ups?chat_id=7").json() == [])
ok("other users' data untouched by erase", len(c.get("/tracker/follow-ups?chat_id=5000000000").json()) == 1)

os.environ["FIRSTHOUR_API_KEY"] = "secret-test-key"
ok("api key required when set", c.get("/tracker/due").status_code == 401)
ok("wrong key rejected", c.get("/tracker/due", headers={"X-API-Key": "nope"}).status_code == 401)
ok("right key accepted", c.get("/tracker/due", headers={"X-API-Key": "secret-test-key"}).status_code == 200)
ok("non-tracker endpoints stay open", c.get("/cases").status_code == 200)
print("TRACKER API TESTS PASSED")
