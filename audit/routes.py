from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.routes import _get_current_user
from db.config import get_session
from db.models import AuditLog, User

router = APIRouter(prefix="/api/audit", tags=["audit"])

ALLOWED_ROLES = {"super_admin", "client_superadmin"}


# ---------- schemas ----------

class AuditLogEntry(BaseModel):
    id: str
    tenant_id: str | None
    user_id: str | None
    action: str
    entity_type: str
    entity_id: str | None
    old_value: Any | None
    new_value: Any | None
    ip_address: str | None
    user_agent: str | None
    created_at: datetime

    class Config:
        from_attributes = True


class PaginatedAuditResponse(BaseModel):
    items: list[AuditLogEntry]
    total: int
    page: int
    per_page: int
    pages: int


# ---------- helpers ----------

def _parse_json_field(value: str | None) -> Any:
    if value is None:
        return None
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return value


def _to_entry(row: AuditLog) -> AuditLogEntry:
    return AuditLogEntry(
        id=str(row.id),
        tenant_id=str(row.tenant_id) if row.tenant_id else None,
        user_id=str(row.user_id) if row.user_id else None,
        action=row.action,
        entity_type=row.entity_type,
        entity_id=row.entity_id,
        old_value=_parse_json_field(row.old_value),
        new_value=_parse_json_field(row.new_value),
        ip_address=row.ip_address,
        user_agent=row.user_agent,
        created_at=row.created_at,
    )


def _build_query(
    user: User,
    tenant_id: str | None,
    user_id: str | None,
    action: str | None,
    entity_type: str | None,
    start_date: datetime | None,
    end_date: datetime | None,
):
    stmt = select(AuditLog)

    # Scope by role
    if user.role != "super_admin":
        stmt = stmt.where(AuditLog.tenant_id == user.tenant_id)
    elif tenant_id:
        stmt = stmt.where(AuditLog.tenant_id == tenant_id)

    if user_id:
        stmt = stmt.where(AuditLog.user_id == user_id)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if start_date:
        stmt = stmt.where(AuditLog.created_at >= start_date)
    if end_date:
        stmt = stmt.where(AuditLog.created_at <= end_date)

    return stmt


def _require_audit_role(user: User) -> None:
    if user.role not in ALLOWED_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to view audit logs",
        )


# ---------- endpoints ----------

@router.get("/logs", response_model=PaginatedAuditResponse)
async def get_audit_logs(
    tenant_id: str | None = Query(None),
    user_id: str | None = Query(None),
    action: str | None = Query(None),
    entity_type: str | None = Query(None),
    start_date: datetime | None = Query(None),
    end_date: datetime | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    user: User = Depends(_get_current_user),
    session: AsyncSession = Depends(get_session),
):
    _require_audit_role(user)

    base = _build_query(user, tenant_id, user_id, action, entity_type, start_date, end_date)

    # Total count
    count_result = await session.execute(select(func.count()).select_from(base.subquery()))
    total = count_result.scalar_one()

    # Paginated results
    stmt = base.order_by(AuditLog.created_at.desc()).offset((page - 1) * per_page).limit(per_page)
    result = await session.execute(stmt)
    rows = result.scalars().all()

    return PaginatedAuditResponse(
        items=[_to_entry(r) for r in rows],
        total=total,
        page=page,
        per_page=per_page,
        pages=(total + per_page - 1) // per_page if total > 0 else 0,
    )


@router.get("/logs/export")
async def export_audit_logs(
    tenant_id: str | None = Query(None),
    user_id: str | None = Query(None),
    action: str | None = Query(None),
    entity_type: str | None = Query(None),
    start_date: datetime | None = Query(None),
    end_date: datetime | None = Query(None),
    user: User = Depends(_get_current_user),
    session: AsyncSession = Depends(get_session),
):
    _require_audit_role(user)

    base = _build_query(user, tenant_id, user_id, action, entity_type, start_date, end_date)
    stmt = base.order_by(AuditLog.created_at.desc())
    result = await session.execute(stmt)
    rows = result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "id", "tenant_id", "user_id", "action", "entity_type",
        "entity_id", "old_value", "new_value", "ip_address",
        "user_agent", "created_at",
    ])
    for r in rows:
        writer.writerow([
            str(r.id),
            str(r.tenant_id) if r.tenant_id else "",
            str(r.user_id) if r.user_id else "",
            r.action,
            r.entity_type,
            r.entity_id or "",
            r.old_value or "",
            r.new_value or "",
            r.ip_address or "",
            r.user_agent or "",
            r.created_at.isoformat(),
        ])

    output.seek(0)
    return StreamingResponse(
        output,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit-logs.csv"},
    )
