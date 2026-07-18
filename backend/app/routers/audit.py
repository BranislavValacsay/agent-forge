from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AuditEvent, User
from ..schemas import AuditEventCreate, AuditEventOut
from ..security import current_user


router = APIRouter(prefix="/audit-events", tags=["audit"])


@router.post("", response_model=AuditEventOut, status_code=201)
def create_event(payload: AuditEventCreate, db: Session = Depends(get_db), user: User = Depends(current_user)) -> AuditEvent:
    event = AuditEvent(**payload.model_dump(), user_id=user.id)
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


@router.get("", response_model=list[AuditEventOut])
def list_events(db: Session = Depends(get_db), user: User = Depends(current_user)) -> list[AuditEvent]:
    query = select(AuditEvent).where(AuditEvent.user_id == user.id).order_by(AuditEvent.created_at.desc()).limit(200)
    return list(db.scalars(query))
