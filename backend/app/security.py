import base64
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from cryptography.fernet import Fernet
from fastapi import Cookie, Depends, HTTPException, status
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .database import get_db
from .models import AclEntry, GroupMember, User, Visibility


password_hash = PasswordHash.recommended()
settings = get_settings()


def _fernet() -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.secret_key.encode()).digest())
    return Fernet(key)


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt_secret(value: str) -> str:
    return _fernet().decrypt(value.encode()).decode()


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return password_hash.verify(password, hashed)


def create_opaque_token(prefix: str) -> str:
    return f"{prefix}_{secrets.token_urlsafe(32)}"


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session_token(user: User) -> str:
    expires = datetime.now(timezone.utc) + timedelta(minutes=settings.session_ttl_minutes)
    return jwt.encode(
        {"sub": user.id, "exp": expires, "root": user.is_root},
        settings.secret_key,
        algorithm="HS256",
    )


def resolve_session_user(af_session: str | None, db: Session) -> User:
    """Resolve a session cookie using a caller-owned, short-lived DB session."""
    if not af_session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        payload = jwt.decode(af_session, settings.secret_key, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session"
        ) from exc
    user = db.scalar(select(User).where(User.id == payload["sub"], User.is_active.is_(True)))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User unavailable")
    return user


def current_user(
    af_session: str | None = Cookie(default=None), db: Session = Depends(get_db)
) -> User:
    return resolve_session_user(af_session, db)


def has_permission(
    db: Session,
    user: User,
    resource_type: str,
    resource_id: str,
    owner_id: str,
    visibility: Visibility,
    permission: str,
) -> bool:
    if user.is_root or user.id == owner_id:
        return True
    if visibility == Visibility.public and permission in {"view", "run"}:
        return True
    group_ids = list(db.scalars(select(GroupMember.group_id).where(GroupMember.user_id == user.id)))
    entries = list(
        db.scalars(
            select(AclEntry).where(
                AclEntry.resource_type == resource_type,
                AclEntry.resource_id == resource_id,
            )
        )
    )
    implied = {
        "owner": {"view", "run", "edit", "manage"},
        "manage": {"view", "run", "edit", "manage"},
        "edit": {"view", "run", "edit"},
        "run": {"view", "run"},
        "view": {"view"},
    }
    for entry in entries:
        subject_matches = (entry.subject_type == "user" and entry.subject_id == user.id) or (
            entry.subject_type == "group" and entry.subject_id in group_ids
        )
        if subject_matches and any(
            permission in implied.get(grant, {grant}) for grant in entry.permissions
        ):
            return True
    return False
