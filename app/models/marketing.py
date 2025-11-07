"""ORM models representing the marketing analytics warehouse schema."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional           

from sqlalchemy import (         
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    PrimaryKeyConstraint,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
class DimPlatform(Base):
    __tablename__ = "dim_platform"

    platform_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)


class DimDMA(Base):
    __tablename__ = "dim_dma"

    dma_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dma_code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    dma_name: Mapped[str] = mapped_column(Text, nullable=False)


class MapPlatformDMA(Base):
    __tablename__ = "map_platform_dma"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    platform_id: Mapped[int] = mapped_column(ForeignKey("dim_platform.platform_id"), nullable=False)
    platform_dma_label: Mapped[str] = mapped_column(Text, nullable=False)
    dma_id: Mapped[int] = mapped_column(ForeignKey("dim_dma.dma_id"), nullable=False)


class DimAccount(Base):
    __tablename__ = "dim_account"

    account_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    platform_id: Mapped[int] = mapped_column(ForeignKey("dim_platform.platform_id"), nullable=False)
    external_account_id: Mapped[Optional[str]] = mapped_column(Text)
    account_name: Mapped[Optional[str]] = mapped_column(Text)


class DimCampaign(Base):
    __tablename__ = "dim_campaign"

    campaign_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("dim_account.account_id"), nullable=False)
    external_campaign_id: Mapped[Optional[str]] = mapped_column(Text)
    campaign_name: Mapped[Optional[str]] = mapped_column(Text)                                       


class DimAdsetOrAdgroup(Base):                                               
    __tablename__ = "dim_adset_or_adgroup"

    adset_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("dim_campaign.campaign_id"), nullable=False)
    external_adset_id: Mapped[Optional[str]] = mapped_column(Text)
    adset_name: Mapped[Optional[str]] = mapped_column(Text)


class DimAd(Base):
    __tablename__ = "dim_ad"

    ad_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    adset_id: Mapped[int] = mapped_column(ForeignKey("dim_adset_or_adgroup.adset_id"), nullable=False)
    external_ad_id: Mapped[Optional[str]] = mapped_column(Text)
    ad_name: Mapped[Optional[str]] = mapped_column(Text)


class DimAttribution(Base):
    __tablename__ = "dim_attribution"

    attribution_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    platform_id: Mapped[int] = mapped_column(ForeignKey("dim_platform.platform_id"), nullable=False)
    window_type: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)


class DimCountry(Base):          
    __tablename__ = "dim_country"

    country_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    iso2: Mapped[str] = mapped_column(Text, nullable=False)
    country_name: Mapped[str] = mapped_column(Text, nullable=False)


class DimRegion(Base):
    __tablename__ = "dim_region"

    region_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    country_id: Mapped[int] = mapped_column(ForeignKey("dim_country.country_id"), nullable=False)
    region_name: Mapped[str] = mapped_column(Text, nullable=False)
    iso_subdivision: Mapped[Optional[str]] = mapped_column(Text)


class DimCity(Base):          
    __tablename__ = "dim_city"

    city_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    region_id: Mapped[int] = mapped_column(ForeignKey("dim_region.region_id"), nullable=False)
    city_name: Mapped[str] = mapped_column(Text, nullable=False)


class DimPostal(Base): 
    __tablename__ = "dim_postal"

    postal_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    city_id: Mapped[int] = mapped_column(ForeignKey("dim_city.city_id"), nullable=False)
    postal_code: Mapped[str] = mapped_column(Text, nullable=False)


class DimDate(Base):          
    __tablename__ = "dim_date"

    date_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date_actual: Mapped[date] = mapped_column(Date, nullable=False)
    week: Mapped[Optional[int]] = mapped_column(Integer)
    month: Mapped[Optional[int]] = mapped_column(Integer)
    quarter: Mapped[Optional[int]] = mapped_column(Integer)
    year: Mapped[Optional[int]] = mapped_column(Integer)


class FactMarketingDaily(Base):                               
    __tablename__ = "fact_marketing_daily"             

    fact_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    platform_id: Mapped[int] = mapped_column(ForeignKey("dim_platform.platform_id"), nullable=False)
    account_id: Mapped[int] = mapped_column(ForeignKey("dim_account.account_id"), nullable=False)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("dim_campaign.campaign_id"), nullable=False)
    adset_id: Mapped[int] = mapped_column(ForeignKey("dim_adset_or_adgroup.adset_id"), nullable=False)
    ad_id: Mapped[int] = mapped_column(ForeignKey("dim_ad.ad_id"), nullable=False)
    date_id: Mapped[int] = mapped_column(ForeignKey("dim_date.date_id"), nullable=False)
    attribution_id: Mapped[Optional[int]] = mapped_column(ForeignKey("dim_attribution.attribution_id"))
    country_id: Mapped[Optional[int]] = mapped_column(ForeignKey("dim_country.country_id"))
    region_id: Mapped[Optional[int]] = mapped_column(ForeignKey("dim_region.region_id"))
    dma_id: Mapped[Optional[int]] = mapped_column(ForeignKey("dim_dma.dma_id"))
    currency_code: Mapped[Optional[str]] = mapped_column(Text)
    spend: Mapped[Optional[Decimal]] = mapped_column(Numeric)
    impressions: Mapped[Optional[int]] = mapped_column(BigInteger)
    clicks: Mapped[Optional[int]] = mapped_column(BigInteger)
    conversions: Mapped[Optional[int]] = mapped_column(BigInteger)
    conversion_value: Mapped[Optional[Decimal]] = mapped_column(Numeric)
    video_view_time: Mapped[Optional[int]] = mapped_column(BigInteger)
    frequency: Mapped[Optional[Decimal]] = mapped_column(Numeric)
    reach: Mapped[Optional[int]] = mapped_column(BigInteger)
    add_to_cart: Mapped[Optional[int]] = mapped_column(BigInteger) 


class FactShopifyDaily(Base): 
    __tablename__ = "fact_shopify_daily"

    fact_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    date_id: Mapped[int] = mapped_column(ForeignKey("dim_date.date_id"), nullable=False)
    country_id: Mapped[int] = mapped_column(ForeignKey("dim_country.country_id"), nullable=False)
    region_id: Mapped[int] = mapped_column(ForeignKey("dim_region.region_id"), nullable=False)
    city_id: Mapped[int] = mapped_column(ForeignKey("dim_city.city_id"), nullable=False)
    postal_id: Mapped[int] = mapped_column(ForeignKey("dim_postal.postal_id"), nullable=False)
    currency_code: Mapped[Optional[str]] = mapped_column(Text)
    sessions: Mapped[Optional[int]] = mapped_column(BigInteger)
    orders: Mapped[Optional[int]] = mapped_column(BigInteger)
    revenue: Mapped[Optional[Decimal]] = mapped_column(Numeric)
    add_to_cart: Mapped[Optional[int]] = mapped_column(BigInteger)


class FactModelResults(Base):           
    __tablename__ = "fact_model_results"

    model_run_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    model_name: Mapped[str] = mapped_column(Text, nullable=False)
    run_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, server_default=text("now()"))
    platform_id: Mapped[Optional[int]] = mapped_column(ForeignKey("dim_platform.platform_id"))
    dma_id: Mapped[Optional[int]] = mapped_column(ForeignKey("dim_dma.dma_id"))
    date_id: Mapped[Optional[int]] = mapped_column(ForeignKey("dim_date.date_id"))
    predicted_sales: Mapped[Optional[Decimal]] = mapped_column(Numeric)
    attributed_sales: Mapped[Optional[Decimal]] = mapped_column(Numeric)
    effect_size: Mapped[Optional[Decimal]] = mapped_column(Numeric)
    confidence_interval: Mapped[Optional[dict]] = mapped_column(JSONB)
    feature_importances: Mapped[Optional[dict]] = mapped_column(JSONB)
    model_version: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "model_name",
            "model_version",
            "platform_id",
            "dma_id",
            "date_id",
            name="ux_model_result",
        ),
        Index("ix_model_results_date", "date_id"),
        Index("ix_model_results_geo", "dma_id"),
    )


class StgShopifyDailyCity(Base):            
    __tablename__ = "stg_shopify_daily_city"

    date_id: Mapped[date] = mapped_column(Date, nullable=False)
    platform_id: Mapped[int] = mapped_column(
        ForeignKey("dim_platform.platform_id", deferrable=True, initially="DEFERRED"),
        nullable=False,
    )
    account_id: Mapped[int] = mapped_column(
        ForeignKey("dim_account.account_id", deferrable=True, initially="DEFERRED"),
        nullable=False,
    )
    country_iso2: Mapped[str] = mapped_column(Text, nullable=False)
    region_code: Mapped[str] = mapped_column(Text, nullable=False)
    city_name_norm: Mapped[str] = mapped_column(Text, nullable=False)
    country_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("dim_country.country_id", deferrable=True, initially="DEFERRED")
    )
    region_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("dim_region.region_id", deferrable=True, initially="DEFERRED")
    )
    city_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("dim_city.city_id", deferrable=True, initially="DEFERRED")
    )
    attribution_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("dim_attribution.attribution_id", deferrable=True, initially="DEFERRED")
    )
    orders: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4), server_default=text("0"))
    gross_sales: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4), server_default=text("0"))
    refunds: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4), server_default=text("0"))
    shipping: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4), server_default=text("0"))
    _ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), server_default=text("now()"))
    _source_file: Mapped[Optional[str]] = mapped_column(Text)

    __table_args__ = (
        PrimaryKeyConstraint(
            "date_id",
            "account_id",
            "country_iso2",
            "region_code",
            "city_name_norm",
            name="stg_shopify_daily_city_pk",
        ),
    )


class MapCityDMA(Base):
    __tablename__ = "map_city_dma"

    country_id: Mapped[int] = mapped_column(ForeignKey("dim_country.country_id"), nullable=False)
    region_id: Mapped[int] = mapped_column(ForeignKey("dim_region.region_id"), nullable=False)
    city_id: Mapped[int] = mapped_column(ForeignKey("dim_city.city_id"), nullable=False)
    dma_id: Mapped[int] = mapped_column(ForeignKey("dim_dma.dma_id"), nullable=False)
    effective_start_date: Mapped[date] = mapped_column(
        Date, nullable=False, server_default=text("'2000-01-01'::date")
    )     
    effective_end_date: Mapped[date] = mapped_column(
        Date, nullable=False, server_default=text("'2999-12-31'::date")
    )
    dma_share: Mapped[Decimal] = mapped_column(Numeric(6, 5), nullable=False, server_default=text("1.00000"))

    __table_args__ = (
        PrimaryKeyConstraint(
            "country_id",
            "region_id",
            "city_id",
            "dma_id",
            "effective_start_date",
            name="map_city_dma_pk",
        ),
        UniqueConstraint(
            "country_id",
            "region_id",
            "city_id",
            "effective_start_date",
            "effective_end_date",
            name="map_city_dma_city_window_unique",
        ),
    )


class MapPostalCityState(Base):
    __tablename__ = "map_postal_city_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    postal_code: Mapped[str] = mapped_column(Text, nullable=False)
    city_name: Mapped[str] = mapped_column(Text, nullable=False)
    state_code: Mapped[str] = mapped_column(Text, nullable=False)
    city_id: Mapped[Optional[int]] = mapped_column(ForeignKey("dim_city.city_id"))


class MetricAvailability(Base):
    __tablename__ = "metric_availability"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    platform_id: Mapped[int] = mapped_column(ForeignKey("dim_platform.platform_id"), nullable=False)
    location_level: Mapped[str] = mapped_column(Text, nullable=False)
    metric_name: Mapped[str] = mapped_column(Text, nullable=False)
    is_available: Mapped[bool] = mapped_column(Boolean, nullable=False)


class EventIngestionLog(Base):
    __tablename__ = "event_ingestion_log"

    log_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    platform_id: Mapped[Optional[int]] = mapped_column(ForeignKey("dim_platform.platform_id"))
    sync_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, server_default=text("now()")
    )
    records_fetched: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    duration_seconds: Mapped[Optional[Decimal]] = mapped_column(Numeric)
