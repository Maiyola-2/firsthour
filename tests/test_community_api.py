import os, sys, tempfile
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tempfile.mkdtemp(), "c.db")
os.environ.pop("FIRSTHOUR_API_KEY", None)
sys.path.insert(0, "backend")
from datetime import timedelta
from fastapi.testclient import TestClient
import community
from tracker import SessionLocal
from main import app

c = TestClient(app)
def ok(label, cond):
    print(("PASS " if cond else "FAIL ") + label)
    if not cond: raise SystemExit(1)

ok("47 counties", len(community.COUNTIES) == 47 and len(set(community.COUNTIES)) == 47 and "Kakamega" in community.COUNTIES)
ok("every plan has a chart label", all(p in community.SUBTYPE_LABELS for plans in community.CASE_PLANS.values() for p in plans))
ok("older endpoints still work", c.get("/cases").status_code == 200 and c.get("/tracker/due").status_code == 200)

s = c.get("/community/stats").json()
ok("empty stats are safe", s["total_shown"] is None and s["by_type"] == [] and s["by_county"] == [])

post = lambda **kw: c.post("/community/reports", json=kw)
ok("report accepted", post(case_id="sent_money", plan_id="plan_safaricom", county="Kakamega").json() == {"ok": True})
ok("unknown case rejected", post(case_id="nope").status_code == 422)
ok("plan from another case rejected", post(case_id="sent_money", plan_id="plan_whatsapp").status_code == 422)
ok("unknown county rejected", post(case_id="sent_money", county="Atlantis").status_code == 422)
ok("county optional", post(case_id="sent_money", plan_id="plan_safaricom").status_code == 200)

s = c.get("/community/stats").json()
ok("1-2 reports are hidden everywhere", s["total_shown"] is None and s["by_type"] == [] and s["by_county"] == [] and s["by_subtype"] == [])
ok("small weeks show as hidden (null), not the real count", any(w["count"] is None for w in s["by_week"]) and all(w["count"] in (None, 0) for w in s["by_week"]))

for _ in range(3): post(case_id="sent_money", plan_id="plan_safaricom", county="Kakamega")
post(case_id="sent_money", plan_id="plan_bank_transfer", county="Kisumu")
post(case_id="hijacked_account", plan_id="plan_whatsapp", county="Nairobi")
s = c.get("/community/stats").json()
types = {r["id"]: r["count"] for r in s["by_type"]}
ok("large group shown, single-report group hidden", types == {"sent_money": 6})
ok("no group below the minimum is ever shown", all(r["count"] >= 3 for key in ("by_type", "by_subtype", "by_county") for r in s[key]))
ok("subtype label localised", any(r["label"] == "Safaricom M-PESA" or "Safaricom" in r["label"] for r in s["by_subtype"]))
ok("single-report counties are not shown by name", [r["id"] for r in s["by_county"] if r["id"] not in ("other",)] == ["Kakamega"])

# small cells merge into 'other' only when that is itself big enough
for county in ("Kisumu", "Nairobi", "Mombasa"): post(case_id="sent_money", plan_id="plan_safaricom", county=county)
s = c.get("/community/stats").json()
ids = [r["id"] for r in s["by_county"]]
ok("small counties merge into an 'Other' row once big enough", "other" in ids and all(r["count"] >= 3 for r in s["by_county"]))
sw = c.get("/community/stats?lang=sw").json()
ok("swahili labels", any("Nyingine" in r["label"] for r in sw["by_county"]) and sw["by_type"][0]["label"] in ("Nilituma pesa kwa tapeli", "Akaunti iliyodukuliwa"))

# no identifying data stored
with SessionLocal() as db:
    cols = {col.name for col in community.IncidentReport.__table__.columns}
ok("table holds no identifying columns", cols == {"id", "case_id", "plan_id", "county", "week_start", "is_demo"})
ok("week is a Monday, not an exact time", all(r.week_start.weekday() == 0 for r in SessionLocal().scalars(__import__("sqlalchemy").select(community.IncidentReport))))

# demo data stays separate from real data
import subprocess
env = dict(os.environ, PYTHONPATH="backend")
out = subprocess.run([sys.executable, "seed_demo.py"], cwd="backend", env=env, capture_output=True, text=True)
ok("seed script runs", "SYNTHETIC" in out.stdout and out.returncode == 0)
real = c.get("/community/stats?data=real").json()
demo = c.get("/community/stats?data=demo").json()
ok("demo data never leaks into real stats", real["total_shown"] == 9 and real["total_shown"] != demo["total_shown"])
ok("demo stats are populated and labelled", demo["data"] == "demo" and demo["total_shown"] > 100 and len(demo["by_week"]) >= 12)
out = subprocess.run([sys.executable, "seed_demo.py", "--clear"], cwd="backend", env=env, capture_output=True, text=True)
ok("demo data can be cleared", c.get("/community/stats?data=demo").json()["total_shown"] is None)
ok("clearing demo data keeps real reports", c.get("/community/stats?data=real").json()["total_shown"] == real["total_shown"])

# dashboard page and validation
r = c.get("/dashboard")
ok("dashboard page served", r.status_code == 200 and "FirstHour Community Dashboard" in r.text and "text/html" in r.headers["content-type"])
ok("days validation", c.get("/community/stats?days=1").status_code == 422 and c.get("/community/stats?data=other").status_code == 422)

# submitting needs the key when one is set, reading stats does not
os.environ["FIRSTHOUR_API_KEY"] = "k"
ok("submit needs api key", post(case_id="sent_money").status_code == 401)
ok("stats stay public", c.get("/community/stats").status_code == 200 and c.get("/dashboard").status_code == 200)
print("COMMUNITY API TESTS PASSED")
