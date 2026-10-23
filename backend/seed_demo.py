"""Fill the database with clearly labelled SYNTHETIC demo reports.

These rows are flagged is_demo=True. They never appear on the real dashboard,
only at http://127.0.0.1:8000/dashboard?demo=1, which shows a DEMO DATA banner.
Use them for presentations only, and say so. Never present them as real data.

Run from the backend folder (with venv active):
    python seed_demo.py            add demo data (replaces any earlier demo data)
    python seed_demo.py --clear    remove all demo data
"""

import random
import sys
from datetime import timedelta

from community import COUNTIES, IncidentReport, CASE_PLANS, kenya_today, monday_of
from tracker import SessionLocal, init_db

# Rough, invented weights. They are NOT real statistics.
COUNTY_WEIGHTS = {"Nairobi": 18, "Kakamega": 14, "Mombasa": 10, "Kisumu": 9, "Bungoma": 8,
                  "Nakuru": 8, "Kiambu": 7, "Vihiga": 5, "Busia": 5, "Uasin Gishu": 5, "Machakos": 4, "Kisii": 3}
PLAN_WEIGHTS = {"plan_safaricom": 30, "plan_money_lost": 14, "plan_details_shared": 12, "plan_whatsapp": 22,
                "plan_social": 8, "plan_bank_transfer": 7, "plan_remote_access": 6, "plan_email": 4,
                "plan_other_payment": 3, "plan_mobile_money": 3, "plan_nothing_shared": 2}


def plan_to_case(plan_id: str) -> str:
    return next(case for case, plans in CASE_PLANS.items() if plan_id in plans)


def main() -> None:
    init_db()
    with SessionLocal() as db:
        db.query(IncidentReport).filter(IncidentReport.is_demo.is_(True)).delete()
        if "--clear" in sys.argv:
            db.commit()
            print("Demo data removed.")
            return
        rng = random.Random(2026)
        this_week = monday_of(kenya_today())
        for weeks_ago in range(12):
            week = this_week - timedelta(days=7 * weeks_ago)
            for _ in range(rng.randint(8, 22)):
                plan = rng.choices(list(PLAN_WEIGHTS), weights=list(PLAN_WEIGHTS.values()))[0]
                county = rng.choices(list(COUNTY_WEIGHTS), weights=list(COUNTY_WEIGHTS.values()))[0]
                if rng.random() < 0.12:
                    county = None
                db.add(IncidentReport(case_id=plan_to_case(plan), plan_id=plan, county=county,
                                      week_start=week, is_demo=True))
        db.commit()
        total = db.query(IncidentReport).filter(IncidentReport.is_demo.is_(True)).count()
        print(f"Added {total} SYNTHETIC demo reports. View them at /dashboard?demo=1")


if __name__ == "__main__":
    main()
