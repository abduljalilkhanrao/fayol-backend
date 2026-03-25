"""
Seed script — populates the database with initial tenants and the super-admin user.

Usage:
    python -m db.seed
"""

from __future__ import annotations

import asyncio
import os
from datetime import date
from decimal import Decimal

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

load_dotenv()

from db.config import _get_database_url  # noqa: E402
from db.models import Base, Tenant, User  # noqa: E402

from auth.security import hash_password as _hash_password


# ---------------------------------------------------------------------------
# Demo clients — mirrors the 10 hardcoded tenants from the frontend
# ---------------------------------------------------------------------------

DEMO_CLIENTS: list[dict] = [
    {
        "name": "Vantara Industries",
        "slug": "vantara",
        "tier": "platinum",
        "region": "AMER",
        "status": "active",
        "contract_start": date(2024, 1, 15),
        "contract_end": date(2026, 1, 14),
        "arr": Decimal("480000.00"),
    },
    {
        "name": "Meridian Logistics",
        "slug": "meridian",
        "tier": "gold",
        "region": "EMEA",
        "status": "active",
        "contract_start": date(2024, 3, 1),
        "contract_end": date(2026, 2, 28),
        "arr": Decimal("320000.00"),
    },
    {
        "name": "Helios Energy",
        "slug": "helios",
        "tier": "gold",
        "region": "AMER",
        "status": "active",
        "contract_start": date(2024, 6, 1),
        "contract_end": date(2026, 5, 31),
        "arr": Decimal("295000.00"),
    },
    {
        "name": "NovaChem Corp",
        "slug": "novachem",
        "tier": "silver",
        "region": "APAC",
        "status": "active",
        "contract_start": date(2024, 2, 1),
        "contract_end": date(2025, 7, 31),
        "arr": Decimal("185000.00"),
    },
    {
        "name": "Atlas Manufacturing",
        "slug": "atlas",
        "tier": "platinum",
        "region": "AMER",
        "status": "active",
        "contract_start": date(2023, 9, 1),
        "contract_end": date(2026, 8, 31),
        "arr": Decimal("520000.00"),
    },
    {
        "name": "Pinnacle Retail Group",
        "slug": "pinnacle",
        "tier": "silver",
        "region": "EMEA",
        "status": "active",
        "contract_start": date(2024, 4, 15),
        "contract_end": date(2025, 10, 14),
        "arr": Decimal("150000.00"),
    },
    {
        "name": "Cobalt Financial",
        "slug": "cobalt",
        "tier": "gold",
        "region": "AMER",
        "status": "active",
        "contract_start": date(2024, 1, 1),
        "contract_end": date(2025, 12, 31),
        "arr": Decimal("360000.00"),
    },
    {
        "name": "Zenith Pharma",
        "slug": "zenith",
        "tier": "platinum",
        "region": "APAC",
        "status": "active",
        "contract_start": date(2023, 11, 1),
        "contract_end": date(2026, 10, 31),
        "arr": Decimal("540000.00"),
    },
    {
        "name": "Orion Aerospace",
        "slug": "orion",
        "tier": "gold",
        "region": "AMER",
        "status": "paused",
        "contract_start": date(2024, 5, 1),
        "contract_end": date(2025, 4, 30),
        "arr": Decimal("275000.00"),
    },
    {
        "name": "TerraGreen Solutions",
        "slug": "terragreen",
        "tier": "bronze",
        "region": "EMEA",
        "status": "active",
        "contract_start": date(2024, 7, 1),
        "contract_end": date(2025, 6, 30),
        "arr": Decimal("95000.00"),
    },
]


async def seed() -> None:
    url = _get_database_url()
    if not url:
        raise RuntimeError("DATABASE_URL is not set")

    engine = create_async_engine(url, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Ensure tables exist (in case migrations haven't been run yet)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        # ------------------------------------------------------------------
        # 1. CyberCradle super-admin tenant
        # ------------------------------------------------------------------
        cybercradle = Tenant(
            name="CyberCradle",
            slug="cybercradle",
            tier="platinum",
            region="AMER",
            status="active",
            contract_start=date(2024, 1, 1),
            contract_end=date(2099, 12, 31),
            arr=Decimal("0.00"),
        )
        session.add(cybercradle)
        await session.flush()  # populate cybercradle.id

        # ------------------------------------------------------------------
        # 2. Super-admin user
        # ------------------------------------------------------------------
        admin_user = User(
            tenant_id=cybercradle.id,
            email="admin@cybercradle.io",
            password_hash=_hash_password("ChangeMeNow!2024"),
            full_name="CyberCradle Admin",
            role="super_admin",
        )
        session.add(admin_user)

        # ------------------------------------------------------------------
        # 3. Demo client tenants
        # ------------------------------------------------------------------
        for client in DEMO_CLIENTS:
            session.add(Tenant(**client))

        await session.commit()

    print("Seed complete — 1 admin tenant, 1 super-admin user, 10 demo clients.")


if __name__ == "__main__":
    asyncio.run(seed())
