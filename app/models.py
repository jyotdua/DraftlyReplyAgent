from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class DraftStatus(str, Enum):
    generated = "generated"
    edited = "edited"
    approved = "approved"
    rejected = "rejected"
    sending = "sending"
    sent = "sent"
    failed = "failed"


class SendStatus(str, Enum):
    pending = "pending"
    retrying = "retrying"
    sent = "sent"
    failed = "failed"


class UserAccount(Base):
    __tablename__ = "user_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    encrypted_credentials: Mapped[str] = mapped_column(Text)
    encrypted_preferences: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    drafts: Mapped[list["EmailDraft"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    oauth_states: Mapped[list["OAuthState"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class OAuthState(Base):
    __tablename__ = "oauth_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    state: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    redirect_uri: Mapped[str] = mapped_column(String(2048))
    user_email_hint: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("user_accounts.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[Optional["UserAccount"]] = relationship(back_populates="oauth_states")


class EmailDraft(Base):
    __tablename__ = "email_drafts"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_email_draft_idempotency"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    source_message_id: Mapped[str] = mapped_column(String(255), index=True)
    thread_id: Mapped[str] = mapped_column(String(255), index=True)
    reply_to_message_id: Mapped[str] = mapped_column(String(255))
    subject: Mapped[str] = mapped_column(String(998))
    tone: Mapped[str] = mapped_column(String(80), default="professional")
    prompt_context: Mapped[dict] = mapped_column(JSON)
    generated_body: Mapped[str] = mapped_column(Text)
    edited_body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default=DraftStatus.generated.value)
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(255))
    gmail_draft_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    gmail_sent_message_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    gmail_sent_thread_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    draft_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[UserAccount] = relationship(back_populates="drafts")
    send_attempts: Mapped[list["SendAttempt"]] = relationship(
        back_populates="draft", cascade="all, delete-orphan"
    )


class SendAttempt(Base):
    __tablename__ = "send_attempts"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_send_attempt_idempotency"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    draft_id: Mapped[int] = mapped_column(ForeignKey("email_drafts.id"), index=True)
    attempt_number: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(32), default=SendStatus.pending.value)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    gmail_message_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    gmail_thread_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    draft: Mapped[EmailDraft] = relationship(back_populates="send_attempts")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("user_accounts.id"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    message: Mapped[str] = mapped_column(Text)
    payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
