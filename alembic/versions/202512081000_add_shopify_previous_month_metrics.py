"""add previous month shopify metrics

Revision ID: 202512081000
Revises: 202512080512
Create Date: 2025-12-08 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '202512081000'
down_revision = '202512080512'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'stg_shopify_daily_city',
        sa.Column('orders_previous_month', sa.Numeric(18, 4), server_default=sa.text('0'), nullable=True),
    )
    op.add_column(
        'stg_shopify_daily_city',
        sa.Column('gross_sales_previous_month', sa.Numeric(18, 4), server_default=sa.text('0'), nullable=True),
    )
    op.add_column(
        'stg_shopify_daily_city',
        sa.Column('total_sales_previous_month', sa.Numeric(18, 4), server_default=sa.text('0'), nullable=True),
    )
    op.add_column(
        'stg_shopify_daily_city',
        sa.Column('net_sales_previous_month', sa.Numeric(18, 4), server_default=sa.text('0'), nullable=True),
    )
    op.add_column(
        'stg_shopify_daily_city',
        sa.Column('duties_previous_month', sa.Numeric(18, 4), server_default=sa.text('0'), nullable=True),
    )
    op.add_column(
        'stg_shopify_daily_city',
        sa.Column('taxes_previous_month', sa.Numeric(18, 4), server_default=sa.text('0'), nullable=True),
    )
    op.add_column(
        'stg_shopify_daily_city',
        sa.Column('returning_customers_previous_month', sa.Numeric(18, 4), server_default=sa.text('0'), nullable=True),
    )
    op.add_column(
        'stg_shopify_daily_city',
        sa.Column('new_customers_previous_month', sa.Numeric(18, 4), server_default=sa.text('0'), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('stg_shopify_daily_city', 'new_customers_previous_month')
    op.drop_column('stg_shopify_daily_city', 'returning_customers_previous_month')
    op.drop_column('stg_shopify_daily_city', 'taxes_previous_month')
    op.drop_column('stg_shopify_daily_city', 'duties_previous_month')
    op.drop_column('stg_shopify_daily_city', 'net_sales_previous_month')
    op.drop_column('stg_shopify_daily_city', 'total_sales_previous_month')
    op.drop_column('stg_shopify_daily_city', 'gross_sales_previous_month')
    op.drop_column('stg_shopify_daily_city', 'orders_previous_month')
