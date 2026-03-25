from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from auth.security import create_access_token, decode_access_token, hash_password, verify_password
from db.config import get_session
from db.models import User

router = APIRouter(prefix="/api/auth", tags=["auth"])
bearer_scheme = HTTPBearer()

LOCKOUT_ATTEMPTS = 5
LOCKOUT_MINUTES = 30


# ---------- request / response schemas ----------

class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class UserProfile(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    tenant_id: str
    tenant_name: str

    class Config:
        from_attributes = True


class LoginResponse(BaseModel):
    token: str
    user: UserProfile


# ---------- helpers ----------

async def _get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_session),
) -> User:
    payload = decode_access_token(creds.credentials)
    user_id: str | None = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    stmt = select(User).options(joinedload(User.tenant)).where(User.id == user_id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    return user


def _user_profile(user: User) -> UserProfile:
    return UserProfile(
        id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        tenant_id=str(user.tenant_id),
        tenant_name=user.tenant.name,
    )


# ---------- endpoints ----------

@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, session: AsyncSession = Depends(get_session)):
    stmt = select(User).options(joinedload(User.tenant)).where(User.email == body.email)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    # Check lockout
    now = datetime.now(timezone.utc)
    if user.locked_until and user.locked_until > now:
        minutes_left = int((user.locked_until - now).total_seconds() // 60) + 1
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Account locked. Try again in {minutes_left} minute(s).",
        )

    # Verify password
    if not verify_password(body.password, user.password_hash):
        user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
        if user.failed_login_attempts >= LOCKOUT_ATTEMPTS:
            user.locked_until = now + timedelta(minutes=LOCKOUT_MINUTES)
        await session.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    # Successful login — reset lockout counters, update last_login
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login = now
    await session.commit()

    token = create_access_token(str(user.id))
    return LoginResponse(token=token, user=_user_profile(user))


@router.get("/me", response_model=UserProfile)
async def me(user: User = Depends(_get_current_user)):
    return _user_profile(user)


@router.post("/change-password")
async def change_password(
    body: ChangePasswordRequest,
    user: User = Depends(_get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")

    user.password_hash = hash_password(body.new_password)
    await session.commit()
    return {"message": "Password updated successfully"}
