"""FirstHour community statistics (Phase 5, feature 3).

Victims can choose to share an incident anonymously. Only three things are
stored: the type of incident, an optional county, and the week it happened.
No chat id, no name, no reference number, no exact time.

The public dashboard shows only totals. Any group with fewer than
MIN_GROUP_SIZE reports is hidden, so nobody can be singled out.
"""

import json
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import Boolean, Date, Integer, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from tracker import Base, get_db, localize, require_key

BASE_DIR = Path(__file__).parent
DASHBOARD_FILE = BASE_DIR.parent / "dashboard" / "index.html"
MIN_GROUP_SIZE = 3

Lang = Literal["en", "sw"]

COUNTIES = [
    "Mombasa", "Kwale", "Kilifi", "Tana River", "Lamu", "Taita-Taveta", "Garissa", "Wajir",
    "Mandera", "Marsabit", "Isiolo", "Meru", "Tharaka-Nithi", "Embu", "Kitui", "Machakos",
    "Makueni", "Nyandarua", "Nyeri", "Kirinyaga", "Murang'a", "Kiambu", "Turkana", "West Pokot",
    "Samburu", "Trans-Nzoia", "Uasin Gishu", "Elgeyo-Marakwet", "Nandi", "Baringo", "Laikipia",
    "Nakuru", "Narok", "Kajiado", "Kericho", "Bomet", "Kakamega", "Vihiga", "Bungoma", "Busia",
    "Siaya", "Kisumu", "Homa Bay", "Migori", "Kisii", "Nyamira", "Nairobi",
]

# Short chart labels for each action plan (plan id -> {en, sw})
SUBTYPE_LABELS = {
    "plan_money_lost": {"en": "Money taken after fake bank call", "sw": "Pesa zimechukuliwa baada ya simu feki ya benki"},
    "plan_details_shared": {"en": "Details shared with fake bank agent", "sw": "Taarifa zimetolewa kwa wakala feki wa benki"},
    "plan_remote_access": {"en": "Remote access app installed", "sw": "Programu ya ufikiaji wa mbali imepakuliwa"},
    "plan_nothing_shared": {"en": "Fake bank call, nothing shared", "sw": "Simu feki ya benki, hakuna kilichotolewa"},
    "plan_safaricom": {"en": "M-PESA sent to scammer (Safaricom)", "sw": "M-PESA imetumwa kwa tapeli (Safaricom)"},
    "plan_mobile_money": {"en": "Other mobile money sent to scammer", "sw": "Pesa za simu (mtoa mwingine) zimetumwa kwa tapeli"},
    "plan_bank_transfer": {"en": "Bank transfer to scammer", "sw": "Uhamisho wa benki kwa tapeli"},
    "plan_other_payment": {"en": "Airtime, gift cards or crypto", "sw": "Muda wa maongezi, kadi za zawadi au sarafu za kidijitali"},
    "plan_whatsapp": {"en": "WhatsApp hijacked", "sw": "WhatsApp imedukuliwa"},
    "plan_social": {"en": "Social media hijacked", "sw": "Mitandao ya kijamii imedukuliwa"},
    "plan_email": {"en": "Email hijacked", "sw": "Barua pepe imedukuliwa"},
}
OTHER_LABEL = {"en": "Other (groups under {k})", "sw": "Nyingine (makundi chini ya {k})"}
NOT_STATED_LABEL = {"en": "Not stated", "sw": "Haikutajwa"}

# Which cases and plans exist (read from the triage data so there is one source of truth)
with open(BASE_DIR / "triage_data.json", encoding="utf-8") as _f:
    _TRIAGE = json.load(_f)
CASE_PLANS: Dict[str, set] = {
    case_id: {nid for nid, node in case["nodes"].items() if node["type"] == "plan"}
    for case_id, case in _TRIAGE["cases"].items()
}
CASE_TITLES = {case_id: case["title"] for case_id, case in _TRIAGE["cases"].items()}
_missing = {p for plans in CASE_PLANS.values() for p in plans} - set(SUBTYPE_LABELS)
if _missing:
    raise ValueError(f"community.py is missing chart labels for plans: {sorted(_missing)}")


class IncidentReport(Base):
    __tablename__ = "incident_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[str] = mapped_column(String(40))
    plan_id: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    county: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    week_start: Mapped[date] = mapped_column(Date, index=True)  # the Monday of the week, nothing finer
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)


def kenya_today() -> date:
    return (datetime.now(timezone.utc) + timedelta(hours=3)).date()


def monday_of(day: date) -> date:
    return day - timedelta(days=day.weekday())


class ReportCreate(BaseModel):
    case_id: str = Field(max_length=40)
    plan_id: Optional[str] = Field(None, max_length=60)
    county: Optional[str] = Field(None, max_length=30)


submit_router = APIRouter(prefix="/community", tags=["community"], dependencies=[Depends(require_key)])
public_router = APIRouter(prefix="/community", tags=["community"])
page_router = APIRouter(tags=["community"])


@submit_router.post("/reports")
def submit_report(body: ReportCreate, db: Session = Depends(get_db)) -> dict:
    """Add one anonymous report. Nothing that identifies the sender is stored."""
    if body.case_id not in CASE_PLANS:
        raise HTTPException(status_code=422, detail="Unknown case")
    if body.plan_id is not None and body.plan_id not in CASE_PLANS[body.case_id]:
        raise HTTPException(status_code=422, detail="Unknown plan for this case")
    if body.county is not None and body.county not in COUNTIES:
        raise HTTPException(status_code=422, detail="Unknown county")
    db.add(
        IncidentReport(
            case_id=body.case_id,
            plan_id=body.plan_id,
            county=body.county,
            week_start=monday_of(kenya_today()),
            is_demo=False,
        )
    )
    db.commit()
    return {"ok": True}


@public_router.get("/counties")
def list_counties() -> List[str]:
    return COUNTIES


def group(counter: Counter, labels: Dict[str, str], lang: str) -> List[dict]:
    """Turn counts into chart rows, hiding groups smaller than MIN_GROUP_SIZE.

    Hidden groups are merged into one 'Other' row, which is itself shown only
    if it is big enough. This stops anyone working out a small count by
    subtracting.
    """
    rows = [
        {"id": key, "label": labels.get(key, key), "count": count}
        for key, count in counter.items()
        if count >= MIN_GROUP_SIZE
    ]
    rows.sort(key=lambda row: (-row["count"], row["label"]))
    hidden = sum(count for count in counter.values() if count < MIN_GROUP_SIZE)
    if hidden >= MIN_GROUP_SIZE:
        rows.append({"id": "other", "label": OTHER_LABEL[lang].format(k=MIN_GROUP_SIZE), "count": hidden})
    return rows


@public_router.get("/stats")
def community_stats(
    days: int = Query(90, ge=7, le=365),
    data: Literal["real", "demo"] = Query("real", description="'demo' shows labelled synthetic data only"),
    lang: Lang = Query("en"),
    db: Session = Depends(get_db),
) -> dict:
    today = kenya_today()
    first_week = monday_of(today - timedelta(days=days))
    rows = db.scalars(
        select(IncidentReport).where(
            IncidentReport.week_start >= first_week,
            IncidentReport.is_demo.is_(data == "demo"),
        )
    ).all()

    type_labels = {cid: localize(title, lang) for cid, title in CASE_TITLES.items()}
    subtype_labels = {pid: labels[lang] for pid, labels in SUBTYPE_LABELS.items()}
    county_labels = {c: c for c in COUNTIES}
    county_labels["not_stated"] = NOT_STATED_LABEL[lang]

    by_type = group(Counter(r.case_id for r in rows), type_labels, lang)
    by_subtype = group(Counter(r.plan_id for r in rows if r.plan_id), subtype_labels, lang)
    by_county = group(Counter(r.county or "not_stated" for r in rows), county_labels, lang)

    week_counts = Counter(r.week_start for r in rows)
    by_week, week = [], first_week
    while week <= monday_of(today):
        count = week_counts.get(week, 0)
        by_week.append({"week_start": week.isoformat(), "count": count if count == 0 or count >= MIN_GROUP_SIZE else None})
        week += timedelta(days=7)

    shown_total = sum(row["count"] for row in by_type)
    return {
        "data": data,
        "days": days,
        "min_group_size": MIN_GROUP_SIZE,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_shown": shown_total if shown_total >= MIN_GROUP_SIZE else None,
        "by_type": by_type,
        "by_subtype": by_subtype,
        "by_county": by_county,
        "by_week": by_week,
    }


@page_router.get("/dashboard", include_in_schema=False)
def dashboard_page():
    if not DASHBOARD_FILE.exists():
        raise HTTPException(status_code=404, detail="dashboard/index.html is missing")
    return FileResponse(DASHBOARD_FILE, media_type="text/html")
