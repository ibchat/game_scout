"""
Intel Database Models
All Intel-related tables isolated from main domain models.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional
from enum import Enum

import sqlalchemy as sa
from sqlalchemy import (
    JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text,
    UniqueConstraint, Index, BigInteger
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.db.base import Base, TimestampMixin


# ========================================
# ENUM CLASSES
# ========================================

class IntelSourceType(str, Enum):
    """Type of Intel source"""
    rss = "rss"
    steam = "steam"
    reddit_rss = "reddit_rss"


class IntelEventType(str, Enum):
    """Type of Intel event"""
    release = "release"
    early_access = "early_access"
    patch_major = "patch_major"
    discount = "discount"
    review_spike = "review_spike"
    influencer_spike = "influencer_spike"
    controversy = "controversy"
    publisher_deal = "publisher_deal"
    funding = "funding"
    market_trend = "market_trend"
    other = "other"


class IntelEventStatus(str, Enum):
    """Status of Intel event"""
    new = "new"
    ready = "ready"
    published = "published"
    ignored = "ignored"
    needs_review = "needs_review"


# ========================================
# MODELS
# ========================================

class IntelSource(Base, TimestampMixin):
    """Intel source configuration"""
    __tablename__ = "intel_sources"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa.text('gen_random_uuid()')
    )
    type: Mapped[str] = mapped_column(String(50), nullable=False)  # IntelSourceType
    name: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    language_hint: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    # Relationships
    raw_items: Mapped[list["IntelRawItem"]] = relationship(
        "IntelRawItem", back_populates="source", cascade="all, delete-orphan"
    )


class IntelRawItem(Base):
    """Raw items collected from sources"""
    __tablename__ = "intel_raw_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa.text('gen_random_uuid()')
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("intel_sources.id", ondelete="CASCADE"),
        nullable=False
    )
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sa.text('now()')
    )
    url: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    snippet: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    raw_payload: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    raw_html: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    source: Mapped["IntelSource"] = relationship("IntelSource", back_populates="raw_items")
    extracted_item: Mapped[Optional["IntelExtractedItem"]] = relationship(
        "IntelExtractedItem", back_populates="raw_item", uselist=False
    )

    __table_args__ = (
        Index("idx_intel_raw_items_url", "url"),
        Index("idx_intel_raw_items_source_id", "source_id"),
        Index("idx_intel_raw_items_fetched_at", "fetched_at"),
    )


class IntelExtractedItem(Base):
    """Extracted and normalized items"""
    __tablename__ = "intel_extracted_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa.text('gen_random_uuid()')
    )
    raw_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("intel_raw_items.id", ondelete="CASCADE"),
        nullable=False,
        unique=True
    )
    published_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    lang: Mapped[str] = mapped_column(String(10), nullable=False)
    title_norm: Mapped[str] = mapped_column(Text, nullable=False)
    url_norm: Mapped[str] = mapped_column(Text, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    meta: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Relationships
    raw_item: Mapped["IntelRawItem"] = relationship("IntelRawItem", back_populates="extracted_item")
    entities: Mapped[list["IntelEntity"]] = relationship(
        "IntelEntity", back_populates="extracted_item", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_intel_extracted_items_url_norm", "url_norm"),
        Index("idx_intel_extracted_items_raw_item_id", "raw_item_id"),
    )


class IntelCluster(Base):
    """Clusters of duplicate/similar items"""
    __tablename__ = "intel_clusters"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa.text('gen_random_uuid()')
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sa.text('now()')
    )
    representative_extracted_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("intel_extracted_items.id", ondelete="CASCADE"),
        nullable=False
    )
    member_extracted_ids: Mapped[list[uuid.UUID]] = mapped_column(
        JSONB,
        nullable=False,
        server_default="[]"
    )

    # Relationships
    events: Mapped[list["IntelEvent"]] = relationship(
        "IntelEvent", back_populates="cluster", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_intel_clusters_representative", "representative_extracted_id"),
        Index("idx_intel_clusters_created_at", "created_at"),
    )


class IntelEntity(Base):
    """Resolved entities (steam_appid mappings)"""
    __tablename__ = "intel_entities"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa.text('gen_random_uuid()')
    )
    extracted_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("intel_extracted_items.id", ondelete="CASCADE"),
        nullable=False
    )
    steam_appid: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    canonical_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    method: Mapped[str] = mapped_column(Text, nullable=False)  # e.g., "fuzzy", "steam_source"
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sa.text('now()')
    )

    # Relationships
    extracted_item: Mapped["IntelExtractedItem"] = relationship(
        "IntelExtractedItem", back_populates="entities"
    )

    __table_args__ = (
        Index("idx_intel_entities_extracted_id", "extracted_id"),
        Index("idx_intel_entities_steam_appid", "steam_appid"),
        Index("idx_intel_entities_confidence", "confidence"),
    )


class IntelEvent(Base, TimestampMixin):
    """Intel events (processed and ready for publication)"""
    __tablename__ = "intel_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa.text('gen_random_uuid()')
    )
    cluster_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("intel_clusters.id", ondelete="SET NULL"),
        nullable=True
    )
    steam_appid: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)  # IntelEventType
    score: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    status: Mapped[str] = mapped_column(String(50), nullable=False, server_default="new")  # IntelEventStatus

    # Russian content fields
    title_ru: Mapped[str] = mapped_column(Text, nullable=False)
    what_happened_ru: Mapped[str] = mapped_column(Text, nullable=False)
    why_it_matters_ru: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    facts_ru: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    risks_ru: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    tags: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    sources: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)

    # LLM and policy metadata
    llm_meta: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    policy_decision: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    policy_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Publication tracking
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    telegram_message_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Business brief fields
    business_brief_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    business_brief_generated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Publish status and channel
    publish_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, server_default="draft")  # draft/published/failed
    publish_channel: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # public/premium
    is_premium: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")

    # Relationships
    cluster: Mapped[Optional["IntelCluster"]] = relationship("IntelCluster", back_populates="events")
    publish_logs: Mapped[list["IntelPublishLog"]] = relationship(
        "IntelPublishLog", back_populates="event", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_intel_events_status_created_at", "status", "created_at"),
        Index("idx_intel_events_steam_appid", "steam_appid"),
        Index("idx_intel_events_score", "score"),
        Index("idx_intel_events_event_type", "event_type"),
        Index("idx_intel_events_cluster_id", "cluster_id"),
        Index("idx_intel_events_publish_status", "publish_status"),
        Index("idx_intel_events_is_premium", "is_premium"),
    )


class IntelPublishLog(Base):
    """Log of published events"""
    __tablename__ = "intel_publish_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa.text('gen_random_uuid()')
    )
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("intel_events.id", ondelete="CASCADE"),
        nullable=False
    )
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sa.text('now()')
    )
    channel_id: Mapped[str] = mapped_column(Text, nullable=False)
    telegram_message_id: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Relationships
    event: Mapped["IntelEvent"] = relationship("IntelEvent", back_populates="publish_logs")

    __table_args__ = (
        Index("idx_intel_publish_log_event_id", "event_id"),
        Index("idx_intel_publish_log_published_at", "published_at"),
    )


class IntelAuditLog(Base):
    """Audit log for policy checks"""
    __tablename__ = "intel_audit_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa.text('gen_random_uuid()')
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sa.text('now()')
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)  # ok, warning, error
    details: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        Index("idx_intel_audit_log_created_at", "created_at"),
        Index("idx_intel_audit_log_status", "status"),
    )
