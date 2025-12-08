"""add shopify staging metrics

Revision ID: 202512080512
Revises: 9b3f4e3b25c3
Create Date: 2025-12-08 05:12:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '202512080512'
down_revision = '9b3f4e3b25c3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'stg_shopify_daily_city',
        sa.Column('total_sales', sa.Numeric(18, 4), server_default=sa.text('0'), nullable=True),
    )
    op.add_column(
        'stg_shopify_daily_city',
        sa.Column('net_sales', sa.Numeric(18, 4), server_default=sa.text('0'), nullable=True),
    )
    op.add_column(
        'stg_shopify_daily_city',
        sa.Column('duties', sa.Numeric(18, 4), server_default=sa.text('0'), nullable=True),
    )
    op.add_column(
        'stg_shopify_daily_city',
        sa.Column('taxes', sa.Numeric(18, 4), server_default=sa.text('0'), nullable=True),
    )
    op.add_column(
        'stg_shopify_daily_city',
        sa.Column('returning_customers', sa.Numeric(18, 4), server_default=sa.text('0'), nullable=True),
    )
    op.add_column(
        'stg_shopify_daily_city',
        sa.Column('new_customers', sa.Numeric(18, 4), server_default=sa.text('0'), nullable=True),
    )
    op.add_column(
        'stg_shopify_daily_city',
        sa.Column('checkout_sessions', sa.Numeric(18, 4), server_default=sa.text('0'), nullable=True),
    )
    op.add_column(
        'stg_shopify_daily_city',
        sa.Column('online_store_visitors', sa.Numeric(18, 4), server_default=sa.text('0'), nullable=True),
    )
    op.add_column(
        'stg_shopify_daily_city',
        sa.Column('sessions', sa.Numeric(18, 4), server_default=sa.text('0'), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('stg_shopify_daily_city', 'sessions')
    op.drop_column('stg_shopify_daily_city', 'online_store_visitors')
    op.drop_column('stg_shopify_daily_city', 'checkout_sessions')
    op.drop_column('stg_shopify_daily_city', 'new_customers')
    op.drop_column('stg_shopify_daily_city', 'returning_customers')
    op.drop_column('stg_shopify_daily_city', 'taxes')
    op.drop_column('stg_shopify_daily_city', 'duties')
    op.drop_column('stg_shopify_daily_city', 'net_sales')
    op.drop_column('stg_shopify_daily_city', 'total_sales')
