from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from db.models import AuditLog


async def log_action(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID | str | None = None,
    user_id: uuid.UUID | str | None = None,
    action: str,
    entity_type: str,
    entity_id: str | None = None,
    old_value: Any = None,
    new_value: Any = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> None:
    """Append a single audit log entry. This is the sole entry point for all audit logging."""
    entry = AuditLog(
        tenant_id=uuid.UUID(str(tenant_id)) if tenant_id else None,
        user_id=uuid.UUID(str(user_id)) if user_id else None,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        old_value=json.dumps(old_value, default=str) if old_value is not None else None,
        new_value=json.dumps(new_value, default=str) if new_value is not None else None,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(entry)
    await db.commit()
