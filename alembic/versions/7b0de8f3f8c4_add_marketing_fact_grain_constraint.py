"""add unique grain constraint to fact_marketing_daily

Revision ID: 7b0de8f3f8c4
Revises: db000f00160b
Create Date: 2025-02-14 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "7b0de8f3f8c4"
down_revision = "db000f00160b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "ux_fact_marketing_daily_grain",
        "fact_marketing_daily",
        [
            "platform_id",
            "account_id",
            "campaign_id",
            "adset_id",
            "ad_id",
            "date_id",
            "dma_id",
            "region_id",
            "country_id",
        ],
    )


def downgrade() -> None:
    op.drop_constraint(
        "ux_fact_marketing_daily_grain",
        "fact_marketing_daily",
        type_="unique",
    )
