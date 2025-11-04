"""create marketing warehouse schema

Revision ID: db000f00160b
Revises: f8b25d2de45f
Create Date: 2025-11-04 08:41:18.957427

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "db000f00160b"
down_revision = "f8b25d2de45f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dim_platform",
        sa.Column("platform_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("platform_id", name="dim_platform_pkey"),
    )

    op.create_table(
        "dim_dma",
        sa.Column("dma_id", sa.Integer(), nullable=False),
        sa.Column("dma_code", sa.Text(), nullable=False),
        sa.Column("dma_name", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("dma_id", name="dim_dma_pkey"),
        sa.UniqueConstraint("dma_code", name="dim_dma_dma_code_key"),
    )

    op.create_table(
        "map_platform_dma",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("platform_id", sa.Integer(), nullable=False),
        sa.Column("platform_dma_label", sa.Text(), nullable=False),
        sa.Column("dma_id", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="map_platform_dma_pkey"),
        sa.ForeignKeyConstraint(
            ["dma_id"],
            ["dim_dma.dma_id"],
            name="map_platform_dma_dma_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["platform_id"],
            ["dim_platform.platform_id"],
            name="map_platform_dma_platform_id_fkey",
        ),
    )

    op.create_table(
        "dim_account",
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("platform_id", sa.Integer(), nullable=False),
        sa.Column("external_account_id", sa.Text(), nullable=True),
        sa.Column("account_name", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("account_id", name="dim_account_pkey"),
        sa.ForeignKeyConstraint(
            ["platform_id"],
            ["dim_platform.platform_id"],
            name="dim_account_platform_id_fkey",
        ),
    )

    op.create_table(
        "dim_campaign",
        sa.Column("campaign_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("external_campaign_id", sa.Text(), nullable=True),
        sa.Column("campaign_name", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("campaign_id", name="dim_campaign_pkey"),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["dim_account.account_id"],
            name="dim_campaign_account_id_fkey",
        ),
    )

    op.create_table(
        "dim_adset_or_adgroup",
        sa.Column("adset_id", sa.Integer(), nullable=False),
        sa.Column("campaign_id", sa.Integer(), nullable=False),
        sa.Column("external_adset_id", sa.Text(), nullable=True),
        sa.Column("adset_name", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("adset_id", name="dim_adset_or_adgroup_pkey"),
        sa.ForeignKeyConstraint(
            ["campaign_id"],
            ["dim_campaign.campaign_id"],
            name="dim_adset_or_adgroup_campaign_id_fkey",
        ),
    )

    op.create_table(
        "dim_ad",
        sa.Column("ad_id", sa.Integer(), nullable=False),
        sa.Column("adset_id", sa.Integer(), nullable=False),
        sa.Column("external_ad_id", sa.Text(), nullable=True),
        sa.Column("ad_name", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("ad_id", name="dim_ad_pkey"),
        sa.ForeignKeyConstraint(
            ["adset_id"],
            ["dim_adset_or_adgroup.adset_id"],
            name="dim_ad_adset_id_fkey",
        ),
    )

    op.create_table(
        "dim_attribution",
        sa.Column("attribution_id", sa.Integer(), nullable=False),
        sa.Column("platform_id", sa.Integer(), nullable=False),
        sa.Column("window_type", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("attribution_id", name="dim_attribution_pkey"),
        sa.ForeignKeyConstraint(
            ["platform_id"],
            ["dim_platform.platform_id"],
            name="dim_attribution_platform_id_fkey",
        ),
    )

    op.create_table(
        "dim_country",
        sa.Column("country_id", sa.Integer(), nullable=False),
        sa.Column("iso2", sa.Text(), nullable=False),
        sa.Column("country_name", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("country_id", name="dim_country_pkey"),
    )

    op.create_table(
        "dim_region",
        sa.Column("region_id", sa.Integer(), nullable=False),
        sa.Column("country_id", sa.Integer(), nullable=False),
        sa.Column("region_name", sa.Text(), nullable=False),
        sa.Column("iso_subdivision", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("region_id", name="dim_region_pkey"),
        sa.ForeignKeyConstraint(
            ["country_id"],
            ["dim_country.country_id"],
            name="dim_region_country_id_fkey",
        ),
    )

    op.create_table(
        "dim_city",
        sa.Column("city_id", sa.Integer(), nullable=False),
        sa.Column("region_id", sa.Integer(), nullable=False),
        sa.Column("city_name", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("city_id", name="dim_city_pkey"),
        sa.ForeignKeyConstraint(
            ["region_id"],
            ["dim_region.region_id"],
            name="dim_city_region_id_fkey",
        ),
    )

    op.create_table(
        "dim_postal",
        sa.Column("postal_id", sa.Integer(), nullable=False),
        sa.Column("city_id", sa.Integer(), nullable=False),
        sa.Column("postal_code", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("postal_id", name="dim_postal_pkey"),
        sa.ForeignKeyConstraint(
            ["city_id"],
            ["dim_city.city_id"],
            name="dim_postal_city_id_fkey",
        ),
    )

    op.create_table(
        "dim_date",
        sa.Column("date_id", sa.Integer(), nullable=False),
        sa.Column("date_actual", sa.Date(), nullable=False),
        sa.Column("week", sa.Integer(), nullable=True),
        sa.Column("month", sa.Integer(), nullable=True),
        sa.Column("quarter", sa.Integer(), nullable=True),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("date_id", name="dim_date_pkey"),
    )

    op.create_table(
        "fact_marketing_daily",
        sa.Column("fact_id", sa.BigInteger(), nullable=False),
        sa.Column("platform_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("campaign_id", sa.Integer(), nullable=False),
        sa.Column("adset_id", sa.Integer(), nullable=False),
        sa.Column("ad_id", sa.Integer(), nullable=False),
        sa.Column("date_id", sa.Integer(), nullable=False),
        sa.Column("attribution_id", sa.Integer(), nullable=True),
        sa.Column("country_id", sa.Integer(), nullable=True),
        sa.Column("region_id", sa.Integer(), nullable=True),
        sa.Column("dma_id", sa.Integer(), nullable=True),
        sa.Column("currency_code", sa.Text(), nullable=True),
        sa.Column("spend", sa.Numeric(), nullable=True),
        sa.Column("impressions", sa.BigInteger(), nullable=True),
        sa.Column("clicks", sa.BigInteger(), nullable=True),
        sa.Column("conversions", sa.BigInteger(), nullable=True),
        sa.Column("conversion_value", sa.Numeric(), nullable=True),
        sa.Column("video_view_time", sa.BigInteger(), nullable=True),
        sa.Column("frequency", sa.Numeric(), nullable=True),
        sa.Column("reach", sa.BigInteger(), nullable=True),
        sa.Column("add_to_cart", sa.BigInteger(), nullable=True),
        sa.PrimaryKeyConstraint("fact_id", name="fact_marketing_daily_pkey"),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["dim_account.account_id"],
            name="fact_marketing_daily_account_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["ad_id"],
            ["dim_ad.ad_id"],
            name="fact_marketing_daily_ad_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["adset_id"],
            ["dim_adset_or_adgroup.adset_id"],
            name="fact_marketing_daily_adset_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["attribution_id"],
            ["dim_attribution.attribution_id"],
            name="fact_marketing_daily_attribution_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["campaign_id"],
            ["dim_campaign.campaign_id"],
            name="fact_marketing_daily_campaign_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["country_id"],
            ["dim_country.country_id"],
            name="fact_marketing_daily_country_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["date_id"],
            ["dim_date.date_id"],
            name="fact_marketing_daily_date_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["dma_id"],
            ["dim_dma.dma_id"],
            name="fact_marketing_daily_dma_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["platform_id"],
            ["dim_platform.platform_id"],
            name="fact_marketing_daily_platform_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["region_id"],
            ["dim_region.region_id"],
            name="fact_marketing_daily_region_id_fkey",
        ),
    )

    op.create_table(
        "fact_shopify_daily",
        sa.Column("fact_id", sa.BigInteger(), nullable=False),
        sa.Column("date_id", sa.Integer(), nullable=False),
        sa.Column("country_id", sa.Integer(), nullable=False),
        sa.Column("region_id", sa.Integer(), nullable=False),
        sa.Column("city_id", sa.Integer(), nullable=False),
        sa.Column("postal_id", sa.Integer(), nullable=False),
        sa.Column("currency_code", sa.Text(), nullable=True),
        sa.Column("sessions", sa.BigInteger(), nullable=True),
        sa.Column("orders", sa.BigInteger(), nullable=True),
        sa.Column("revenue", sa.Numeric(), nullable=True),
        sa.Column("add_to_cart", sa.BigInteger(), nullable=True),
        sa.PrimaryKeyConstraint("fact_id", name="fact_shopify_daily_pkey"),
        sa.ForeignKeyConstraint(
            ["city_id"],
            ["dim_city.city_id"],
            name="fact_shopify_daily_city_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["country_id"],
            ["dim_country.country_id"],
            name="fact_shopify_daily_country_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["date_id"],
            ["dim_date.date_id"],
            name="fact_shopify_daily_date_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["postal_id"],
            ["dim_postal.postal_id"],
            name="fact_shopify_daily_postal_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["region_id"],
            ["dim_region.region_id"],
            name="fact_shopify_daily_region_id_fkey",
        ),
    )

    op.create_table(
        "fact_model_results",
        sa.Column("model_run_id", sa.Integer(), nullable=False),
        sa.Column("model_name", sa.Text(), nullable=False),
        sa.Column("run_timestamp", sa.DateTime(timezone=False), server_default=sa.text("now()"), nullable=False),
        sa.Column("platform_id", sa.Integer(), nullable=True),
        sa.Column("dma_id", sa.Integer(), nullable=True),
        sa.Column("date_id", sa.Integer(), nullable=True),
        sa.Column("predicted_sales", sa.Numeric(), nullable=True),
        sa.Column("attributed_sales", sa.Numeric(), nullable=True),
        sa.Column("effect_size", sa.Numeric(), nullable=True),
        sa.Column("confidence_interval", postgresql.JSONB(), nullable=True),
        sa.Column("feature_importances", postgresql.JSONB(), nullable=True),
        sa.Column("model_version", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("model_run_id", name="fact_model_results_pkey"),
        sa.UniqueConstraint(
            "model_name",
            "model_version",
            "platform_id",
            "dma_id",
            "date_id",
            name="ux_model_result",
        ),
        sa.ForeignKeyConstraint(
            ["date_id"],
            ["dim_date.date_id"],
            name="fact_model_results_date_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["dma_id"],
            ["dim_dma.dma_id"],
            name="fact_model_results_dma_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["platform_id"],
            ["dim_platform.platform_id"],
            name="fact_model_results_platform_id_fkey",
        ),
    )
    op.create_index("ix_model_results_date", "fact_model_results", ["date_id"], unique=False)
    op.create_index("ix_model_results_geo", "fact_model_results", ["dma_id"], unique=False)

    op.create_table(
        "stg_shopify_daily_city",
        sa.Column("date_id", sa.Date(), nullable=False),
        sa.Column("platform_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("country_iso2", sa.Text(), nullable=False),
        sa.Column("region_code", sa.Text(), nullable=False),
        sa.Column("city_name_norm", sa.Text(), nullable=False),
        sa.Column("country_id", sa.Integer(), nullable=True),
        sa.Column("region_id", sa.Integer(), nullable=True),
        sa.Column("city_id", sa.Integer(), nullable=True),
        sa.Column("attribution_id", sa.Integer(), nullable=True),
        sa.Column("orders", sa.Numeric(18, 4), server_default=sa.text("0"), nullable=True),
        sa.Column("gross_sales", sa.Numeric(18, 4), server_default=sa.text("0"), nullable=True),
        sa.Column("refunds", sa.Numeric(18, 4), server_default=sa.text("0"), nullable=True),
        sa.Column("shipping", sa.Numeric(18, 4), server_default=sa.text("0"), nullable=True),
        sa.Column("_ingested_at", sa.DateTime(timezone=False), server_default=sa.text("now()"), nullable=True),
        sa.Column("_source_file", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint(
            "date_id",
            "account_id",
            "country_iso2",
            "region_code",
            "city_name_norm",
            name="stg_shopify_daily_city_pk",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["dim_account.account_id"],
            deferrable=True,
            initially="DEFERRED",
            name="stg_shopify_daily_city_account_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["attribution_id"],
            ["dim_attribution.attribution_id"],
            deferrable=True,
            initially="DEFERRED",
            name="stg_shopify_daily_city_attribution_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["city_id"],
            ["dim_city.city_id"],
            deferrable=True,
            initially="DEFERRED",
            name="stg_shopify_daily_city_city_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["country_id"],
            ["dim_country.country_id"],
            deferrable=True,
            initially="DEFERRED",
            name="stg_shopify_daily_city_country_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["platform_id"],
            ["dim_platform.platform_id"],
            deferrable=True,
            initially="DEFERRED",
            name="stg_shopify_daily_city_platform_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["region_id"],
            ["dim_region.region_id"],
            deferrable=True,
            initially="DEFERRED",
            name="stg_shopify_daily_city_region_id_fkey",
        ),
    )

    op.create_table(
        "map_city_dma",
        sa.Column("country_id", sa.Integer(), nullable=False),
        sa.Column("region_id", sa.Integer(), nullable=False),
        sa.Column("city_id", sa.Integer(), nullable=False),
        sa.Column("dma_id", sa.Integer(), nullable=False),
        sa.Column("effective_start_date", sa.Date(), server_default=sa.text("'2000-01-01'::date"), nullable=False),
        sa.Column("effective_end_date", sa.Date(), server_default=sa.text("'2999-12-31'::date"), nullable=False),
        sa.Column("dma_share", sa.Numeric(6, 5), server_default=sa.text("1.00000"), nullable=False),
        sa.PrimaryKeyConstraint(
            "country_id",
            "region_id",
            "city_id",
            "dma_id",
            "effective_start_date",
            name="map_city_dma_pk",
        ),
        sa.UniqueConstraint(
            "country_id",
            "region_id",
            "city_id",
            "effective_start_date",
            "effective_end_date",
            name="map_city_dma_city_window_unique",
        ),
        sa.ForeignKeyConstraint(
            ["city_id"],
            ["dim_city.city_id"],
            name="map_city_dma_city_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["country_id"],
            ["dim_country.country_id"],
            name="map_city_dma_country_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["dma_id"],
            ["dim_dma.dma_id"],
            name="map_city_dma_dma_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["region_id"],
            ["dim_region.region_id"],
            name="map_city_dma_region_id_fkey",
        ),
    )

    op.create_table(
        "map_postal_city_state",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("postal_code", sa.Text(), nullable=False),
        sa.Column("city_name", sa.Text(), nullable=False),
        sa.Column("state_code", sa.Text(), nullable=False),
        sa.Column("city_id", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="map_postal_city_state_pkey"),
        sa.ForeignKeyConstraint(
            ["city_id"],
            ["dim_city.city_id"],
            name="map_postal_city_state_city_id_fkey",
        ),
    )

    op.create_table(
        "metric_availability",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("platform_id", sa.Integer(), nullable=False),
        sa.Column("location_level", sa.Text(), nullable=False),
        sa.Column("metric_name", sa.Text(), nullable=False),
        sa.Column("is_available", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="metric_availability_pkey"),
        sa.ForeignKeyConstraint(
            ["platform_id"],
            ["dim_platform.platform_id"],
            name="metric_availability_platform_id_fkey",
        ),
    )

    op.create_table(
        "event_ingestion_log",
        sa.Column("log_id", sa.BigInteger(), nullable=False),
        sa.Column("platform_id", sa.Integer(), nullable=True),
        sa.Column("sync_timestamp", sa.DateTime(timezone=False), server_default=sa.text("now()"), nullable=False),
        sa.Column("records_fetched", sa.Integer(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("duration_seconds", sa.Numeric(), nullable=True),
        sa.PrimaryKeyConstraint("log_id", name="event_ingestion_log_pkey"),
        sa.ForeignKeyConstraint(
            ["platform_id"],
            ["dim_platform.platform_id"],
            name="event_ingestion_log_platform_id_fkey",
        ),
    )


def downgrade() -> None:
    op.drop_table("event_ingestion_log")
    op.drop_table("metric_availability")
    op.drop_table("map_postal_city_state")
    op.drop_table("map_city_dma")
    op.drop_table("stg_shopify_daily_city")
    op.drop_index("ix_model_results_geo", table_name="fact_model_results")
    op.drop_index("ix_model_results_date", table_name="fact_model_results")
    op.drop_table("fact_model_results")
    op.drop_table("fact_shopify_daily")
    op.drop_table("fact_marketing_daily")
    op.drop_table("dim_date")
    op.drop_table("dim_postal")
    op.drop_table("dim_city")
    op.drop_table("dim_region")
    op.drop_table("dim_country")
    op.drop_table("dim_attribution")
    op.drop_table("dim_ad")
    op.drop_table("dim_adset_or_adgroup")
    op.drop_table("dim_campaign")
    op.drop_table("dim_account")
    op.drop_table("map_platform_dma")
    op.drop_table("dim_dma")
    op.drop_table("dim_platform")
