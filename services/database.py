import os
import json
from datetime import datetime

from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Text,
    DateTime,
)
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()

class Ticket(Base):
    __tablename__ = "tickets"

    id = Column(String, primary_key=True)  # "01", "02", ...
    group_name = Column(String, nullable=False)
    level = Column(String, nullable=False)
    member_count = Column(Integer, nullable=False)
    members = Column(Text, nullable=False)  # JSON list of user IDs
    created_by = Column(String, nullable=False)

    status = Column(String, nullable=False)  # OPEN / CLAIMED / APPROVED / CANCELLED
    claimed_by = Column(String, nullable=True)
    cancelled_by = Column(String, nullable=True)
    cancelled_at = Column(DateTime, nullable=True)

    approval_message_id = Column(String, nullable=True)
    approved_members = Column(Text, nullable=True)  # JSON list
    transcript_message_id = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)


class TicketCounter(Base):
    __tablename__ = "ticket_counter"

    id = Column(Integer, primary_key=True)
    last_ticket_id = Column(Integer, default=0)


DATABASE_URL = os.getenv("DATABASE_URL")

# Railway Postgres usually exposes DATABASE_URL directly in correct format.[web:13]
# Fallback to a local SQLite file so you can test locally without Postgres.[web:11]
if not DATABASE_URL:
    DATABASE_URL = "sqlite:///data/tickets.db"

# Some providers still give "postgres://", normalize to "postgresql://".[web:10]
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)


def init_db():
    Base.metadata.create_all(engine)
    session = SessionLocal()
    try:
        if not session.query(TicketCounter).first():
            session.add(TicketCounter(last_ticket_id=0))
            session.commit()
    finally:
        session.close()


def _ticket_to_dict(t: Ticket):
    return {
        "group_name": t.group_name,
        "level": t.level,
        "member_count": t.member_count,
        "members": json.loads(t.members),
        "created_by": t.created_by,
        "status": t.status,
        "claimed_by": t.claimed_by,
        "cancelled_by": t.cancelled_by,
        "cancelled_at": t.cancelled_at.isoformat() if t.cancelled_at else None,
        "approval_message_id": t.approval_message_id,
        "approved_members": json.loads(t.approved_members) if t.approved_members else [],
        "transcript_message_id": t.transcript_message_id,
    }


def get_ticket(ticket_id: str):
    session = SessionLocal()
    try:
        t = session.query(Ticket).filter_by(id=ticket_id).first()
        return _ticket_to_dict(t) if t else None
    finally:
        session.close()


def save_ticket(ticket_id: str, data: dict):
    session = SessionLocal()
    try:
        t = session.query(Ticket).filter_by(id=ticket_id).first()
        if not t:
            t = Ticket(id=ticket_id, created_by=str(data["created_by"]))
            session.add(t)

        t.group_name = data["group_name"]
        t.level = data["level"]
        t.member_count = data["member_count"]
        t.members = json.dumps(data["members"])
        t.status = data["status"]
        t.claimed_by = str(data["claimed_by"]) if data.get("claimed_by") else None
        t.cancelled_by = str(data["cancelled_by"]) if data.get("cancelled_by") else None
        t.cancelled_at = (
            datetime.fromisoformat(data["cancelled_at"])
            if data.get("cancelled_at")
            else None
        )
        t.approval_message_id = (
            str(data["approval_message_id"]) if data.get("approval_message_id") else None
        )
        t.approved_members = json.dumps(data.get("approved_members", []))
        t.transcript_message_id = (
            str(data["transcript_message_id"]) if data.get("transcript_message_id") else None
        )

        session.commit()
    finally:
        session.close()


def get_all_tickets():
    session = SessionLocal()
    try:
        tickets = session.query(Ticket).all()
        return {t.id: _ticket_to_dict(t) for t in tickets}
    finally:
        session.close()


def next_ticket_id() -> str:
    session = SessionLocal()
    try:
        counter = session.query(TicketCounter).first()
        counter.last_ticket_id += 1
        session.commit()
        return f"{counter.last_ticket_id:02d}"
    finally:
        session.close()


def export_tickets_json() -> str:
    session = SessionLocal()
    try:
        counter = session.query(TicketCounter).first()
        tickets = get_all_tickets()
        data = {
            "last_ticket_id": counter.last_ticket_id if counter else 0,
            "tickets": tickets,
        }
        return json.dumps(data, indent=2)
    finally:
        session.close()