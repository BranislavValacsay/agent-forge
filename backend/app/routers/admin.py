from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Group, GroupMember, User
from ..schemas import GroupCreate, GroupOut, UserAdminOut
from ..security import current_user


router = APIRouter(tags=["administration"])


@router.get("/users", response_model=list[UserAdminOut])
def list_users(db: Session = Depends(get_db), user: User = Depends(current_user)) -> list[User]:
    if not user.is_root:
        raise HTTPException(status_code=403, detail="Root access required")
    return list(db.scalars(select(User).order_by(User.created_at)))


@router.get("/groups", response_model=list[GroupOut])
def list_groups(db: Session = Depends(get_db), user: User = Depends(current_user)) -> list[Group]:
    return list(db.scalars(select(Group).order_by(Group.name)))


@router.post("/groups", response_model=GroupOut, status_code=201)
def create_group(payload: GroupCreate, db: Session = Depends(get_db), user: User = Depends(current_user)) -> Group:
    group = Group(**payload.model_dump(), manager_id=user.id)
    db.add(group)
    db.flush()
    db.add(GroupMember(group_id=group.id, user_id=user.id))
    db.commit()
    db.refresh(group)
    return group
