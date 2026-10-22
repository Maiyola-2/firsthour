"""FirstHour case tracker (Phase 5, feature 2).

Lets a victim save "I reported this to my bank / provider / police" with a
reference number and a follow-up date. The bot reminds them, and if nobody
replied it shows where to escalate.

Privacy: only these things are stored per follow-up: Telegram chat id,
case type, institution, an optional reference number, dates, status and
language. No names, amounts, phone numbers or message text. A user can erase
everything with DELETE /tracker/chats/{chat_id} (the bot's /deletemydata).

Database: SQLite by default (a file named firsthour.db, no setup needed).
To use MySQL instead, put this in backend/.env:
    DATABASE_URL=mysql+pymysql://user:password@localhost:3306/firsthour
"""

import hmac
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, List, Literal, Optional

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, create_engine, delete, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

load_dotenv()

BASE_DIR = Path(__file__).parent
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{(BASE_DIR / 'firsthour.db').as_posix()}")
ESCALATION_FILE = BASE_DIR / "escalation.json"

Lang = Literal["en", "sw"]
Institution = Literal["bank", "mobile_money", "telecom", "police", "other"]
INSTITUTIONS = ("bank", "mobile_money", "telecom", "police", "other")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class FollowUp(Base):
    __tablename__ = "follow_ups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    case_id: Mapped[str] = mapped_column(String(40))
    plan_id: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    institution: Mapped[str] = mapped_column(String(20))
    reference: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    lang: Mapped[str] = mapped_column(String(2), default="en")
    status: Mapped[str] = mapped_column(String(12), default="waiting")  # waiting | resolved
    reminded: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    follow_up_at: Mapped[datetime] = mapped_column(DateTime)


def init_db() -> None:
    Base.metadata.create_all(engine)


def utcnow() -> datetime:
    """Naive UTC time (what we store in the database)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def get_db():
    with SessionLocal() as session:
        yield session


def require_key(x_api_key: Optional[str] = Header(None)) -> None:
    """If FIRSTHOUR_API_KEY is set, every tracker call must send it."""
    expected = os.getenv("FIRSTHOUR_API_KEY", "")
    if expected and not hmac.compare_digest(x_api_key or "", expected):
        raise HTTPException(status_code=401, detail="Invalid API key")


def localize(value: Any, lang: str) -> Any:
    if isinstance(value, dict):
        if set(value.keys()) == {"en", "sw"}:
            return value[lang]
        return {k: localize(v, lang) for k, v in value.items()}
    if isinstance(value, list):
        return [localize(item, lang) for item in value]
    return value


with open(ESCALATION_FILE, encoding="utf-8") as _f:
    ESCALATION = json.load(_f)
for _code in INSTITUTIONS:
    if _code not in ESCALATION:
        raise ValueError(f"escalation.json is missing '{_code}'")


def as_dict(row: FollowUp) -> dict:
    return {
        "id": row.id,
        "chat_id": row.chat_id,
        "case_id": row.case_id,
        "plan_id": row.plan_id,
        "institution": row.institution,
        "reference": row.reference,
        "lang": row.lang,
        "status": row.status,
        "reminded": row.reminded,
        "created_at": row.created_at.isoformat(),
        "follow_up_at": row.follow_up_at.isoformat(),
    }


class FollowUpCreate(BaseModel):
    chat_id: int
    case_id: str = Field(max_length=40)
    plan_id: Optional[str] = Field(None, max_length=60)
    institution: Institution
    reference: Optional[str] = Field(None, max_length=60)
    days: int = Field(7, ge=1, le=60)
    lang: Lang = "en"


class ChatBody(BaseModel):
    chat_id: int


class SnoozeBody(BaseModel):
    chat_id: int
    days: int = Field(3, ge=1, le=60)


router = APIRouter(prefix="/tracker", tags=["tracker"], dependencies=[Depends(require_key)])


def get_owned(db: Session, follow_up_id: int, chat_id: int) -> FollowUp:
    row = db.get(FollowUp, follow_up_id)
    if row is None or row.chat_id != chat_id:
        raise HTTPException(status_code=404, detail="Follow-up not found")
    return row


@router.post("/follow-ups")
def create_follow_up(body: FollowUpCreate, db: Session = Depends(get_db)) -> dict:
    now = utcnow()
    row = FollowUp(
        chat_id=body.chat_id,
        case_id=body.case_id,
        plan_id=body.plan_id,
        institution=body.institution,
        reference=(body.reference or "").strip() or None,
        lang=body.lang,
        status="waiting",
        reminded=False,
        created_at=now,
        follow_up_at=now + timedelta(days=body.days),
    )
    db.add(row)
    db.commit()
    return as_dict(row)


@router.get("/follow-ups")
def list_follow_ups(chat_id: int = Query(...), db: Session = Depends(get_db)) -> List[dict]:
    rows = db.scalars(
        select(FollowUp).where(FollowUp.chat_id == chat_id).order_by(FollowUp.created_at.desc()).limit(20)
    ).all()
    return [as_dict(r) for r in rows]


@router.get("/follow-ups/{follow_up_id}")
def get_follow_up(follow_up_id: int, chat_id: int = Query(...), db: Session = Depends(get_db)) -> dict:
    return as_dict(get_owned(db, follow_up_id, chat_id))


@router.get("/due")
def due_follow_ups(db: Session = Depends(get_db)) -> List[dict]:
    """Follow-ups whose date has passed and that were not reminded yet (used by the bot)."""
    rows = db.scalars(
        select(FollowUp)
        .where(FollowUp.status == "waiting", FollowUp.reminded.is_(False), FollowUp.follow_up_at <= utcnow())
        .order_by(FollowUp.follow_up_at)
        .limit(100)
    ).all()
    return [as_dict(r) for r in rows]


@router.post("/follow-ups/{follow_up_id}/reminded")
def mark_reminded(follow_up_id: int, db: Session = Depends(get_db)) -> dict:
    row = db.get(FollowUp, follow_up_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Follow-up not found")
    row.reminded = True
    db.commit()
    return as_dict(row)


@router.post("/follow-ups/{follow_up_id}/resolve")
def resolve_follow_up(follow_up_id: int, body: ChatBody, db: Session = Depends(get_db)) -> dict:
    row = get_owned(db, follow_up_id, body.chat_id)
    row.status = "resolved"
    db.commit()
    return as_dict(row)


@router.post("/follow-ups/{follow_up_id}/snooze")
def snooze_follow_up(follow_up_id: int, body: SnoozeBody, db: Session = Depends(get_db)) -> dict:
    row = get_owned(db, follow_up_id, body.chat_id)
    row.status = "waiting"
    row.reminded = False
    row.follow_up_at = utcnow() + timedelta(days=body.days)
    db.commit()
    return as_dict(row)


@router.delete("/chats/{chat_id}")
def delete_chat_data(chat_id: int, db: Session = Depends(get_db)) -> dict:
    """Erase everything stored for this chat."""
    result = db.execute(delete(FollowUp).where(FollowUp.chat_id == chat_id))
    db.commit()
    return {"deleted": result.rowcount}


@router.get("/escalation/{institution}")
def get_escalation(institution: Institution, lang: Lang = Query("en")) -> dict:
    """Where to go next if this institution does not reply."""
    entry = ESCALATION[institution]
    return {"institution": institution, **localize({k: v for k, v in entry.items()}, lang)}
