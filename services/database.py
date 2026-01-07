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
    Boolean,
)
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()

# =================================================
# Study Group Tickets Table
# =================================================

class Ticket(Base):
    __tablename__ = "tickets"

    id = Column(String, primary_key=True)
    group_name = Column(String, nullable=False)
    level = Column(String, nullable=False)
    member_count = Column(Integer, nullable=False)
    members = Column(Text, nullable=False)
    created_by = Column(String, nullable=False)

    status = Column(String, nullable=False)
    claimed_by = Column(String, nullable=True)
    cancelled_by = Column(String, nullable=True)
    cancelled_at = Column(DateTime, nullable=True)
    cancellation_reason = Column(Text, nullable=True)

    approval_message_id = Column(String, nullable=True)
    approved_members = Column(Text, nullable=True)
    transcript_message_id = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)


class TicketCounter(Base):
    __tablename__ = "ticket_counter"

    id = Column(Integer, primary_key=True)
    last_ticket_id = Column(Integer, default=0)


# =================================================
# Issue Tickets Table
# =================================================

class IssueTicket(Base):
    __tablename__ = "issue_tickets"

    id = Column(String, primary_key=True)  # ISS-001, ISS-002, etc.
    category = Column(String, nullable=False)
    priority = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    
    created_by = Column(String, nullable=False)
    anonymous = Column(Boolean, default=False)
    reported_user = Column(String, nullable=True)
    
    status = Column(String, nullable=False)  # OPEN, IN_PROGRESS, ESCALATED, RESOLVED, INVALID
    claimed_by = Column(String, nullable=True)
    escalated = Column(Boolean, default=False)
    escalated_by = Column(String, nullable=True)
    
    resolution = Column(Text, nullable=True)
    resolved_by = Column(String, nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    
    thread_id = Column(String, nullable=True)
    transcript_message_id = Column(String, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)


class IssueTicketCounter(Base):
    __tablename__ = "issue_ticket_counter"

    id = Column(Integer, primary_key=True)
    last_issue_id = Column(Integer, default=0)


# =================================================
# Database Connection
# =================================================

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    # LOCAL DEVELOPMENT: Use SQLite
    print("[Database] No DATABASE_URL found - using local SQLite")
    DATABASE_URL = "sqlite:///data/tickets.db"
    
elif DATABASE_URL.startswith("postgres://"):
    # PRODUCTION: Fix Railway's postgres:// to postgresql://
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    print("[Database] Using PostgreSQL (Railway)")

else:
    print(f"[Database] Using: {DATABASE_URL.split('@')[0]}@***")

# Create engine
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)


def init_db():
    """Initialize database tables and counters"""
    Base.metadata.create_all(engine)
    session = SessionLocal()
    try:
        # Study group ticket counter
        if not session.query(TicketCounter).first():
            session.add(TicketCounter(last_ticket_id=0))
            session.commit()
            print("[Database] Initialized ticket counter")
        
        # Issue ticket counter
        if not session.query(IssueTicketCounter).first():
            session.add(IssueTicketCounter(last_issue_id=0))
            session.commit()
            print("[Database] Initialized issue ticket counter")
    finally:
        session.close()


# =================================================
# Study Group Ticket Functions (existing)
# =================================================

def _ticket_to_dict(t: Ticket):
    """Convert Ticket model to dictionary"""
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
        "cancellation_reason": t.cancellation_reason,
        "approval_message_id": t.approval_message_id,
        "approved_members": json.loads(t.approved_members) if t.approved_members else [],
        "transcript_message_id": t.transcript_message_id,
    }


def get_ticket(ticket_id: str):
    """Get a single ticket by ID"""
    session = SessionLocal()
    try:
        t = session.query(Ticket).filter_by(id=ticket_id).first()
        return _ticket_to_dict(t) if t else None
    finally:
        session.close()


def save_ticket(ticket_id: str, data: dict):
    """Save or update a ticket"""
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
        t.cancellation_reason = data.get("cancellation_reason")
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
    """Get all tickets as a dictionary"""
    session = SessionLocal()
    try:
        tickets = session.query(Ticket).all()
        return {t.id: _ticket_to_dict(t) for t in tickets}
    finally:
        session.close()


def next_ticket_id() -> str:
    """Get next ticket ID and increment counter"""
    session = SessionLocal()
    try:
        counter = session.query(TicketCounter).first()
        counter.last_ticket_id += 1
        session.commit()
        return f"{counter.last_ticket_id:02d}"
    finally:
        session.close()


def export_tickets_json() -> str:
    """Export all tickets as JSON for audit purposes"""
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


# =================================================
# Issue Ticket Functions (NEW)
# =================================================

def _issue_ticket_to_dict(t: IssueTicket):
    """Convert IssueTicket model to dictionary"""
    return {
        "category": t.category,
        "priority": t.priority,
        "description": t.description,
        "created_by": t.created_by,
        "anonymous": t.anonymous,
        "reported_user": t.reported_user,
        "status": t.status,
        "claimed_by": t.claimed_by,
        "escalated": t.escalated,
        "escalated_by": t.escalated_by,
        "resolution": t.resolution,
        "resolved_by": t.resolved_by,
        "resolved_at": t.resolved_at.isoformat() if t.resolved_at else None,
        "thread_id": t.thread_id,
        "transcript_message_id": t.transcript_message_id,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


def get_issue_ticket(ticket_id: str):
    """Get a single issue ticket by ID"""
    session = SessionLocal()
    try:
        t = session.query(IssueTicket).filter_by(id=ticket_id).first()
        return _issue_ticket_to_dict(t) if t else None
    finally:
        session.close()


def save_issue_ticket(ticket_id: str, data: dict):
    """Save or update an issue ticket"""
    session = SessionLocal()
    try:
        t = session.query(IssueTicket).filter_by(id=ticket_id).first()
        if not t:
            t = IssueTicket(id=ticket_id)
            session.add(t)

        t.category = data["category"]
        t.priority = data["priority"]
        t.description = data["description"]
        t.created_by = str(data["created_by"])
        t.anonymous = data.get("anonymous", False)
        t.reported_user = str(data["reported_user"]) if data.get("reported_user") else None
        t.status = data["status"]
        t.claimed_by = str(data["claimed_by"]) if data.get("claimed_by") else None
        t.escalated = data.get("escalated", False)
        t.escalated_by = str(data["escalated_by"]) if data.get("escalated_by") else None
        t.resolution = data.get("resolution")
        t.resolved_by = str(data["resolved_by"]) if data.get("resolved_by") else None
        t.resolved_at = (
            datetime.fromisoformat(data["resolved_at"])
            if data.get("resolved_at")
            else None
        )
        t.thread_id = str(data["thread_id"]) if data.get("thread_id") else None
        t.transcript_message_id = (
            str(data["transcript_message_id"]) if data.get("transcript_message_id") else None
        )

        session.commit()
    finally:
        session.close()


def get_all_issue_tickets():
    """Get all issue tickets as a dictionary"""
    session = SessionLocal()
    try:
        tickets = session.query(IssueTicket).all()
        return {t.id: _issue_ticket_to_dict(t) for t in tickets}
    finally:
        session.close()


def next_issue_ticket_id() -> str:
    """Get next issue ticket ID and increment counter"""
    session = SessionLocal()
    try:
        counter = session.query(IssueTicketCounter).first()
        counter.last_issue_id += 1
        session.commit()
        return f"ISS-{counter.last_issue_id:03d}"
    finally:
        session.close()


def export_issue_tickets_json() -> str:
    """Export all issue tickets as JSON for audit purposes"""
    session = SessionLocal()
    try:
        counter = session.query(IssueTicketCounter).first()
        tickets = get_all_issue_tickets()
        data = {
            "last_issue_id": counter.last_issue_id if counter else 0,
            "issue_tickets": tickets,
        }
        return json.dumps(data, indent=2)
    finally:
        session.close()


def get_issue_tickets_by_status(status: str):
    """Get all issue tickets with a specific status"""
    session = SessionLocal()
    try:
        tickets = session.query(IssueTicket).filter_by(status=status).all()
        return {t.id: _issue_ticket_to_dict(t) for t in tickets}
    finally:
        session.close()


def get_issue_tickets_by_user(user_id: int):
    """Get all issue tickets created by a specific user"""
    session = SessionLocal()
    try:
        tickets = session.query(IssueTicket).filter_by(created_by=str(user_id)).all()
        return {t.id: _issue_ticket_to_dict(t) for t in tickets}
    finally:
        session.close()