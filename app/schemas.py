from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field


class HealthResponse(BaseModel):
    status: str
    environment: str


class AuthUrlResponse(BaseModel):
    auth_url: str
    state: str


class AuthStatusResponse(BaseModel):
    connected: bool
    email: EmailStr | None = None


class PreferencesPayload(BaseModel):
    signature: str | None = None
    preferred_tone: str = "professional"
    extra_instructions: str | None = None


class EmailSummary(BaseModel):
    id: str
    thread_id: str
    subject: str
    from_: str = Field(alias="from")
    snippet: str
    internal_date: datetime | None = None
    unread: bool = False

    model_config = {"populate_by_name": True}


class EmailThreadMessage(BaseModel):
    id: str
    thread_id: str
    subject: str
    from_: str = Field(alias="from")
    to: str | None = None
    body: str
    snippet: str
    message_id_header: str | None = None
    references_header: str | None = None
    internal_date: datetime | None = None

    model_config = {"populate_by_name": True}


class EmailThreadResponse(BaseModel):
    thread_id: str
    messages: list[EmailThreadMessage]


class GenerateDraftRequest(BaseModel):
    email: EmailStr
    source_message_id: str
    tone: str = "professional"
    signature: str | None = None
    additional_instructions: str | None = None
    idempotency_key: str | None = None


class DraftResponse(BaseModel):
    id: int
    email: EmailStr
    source_message_id: str
    thread_id: str
    subject: str
    tone: str
    generated_body: str
    edited_body: str | None
    status: str
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    approved_at: datetime | None = None
    sent_at: datetime | None = None


class ReviewDraftRequest(BaseModel):
    action: Literal["approve", "edit", "reject"]
    edited_body: str | None = None
    rejection_reason: str | None = None


class SendDraftRequest(BaseModel):
    email: EmailStr
    idempotency_key: str


class SendDraftResponse(BaseModel):
    draft_id: int
    status: str
    gmail_message_id: str | None = None
    gmail_thread_id: str | None = None


class AuditLogResponse(BaseModel):
    event_type: str
    message: str
    payload: dict[str, Any] | None = None
    created_at: datetime
