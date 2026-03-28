"""Seed platform-level default configuration and permission groups.

Run: python -m db.seed_defaults
"""
from __future__ import annotations

import asyncio
import os

from dotenv import load_dotenv

load_dotenv()

DEFAULT_SLA_MATRIX = {
    "critical": {"response_hours": 1, "resolution_hours": 4},
    "high": {"response_hours": 4, "resolution_hours": 8},
    "medium": {"response_hours": 8, "resolution_hours": 72},
    "low": {"response_hours": 48, "resolution_hours": 120},
}

DEFAULT_HEALTH_SCORE_WEIGHTS = {
    "sla_compliance": 0.3,
    "ticket_aging": 0.2,
    "effort_utilization": 0.2,
    "risk_count": 0.15,
    "milestone_adherence": 0.15,
}

DEFAULT_ESCALATION_RULES = {
    "sla_breach_critical": True,
    "sla_breach_high": True,
    "days_without_update": 3,
    "unassigned_hours": 4,
}

DEFAULT_MILESTONE_BILLING_SPLIT = [25, 25, 25, 25]

DEFAULT_PERMISSION_GROUPS = [
    {
        "name": "Leadership",
        "permissions": [
            "reports.view",
            "finance.view",
            "dashboard.view",
            "tickets.view",
            "projects.view",
            "changes.approve",
            "escalations.view",
            "health.view",
        ],
    },
    {
        "name": "Program Manager",
        "permissions": [
            "reports.view",
            "finance.view",
            "dashboard.view",
            "tickets.view",
            "tickets.write",
            "projects.view",
            "projects.write",
            "team.manage",
            "config.manage",
            "changes.approve",
            "escalations.view",
            "escalations.manage",
            "health.view",
            "effort.view",
            "effort.write",
        ],
    },
    {
        "name": "Consultant",
        "permissions": [
            "tickets.view",
            "tickets.write",
            "effort.view",
            "effort.write",
            "projects.view_assigned",
            "dashboard.view",
        ],
    },
    {
        "name": "Client Viewer",
        "permissions": [
            "dashboard.view",
            "tickets.view",
            "projects.view",
            "reports.view",
            "health.view",
        ],
    },
]


async def seed_defaults() -> None:
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession

    from db.config import async_session
    from db.models import PermissionGroup

    if async_session is None:
        raise RuntimeError("DATABASE_URL is not configured")
    async with async_session() as session:  # type: AsyncSession
        # Check if default permission groups already exist
        result = await session.execute(
            select(PermissionGroup).where(PermissionGroup.is_default == True)
        )
        existing = result.scalars().all()
        existing_names = {g.name for g in existing}

        for group_def in DEFAULT_PERMISSION_GROUPS:
            if group_def["name"] not in existing_names:
                session.add(PermissionGroup(
                    tenant_id=None,
                    name=group_def["name"],
                    permissions=group_def["permissions"],
                    is_default=True,
                ))
                print(f"  Created default permission group: {group_def['name']}")
            else:
                print(f"  Skipped (already exists): {group_def['name']}")

        await session.commit()
        print("Default permission groups seeded.")


if __name__ == "__main__":
    asyncio.run(seed_defaults())
