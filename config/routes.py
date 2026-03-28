from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from audit.service import log_action
from auth.routes import _get_current_user
from db.config import get_session
from db.models import PermissionGroup, Tenant, TenantConfig, User
from db.seed_defaults import (
    DEFAULT_ESCALATION_RULES,
    DEFAULT_HEALTH_SCORE_WEIGHTS,
    DEFAULT_MILESTONE_BILLING_SPLIT,
    DEFAULT_SLA_MATRIX,
)

router = APIRouter(prefix="/api/config", tags=["config"])


# ---------- helpers ----------

def _require_super_admin(user: User) -> None:
    if user.role != "super_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Super admin access required")


def _req_meta(request: Request) -> tuple[str | None, str | None]:
    ip = request.headers.get("x-forwarded-for", request.client.host if request.client else None)
    ua = request.headers.get("user-agent")
    return ip, ua


def _config_to_dict(cfg: TenantConfig) -> dict:
    return {
        "sla_matrix": cfg.sla_matrix,
        "effort_bucket_type": cfg.effort_bucket_type,
        "effort_bucket_hours": str(cfg.effort_bucket_hours) if cfg.effort_bucket_hours is not None else None,
        "effort_rate_per_hour": str(cfg.effort_rate_per_hour) if cfg.effort_rate_per_hour is not None else None,
        "billing_currency": cfg.billing_currency,
        "billing_cycle": cfg.billing_cycle,
        "milestone_billing_split": cfg.milestone_billing_split,
        "escalation_rules": cfg.escalation_rules,
        "health_score_weights": cfg.health_score_weights,
        "modules": cfg.modules,
        "notification_preferences": cfg.notification_preferences,
    }


def _merge_config(tenant_cfg: TenantConfig | None) -> dict:
    """Return merged config: tenant overrides on top of platform defaults."""
    base = {
        "sla_matrix": DEFAULT_SLA_MATRIX,
        "effort_bucket_type": None,
        "effort_bucket_hours": None,
        "effort_rate_per_hour": None,
        "billing_currency": "USD",
        "billing_cycle": None,
        "milestone_billing_split": DEFAULT_MILESTONE_BILLING_SPLIT,
        "escalation_rules": DEFAULT_ESCALATION_RULES,
        "health_score_weights": DEFAULT_HEALTH_SCORE_WEIGHTS,
        "modules": None,
        "notification_preferences": None,
    }
    if tenant_cfg is None:
        return base

    overrides = _config_to_dict(tenant_cfg)
    for key, value in overrides.items():
        if value is not None:
            base[key] = value
    return base


# ---------- schemas ----------

class TenantConfigUpdate(BaseModel):
    sla_matrix: dict | None = None
    effort_bucket_type: str | None = None
    effort_bucket_hours: Decimal | None = None
    effort_rate_per_hour: Decimal | None = None
    billing_currency: str | None = None
    billing_cycle: str | None = None
    milestone_billing_split: list | None = None
    escalation_rules: dict | None = None
    health_score_weights: dict | None = None
    modules: list | None = None
    notification_preferences: dict | None = None


class PermissionGroupOut(BaseModel):
    id: str
    tenant_id: str | None
    name: str
    permissions: list
    is_default: bool

    class Config:
        from_attributes = True


# ---------- endpoints ----------

@router.get("/defaults")
async def get_defaults(
    user: User = Depends(_get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Return all platform-level defaults."""
    _require_super_admin(user)

    # Fetch default permission groups
    result = await session.execute(
        select(PermissionGroup).where(PermissionGroup.is_default == True).order_by(PermissionGroup.name)
    )
    perm_groups = result.scalars().all()

    return {
        "sla_matrix": DEFAULT_SLA_MATRIX,
        "health_score_weights": DEFAULT_HEALTH_SCORE_WEIGHTS,
        "escalation_rules": DEFAULT_ESCALATION_RULES,
        "milestone_billing_split": DEFAULT_MILESTONE_BILLING_SPLIT,
        "permission_groups": [
            PermissionGroupOut(
                id=str(g.id), tenant_id=str(g.tenant_id) if g.tenant_id else None,
                name=g.name, permissions=g.permissions or [], is_default=g.is_default,
            ).model_dump()
            for g in perm_groups
        ],
    }


@router.get("/tenant/{tenant_id}")
async def get_tenant_config(
    tenant_id: str,
    user: User = Depends(_get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Return merged config for a tenant (tenant overrides + platform defaults)."""
    # Access: super_admin OR user belonging to this tenant
    if user.role != "super_admin" and str(user.tenant_id) != tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    # Verify tenant exists
    tenant = (await session.execute(select(Tenant).where(Tenant.id == tenant_id))).scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    # Get tenant-specific config
    cfg = (await session.execute(
        select(TenantConfig).where(TenantConfig.tenant_id == tenant_id)
    )).scalar_one_or_none()

    merged = _merge_config(cfg)

    # Get permission groups: tenant-specific + defaults
    perm_result = await session.execute(
        select(PermissionGroup).where(
            (PermissionGroup.tenant_id == tenant_id) | (PermissionGroup.is_default == True)
        ).order_by(PermissionGroup.name)
    )
    perm_groups = perm_result.scalars().all()

    return {
        "tenant_id": tenant_id,
        "config": merged,
        "has_overrides": cfg is not None,
        "permission_groups": [
            PermissionGroupOut(
                id=str(g.id), tenant_id=str(g.tenant_id) if g.tenant_id else None,
                name=g.name, permissions=g.permissions or [], is_default=g.is_default,
            ).model_dump()
            for g in perm_groups
        ],
    }


@router.put("/tenant/{tenant_id}")
async def update_tenant_config(
    tenant_id: str,
    body: TenantConfigUpdate,
    request: Request,
    user: User = Depends(_get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Create or update tenant-specific config. Super admin only."""
    _require_super_admin(user)
    ip, ua = _req_meta(request)

    # Verify tenant exists
    tenant = (await session.execute(select(Tenant).where(Tenant.id == tenant_id))).scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    # Get or create config
    cfg = (await session.execute(
        select(TenantConfig).where(TenantConfig.tenant_id == tenant_id)
    )).scalar_one_or_none()

    old_value: dict[str, Any] | None = None
    if cfg:
        old_value = _config_to_dict(cfg)
    else:
        cfg = TenantConfig(tenant_id=tenant.id)
        session.add(cfg)

    updates = body.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(cfg, field, value)
    await session.flush()

    await log_action(
        session, tenant_id=tenant.id, user_id=user.id,
        action="config.updated", entity_type="tenant_config", entity_id=str(cfg.id),
        old_value=old_value, new_value=_config_to_dict(cfg),
        ip_address=ip, user_agent=ua,
    )

    merged = _merge_config(cfg)

    return {
        "tenant_id": tenant_id,
        "config": merged,
        "message": "Configuration updated",
    }


@router.get("/permissions")
async def list_permission_groups(
    tenant_id: str | None = None,
    user: User = Depends(_get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Return permission groups. Defaults + tenant-specific if tenant_id provided."""
    stmt = select(PermissionGroup)
    if tenant_id:
        # Access check
        if user.role != "super_admin" and str(user.tenant_id) != tenant_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
        stmt = stmt.where(
            (PermissionGroup.tenant_id == tenant_id) | (PermissionGroup.is_default == True)
        )
    else:
        if user.role != "super_admin":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Super admin access required")
        stmt = stmt.where(PermissionGroup.is_default == True)

    result = await session.execute(stmt.order_by(PermissionGroup.name))
    groups = result.scalars().all()

    return [
        PermissionGroupOut(
            id=str(g.id), tenant_id=str(g.tenant_id) if g.tenant_id else None,
            name=g.name, permissions=g.permissions or [], is_default=g.is_default,
        ).model_dump()
        for g in groups
    ]
