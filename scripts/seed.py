#!/usr/bin/env python3
"""
Database seed script — creates a demo user and sample analysis for development.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

# Ensure we can import the app
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models.user import User, UserPlan
from app.models.analysis import Analysis, AnalysisStatus, UploadedFile
from app.models.insight import Insight


async def seed() -> None:
    engine = create_async_engine(settings.async_database_url, echo=False)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as db:
        # Demo user
        demo_user = User(
            id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
            supabase_id="demo-user",
            email="demo@zephyr.ai",
            full_name="Demo User",
            plan=UserPlan.PRO.value,
            is_active=True,
            is_verified=True,
        )
        db.add(demo_user)
        await db.flush()

        # Demo uploaded file
        demo_file = UploadedFile(
            id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
            user_id=demo_user.id,
            filename="sales_2024.csv",
            original_filename="sales_2024.csv",
            file_size=4096,
            mime_type="text/csv",
            storage_path="/dev/null",
            row_count=12000,
            column_count=8,
            columns=[
                {"name": "date", "dtype": "date"},
                {"name": "revenue", "dtype": "float64"},
                {"name": "orders", "dtype": "int64"},
                {"name": "region", "dtype": "string"},
                {"name": "product", "dtype": "string"},
                {"name": "cost", "dtype": "float64"},
                {"name": "customers", "dtype": "int64"},
                {"name": "returns", "dtype": "int64"},
            ],
        )
        db.add(demo_file)
        await db.flush()

        # Demo analysis
        demo_analysis = Analysis(
            id=uuid.UUID("00000000-0000-0000-0000-000000000003"),
            user_id=demo_user.id,
            file_id=demo_file.id,
            name="Sales Performance 2024",
            status=AnalysisStatus.COMPLETED.value,
            progress=100,
            row_count=12000,
            column_count=8,
            summary=(
                "Revenue reached $4.2M in 2024, a 23% year-over-year increase\n"
                "Q4 was the strongest quarter, contributing 34% of annual revenue\n"
                "West region outperformed all others with $1.8M in sales\n"
                "Customer acquisition grew 18% while churn held below 5%\n"
                "Product line A generated the highest margin at 42%"
            ),
            charts=[],
            metadata_={},
        )
        db.add(demo_analysis)
        await db.flush()

        # KPI insights
        kpis = [
            ("Total Revenue", "summary", "Total revenue: $4,200,000", "critical", {"value": 4200000, "is_currency": True, "kpi_type": "revenue"}),
            ("Total Orders", "summary", "Total orders: 12,000", "high", {"value": 12000, "is_currency": False, "kpi_type": "orders"}),
        ]
        for i, (title, itype, desc, imp, data) in enumerate(kpis):
            db.add(Insight(
                analysis_id=demo_analysis.id,
                type=itype,
                title=title,
                description=desc,
                importance=imp,
                confidence=0.99,
                sort_order=i,
                data=data,
            ))

        # AI insight
        db.add(Insight(
            analysis_id=demo_analysis.id,
            type="trend",
            title="Q4 Revenue Surge",
            description="Revenue spiked 47% in Q4 compared to Q3, driven by holiday promotions in the West region.",
            importance="critical",
            confidence=0.92,
            sort_order=100,
            data={"period": "Q4 2024", "growth": 47},
        ))

        await db.commit()
        print("✅ Seed complete: demo user, file, and analysis created")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
