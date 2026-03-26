from __future__ import annotations

import secrets
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from audit.service import log_action
from auth.routes import _get_current_user
from auth.security import hash_password
from db.config import get_session
from db.models import Tenant, User

router = APIRouter(prefix="/api/admin", tags=["admin"])

ALLOWED_USER_ROLES = {"client_superadmin", "program_manager", "consultant", "client_viewer"}


# ---------- helpers ----------

def _require_super_admin(user: User) -> None:
    if user.role != "super_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Super admin access required")


def _req_meta(request: Request) -> tuple[str | None, str | None]:
    ip = request.headers.get("x-forwarded-for", request.client.host if request.client else None)
    ua = request.headers.get("user-agent")
    return ip, ua


def _tenant_dict(t: Tenant) -> dict:
    return {
        "name": t.name, "slug": t.slug, "tier": t.tier, "region": t.region,
        "status": t.status, "contract_start": str(t.contract_start) if t.contract_start else None,
        "contract_end": str(t.contract_end) if t.contract_end else None,
        "arr": str(t.arr) if t.arr is not None else None,
    }


def _user_dict(u: User) -> dict:
    return {"email": u.email, "full_name": u.full_name, "role": u.role, "is_active": u.is_active}


# ---------- schemas ----------

class TenantCreate(BaseModel):
    name: str
    slug: str
    tier: str = "bronze"
    region: str = "AMER"
    contract_start: date | None = None
    contract_end: date | None = None
    arr: Decimal | None = None


class TenantUpdate(BaseModel):
    name: str | None = None
    slug: str | None = None
    tier: str | None = None
    region: str | None = None
    contract_start: date | None = None
    contract_end: date | None = None
    arr: Decimal | None = None


class TenantOut(BaseModel):
    id: str
    name: str
    slug: str
    tier: str
    region: str
    status: str
    contract_start: date | None
    contract_end: date | None
    arr: Decimal | None
    user_count: int = 0
    deleted_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TenantDetail(TenantOut):
    users: list[UserOut] = []


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str
    role: str
    password: str


class UserUpdate(BaseModel):
    full_name: str | None = None
    role: str | None = None
    is_active: bool | None = None


class UserOut(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    is_active: bool
    last_login: datetime | None
    created_at: datetime

    class Config:
        from_attributes = True


class PaginatedTenants(BaseModel):
    items: list[TenantOut]
    total: int
    page: int
    per_page: int
    pages: int


class PasswordResetResult(BaseModel):
    temporary_password: str
    message: str


class DashboardOut(BaseModel):
    total_tenants: int
    active_tenants: int
    paused_tenants: int
    total_users: int
    total_arr: Decimal
    expiring_soon: int


# ---------- dashboard ----------

@router.get("/dashboard", response_model=DashboardOut)
async def admin_dashboard(
    user: User = Depends(_get_current_user),
    session: AsyncSession = Depends(get_session),
):
    _require_super_admin(user)

    now = datetime.now(timezone.utc).date()
    soon = now + timedelta(days=30)

    # Non-deleted tenants
    non_deleted = select(Tenant).where(Tenant.status != "deleted")
    total_tenants = (await session.execute(
        select(func.count()).select_from(non_deleted.subquery())
    )).scalar_one()

    active_tenants = (await session.execute(
        select(func.count()).where(Tenant.status == "active")
    )).scalar_one()

    paused_tenants = (await session.execute(
        select(func.count()).where(Tenant.status == "paused")
    )).scalar_one()

    total_users = (await session.execute(
        select(func.count()).where(User.is_active == True)
    )).scalar_one()

    arr_result = (await session.execute(
        select(func.coalesce(func.sum(Tenant.arr), 0)).where(Tenant.status == "active")
    )).scalar_one()
    total_arr = Decimal(str(arr_result))

    expiring_soon = (await session.execute(
        select(func.count()).where(
            Tenant.status == "active",
            Tenant.contract_end != None,
            Tenant.contract_end >= now,
            Tenant.contract_end <= soon,
        )
    )).scalar_one()

    return DashboardOut(
        total_tenants=total_tenants,
        active_tenants=active_tenants,
        paused_tenants=paused_tenants,
        total_users=total_users,
        total_arr=total_arr,
        expiring_soon=expiring_soon,
    )


# ---------- tenant endpoints ----------

@router.get("/tenants", response_model=PaginatedTenants)
async def list_tenants(
    status_filter: str | None = None,
    tier: str | None = None,
    region: str | None = None,
    search: str | None = None,
    page: int = 1,
    per_page: int = 50,
    user: User = Depends(_get_current_user),
    session: AsyncSession = Depends(get_session),
):
    _require_super_admin(user)

    stmt = select(Tenant)
    if status_filter:
        stmt = stmt.where(Tenant.status == status_filter)
    if tier:
        stmt = stmt.where(Tenant.tier == tier)
    if region:
        stmt = stmt.where(Tenant.region == region)
    if search:
        stmt = stmt.where(Tenant.name.ilike(f"%{search}%"))

    count_result = await session.execute(select(func.count()).select_from(stmt.subquery()))
    total = count_result.scalar_one()

    stmt = stmt.order_by(Tenant.name).offset((page - 1) * per_page).limit(per_page)
    result = await session.execute(stmt)
    tenants = result.scalars().all()

    # Get user counts
    user_counts_stmt = (
        select(User.tenant_id, func.count().label("cnt"))
        .group_by(User.tenant_id)
    )
    uc_result = await session.execute(user_counts_stmt)
    user_counts = {row.tenant_id: row.cnt for row in uc_result}

    items = []
    for t in tenants:
        items.append(TenantOut(
            id=str(t.id), name=t.name, slug=t.slug, tier=t.tier,
            region=t.region, status=t.status,
            contract_start=t.contract_start, contract_end=t.contract_end,
            arr=t.arr, user_count=user_counts.get(t.id, 0),
            deleted_at=t.deleted_at, created_at=t.created_at, updated_at=t.updated_at,
        ))

    return PaginatedTenants(
        items=items, total=total, page=page, per_page=per_page,
        pages=(total + per_page - 1) // per_page if total > 0 else 0,
    )


@router.get("/tenants/{tenant_id}", response_model=TenantDetail)
async def get_tenant(
    tenant_id: str,
    user: User = Depends(_get_current_user),
    session: AsyncSession = Depends(get_session),
):
    _require_super_admin(user)

    stmt = select(Tenant).options(joinedload(Tenant.users)).where(Tenant.id == tenant_id)
    result = await session.execute(stmt)
    tenant = result.unique().scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    return TenantDetail(
        id=str(tenant.id), name=tenant.name, slug=tenant.slug, tier=tenant.tier,
        region=tenant.region, status=tenant.status,
        contract_start=tenant.contract_start, contract_end=tenant.contract_end,
        arr=tenant.arr, user_count=len(tenant.users),
        deleted_at=tenant.deleted_at, created_at=tenant.created_at, updated_at=tenant.updated_at,
        users=[UserOut(
            id=str(u.id), email=u.email, full_name=u.full_name, role=u.role,
            is_active=u.is_active, last_login=u.last_login, created_at=u.created_at,
        ) for u in tenant.users],
    )


@router.post("/tenants", response_model=TenantOut, status_code=201)
async def create_tenant(
    body: TenantCreate,
    request: Request,
    user: User = Depends(_get_current_user),
    session: AsyncSession = Depends(get_session),
):
    _require_super_admin(user)
    ip, ua = _req_meta(request)

    tenant = Tenant(
        name=body.name, slug=body.slug, tier=body.tier, region=body.region,
        status="active", contract_start=body.contract_start,
        contract_end=body.contract_end, arr=body.arr,
    )
    session.add(tenant)
    await session.flush()

    await log_action(
        session, tenant_id=tenant.id, user_id=user.id,
        action="tenant.created", entity_type="tenant", entity_id=str(tenant.id),
        new_value=_tenant_dict(tenant), ip_address=ip, user_agent=ua,
    )

    return TenantOut(
        id=str(tenant.id), name=tenant.name, slug=tenant.slug, tier=tenant.tier,
        region=tenant.region, status=tenant.status,
        contract_start=tenant.contract_start, contract_end=tenant.contract_end,
        arr=tenant.arr, user_count=0,
        deleted_at=tenant.deleted_at, created_at=tenant.created_at, updated_at=tenant.updated_at,
    )


@router.put("/tenants/{tenant_id}", response_model=TenantOut)
async def update_tenant(
    tenant_id: str,
    body: TenantUpdate,
    request: Request,
    user: User = Depends(_get_current_user),
    session: AsyncSession = Depends(get_session),
):
    _require_super_admin(user)
    ip, ua = _req_meta(request)

    stmt = select(Tenant).where(Tenant.id == tenant_id)
    result = await session.execute(stmt)
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    old = _tenant_dict(tenant)
    updates = body.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(tenant, field, value)
    await session.flush()

    await log_action(
        session, tenant_id=tenant.id, user_id=user.id,
        action="tenant.updated", entity_type="tenant", entity_id=str(tenant.id),
        old_value=old, new_value=_tenant_dict(tenant), ip_address=ip, user_agent=ua,
    )

    uc = await session.execute(select(func.count()).where(User.tenant_id == tenant.id))

    return TenantOut(
        id=str(tenant.id), name=tenant.name, slug=tenant.slug, tier=tenant.tier,
        region=tenant.region, status=tenant.status,
        contract_start=tenant.contract_start, contract_end=tenant.contract_end,
        arr=tenant.arr, user_count=uc.scalar_one(),
        deleted_at=tenant.deleted_at, created_at=tenant.created_at, updated_at=tenant.updated_at,
    )


async def _set_tenant_status(
    tenant_id: str, new_status: str, action: str,
    request: Request, user: User, session: AsyncSession,
) -> dict:
    _require_super_admin(user)
    ip, ua = _req_meta(request)

    stmt = select(Tenant).where(Tenant.id == tenant_id)
    result = await session.execute(stmt)
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    old_status = tenant.status
    tenant.status = new_status
    if new_status == "deleted":
        tenant.deleted_at = datetime.now(timezone.utc)
    elif new_status == "active" and tenant.deleted_at:
        tenant.deleted_at = None
    await session.flush()

    await log_action(
        session, tenant_id=tenant.id, user_id=user.id,
        action=action, entity_type="tenant", entity_id=str(tenant.id),
        old_value={"status": old_status}, new_value={"status": new_status},
        ip_address=ip, user_agent=ua,
    )

    return {"message": f"Tenant {new_status}", "tenant_id": str(tenant.id)}


@router.post("/tenants/{tenant_id}/pause")
async def pause_tenant(
    tenant_id: str, request: Request,
    user: User = Depends(_get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return await _set_tenant_status(tenant_id, "paused", "tenant.paused", request, user, session)


@router.post("/tenants/{tenant_id}/resume")
async def resume_tenant(
    tenant_id: str, request: Request,
    user: User = Depends(_get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return await _set_tenant_status(tenant_id, "active", "tenant.resumed", request, user, session)


@router.post("/tenants/{tenant_id}/delete")
async def soft_delete_tenant(
    tenant_id: str, request: Request,
    user: User = Depends(_get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return await _set_tenant_status(tenant_id, "deleted", "tenant.deleted", request, user, session)


# ---------- user endpoints ----------

@router.get("/tenants/{tenant_id}/users", response_model=list[UserOut])
async def list_tenant_users(
    tenant_id: str,
    user: User = Depends(_get_current_user),
    session: AsyncSession = Depends(get_session),
):
    _require_super_admin(user)

    # Verify tenant exists
    t = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
    if not t.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Tenant not found")

    result = await session.execute(
        select(User).where(User.tenant_id == tenant_id).order_by(User.full_name)
    )
    users = result.scalars().all()
    return [
        UserOut(
            id=str(u.id), email=u.email, full_name=u.full_name, role=u.role,
            is_active=u.is_active, last_login=u.last_login, created_at=u.created_at,
        ) for u in users
    ]


@router.post("/tenants/{tenant_id}/users", response_model=UserOut, status_code=201)
async def create_user(
    tenant_id: str,
    body: UserCreate,
    request: Request,
    user: User = Depends(_get_current_user),
    session: AsyncSession = Depends(get_session),
):
    _require_super_admin(user)
    ip, ua = _req_meta(request)

    if body.role not in ALLOWED_USER_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"Role must be one of: {', '.join(sorted(ALLOWED_USER_ROLES))}",
        )

    # Verify tenant exists and is not deleted
    t_result = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = t_result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    if tenant.status == "deleted":
        raise HTTPException(status_code=400, detail="Cannot add users to a deleted tenant")

    # Check email uniqueness
    existing = await session.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already in use")

    new_user = User(
        tenant_id=tenant.id, email=body.email, full_name=body.full_name,
        role=body.role, password_hash=hash_password(body.password),
    )
    session.add(new_user)
    await session.flush()

    await log_action(
        session, tenant_id=tenant.id, user_id=user.id,
        action="user.created", entity_type="user", entity_id=str(new_user.id),
        new_value={"email": body.email, "full_name": body.full_name, "role": body.role},
        ip_address=ip, user_agent=ua,
    )

    return UserOut(
        id=str(new_user.id), email=new_user.email, full_name=new_user.full_name,
        role=new_user.role, is_active=new_user.is_active,
        last_login=new_user.last_login, created_at=new_user.created_at,
    )


@router.put("/users/{user_id}", response_model=UserOut)
async def update_user(
    user_id: str,
    body: UserUpdate,
    request: Request,
    user: User = Depends(_get_current_user),
    session: AsyncSession = Depends(get_session),
):
    _require_super_admin(user)
    ip, ua = _req_meta(request)

    result = await session.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    old = _user_dict(target)
    updates = body.model_dump(exclude_unset=True)

    if "role" in updates and updates["role"] not in ALLOWED_USER_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"Role must be one of: {', '.join(sorted(ALLOWED_USER_ROLES))}",
        )

    for field, value in updates.items():
        setattr(target, field, value)
    await session.flush()

    await log_action(
        session, tenant_id=target.tenant_id, user_id=user.id,
        action="user.updated", entity_type="user", entity_id=str(target.id),
        old_value=old, new_value=_user_dict(target), ip_address=ip, user_agent=ua,
    )

    return UserOut(
        id=str(target.id), email=target.email, full_name=target.full_name,
        role=target.role, is_active=target.is_active,
        last_login=target.last_login, created_at=target.created_at,
    )


@router.post("/users/{user_id}/deactivate")
async def deactivate_user(
    user_id: str,
    request: Request,
    user: User = Depends(_get_current_user),
    session: AsyncSession = Depends(get_session),
):
    _require_super_admin(user)
    ip, ua = _req_meta(request)

    result = await session.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    target.is_active = False
    await session.flush()

    await log_action(
        session, tenant_id=target.tenant_id, user_id=user.id,
        action="user.deactivated", entity_type="user", entity_id=str(target.id),
        new_value={"email": target.email, "is_active": False},
        ip_address=ip, user_agent=ua,
    )

    return {"message": "User deactivated", "user_id": str(target.id)}


@router.post("/users/{user_id}/reset-password", response_model=PasswordResetResult)
async def reset_password(
    user_id: str,
    request: Request,
    user: User = Depends(_get_current_user),
    session: AsyncSession = Depends(get_session),
):
    _require_super_admin(user)
    ip, ua = _req_meta(request)

    result = await session.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    temp_password = secrets.token_urlsafe(12)
    target.password_hash = hash_password(temp_password)
    target.failed_login_attempts = 0
    target.locked_until = None
    await session.flush()

    await log_action(
        session, tenant_id=target.tenant_id, user_id=user.id,
        action="user.password_reset", entity_type="user", entity_id=str(target.id),
        new_value={"email": target.email, "reset_by": str(user.id)},
        ip_address=ip, user_agent=ua,
    )

    return PasswordResetResult(
        temporary_password=temp_password,
        message=f"Password reset for {target.email}. Share the temporary password securely.",
    )
