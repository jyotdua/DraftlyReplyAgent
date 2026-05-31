from __future__ import annotations

from contextlib import asynccontextmanager
import secrets

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import Base, engine, get_db
from app.models import DraftStatus
from app.schemas import (
    AuditLogResponse,
    AuthStatusResponse,
    AuthUrlResponse,
    DraftResponse,
    EmailSummary,
    EmailThreadResponse,
    GenerateDraftRequest,
    HealthResponse,
    PreferencesPayload,
    ReviewDraftRequest,
    SendDraftRequest,
    SendDraftResponse,
)
from app.services.draft_service import draft_workflow_service
from app.services.gmail_service import gmail_service
from app.services.repositories import (
    add_audit_log,
    consume_oauth_state,
    create_oauth_state,
    find_draft_by_id,
    get_preferences,
    get_user_by_email,
    list_drafts_for_email,
    list_logs,
    save_preferences,
    update_draft_review_state,
    upsert_user_credentials,
)

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def to_draft_response(draft, email: str) -> DraftResponse:
    return DraftResponse(
        id=draft.id,
        email=email,
        source_message_id=draft.source_message_id,
        thread_id=draft.thread_id,
        subject=draft.subject,
        tone=draft.tone,
        generated_body=draft.generated_body,
        edited_body=draft.edited_body,
        status=draft.status,
        metadata=draft.draft_metadata,
        created_at=draft.created_at,
        updated_at=draft.updated_at,
        approved_at=draft.approved_at,
        sent_at=draft.sent_at,
    )


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", environment=settings.app_env)


@app.get("/api/auth/google/start", response_model=AuthUrlResponse)
def start_google_auth(email_hint: str | None = None, db: Session = Depends(get_db)) -> AuthUrlResponse:
    requested_state = secrets.token_urlsafe(24)
    auth_url, state = gmail_service.authorization_url(requested_state)
    user = get_user_by_email(db, email_hint) if email_hint else None
    create_oauth_state(db, state=state, redirect_uri=settings.google_redirect_uri, email_hint=email_hint, user=user)
    db.commit()
    return AuthUrlResponse(auth_url=auth_url, state=state)


@app.get("/api/auth/google/callback")
def google_auth_callback(state: str, code: str, db: Session = Depends(get_db)) -> dict:
    oauth_state = consume_oauth_state(db, state)
    if not oauth_state:
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state.")
    credentials = gmail_service.exchange_code(state, code)
    profile = gmail_service.get_profile(credentials)
    user = upsert_user_credentials(db, profile["emailAddress"], credentials)
    add_audit_log(
        db,
        event_type="auth.connected",
        message="Google account connected.",
        payload={"email": user.email},
        user_id=user.id,
    )
    db.commit()
    return {"connected": True, "email": user.email}


@app.get("/api/auth/status", response_model=AuthStatusResponse)
def auth_status(email: str = Query(...), db: Session = Depends(get_db)) -> AuthStatusResponse:
    user = get_user_by_email(db, email)
    return AuthStatusResponse(connected=bool(user), email=user.email if user else None)


@app.post("/api/auth/logout")
def logout(email: str, db: Session = Depends(get_db)) -> dict:
    user = get_user_by_email(db, email)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    from app.services.repositories import get_user_credentials

    gmail_service.revoke_credentials(get_user_credentials(user))
    db.delete(user)
    add_audit_log(db, event_type="auth.disconnected", message="Google account disconnected.", payload={"email": email})
    db.commit()
    return {"ok": True}


@app.get("/api/preferences")
def get_user_preferences(email: str = Query(...), db: Session = Depends(get_db)) -> dict:
    user = get_user_by_email(db, email)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    return get_preferences(user)


@app.put("/api/preferences")
def update_preferences(email: str, payload: PreferencesPayload, db: Session = Depends(get_db)) -> dict:
    user = get_user_by_email(db, email)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    save_preferences(db, user, payload.model_dump())
    add_audit_log(
        db,
        event_type="preferences.updated",
        message="User preferences updated.",
        payload={"email": email},
        user_id=user.id,
    )
    db.commit()
    return payload.model_dump()


@app.get("/api/emails", response_model=list[EmailSummary])
def list_emails(
    email: str = Query(...),
    query: str | None = None,
    limit: int | None = None,
    db: Session = Depends(get_db),
) -> list[EmailSummary]:
    user = get_user_by_email(db, email)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    from app.services.repositories import get_user_credentials

    messages = gmail_service.list_messages(
        get_user_credentials(user),
        query or settings.gmail_query,
        limit or settings.gmail_fetch_limit,
    )
    return [EmailSummary.model_validate(message) for message in messages]


@app.get("/api/threads/{thread_id}", response_model=EmailThreadResponse)
def get_thread(thread_id: str, email: str = Query(...), db: Session = Depends(get_db)) -> EmailThreadResponse:
    user = get_user_by_email(db, email)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    from app.services.repositories import get_user_credentials

    thread = gmail_service.get_thread(get_user_credentials(user), thread_id)
    return EmailThreadResponse.model_validate(thread)


@app.post("/api/drafts/generate", response_model=DraftResponse)
def generate_draft(payload: GenerateDraftRequest, db: Session = Depends(get_db)) -> DraftResponse:
    user = get_user_by_email(db, payload.email)
    if not user:
        raise HTTPException(status_code=404, detail="User not found. Connect Gmail first.")
    draft = draft_workflow_service.generate_draft(
        db,
        user=user,
        source_message_id=payload.source_message_id,
        tone=payload.tone,
        signature=payload.signature,
        additional_instructions=payload.additional_instructions,
        idempotency_key=payload.idempotency_key,
    )
    db.commit()
    db.refresh(draft)
    return to_draft_response(draft, user.email)


@app.get("/api/drafts", response_model=list[DraftResponse])
def list_drafts(email: str = Query(...), db: Session = Depends(get_db)) -> list[DraftResponse]:
    drafts = list_drafts_for_email(db, email)
    return [to_draft_response(draft, email) for draft in drafts]


@app.get("/api/drafts/{draft_id}", response_model=DraftResponse)
def get_draft(draft_id: int, db: Session = Depends(get_db)) -> DraftResponse:
    draft = find_draft_by_id(db, draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found.")
    return to_draft_response(draft, draft.user.email)


@app.post("/api/drafts/{draft_id}/review", response_model=DraftResponse)
def review_draft(draft_id: int, payload: ReviewDraftRequest, db: Session = Depends(get_db)) -> DraftResponse:
    draft = find_draft_by_id(db, draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found.")
    if payload.action == "edit" and not payload.edited_body:
        raise HTTPException(status_code=400, detail="edited_body is required for edit action.")
    if payload.action == "reject" and not payload.rejection_reason:
        raise HTTPException(status_code=400, detail="rejection_reason is required for reject action.")

    draft = update_draft_review_state(
        db,
        draft,
        action=payload.action,
        edited_body=payload.edited_body,
        rejection_reason=payload.rejection_reason,
    )
    add_audit_log(
        db,
        event_type=f"draft.{payload.action}d",
        message=f"Draft {payload.action}d by user.",
        payload={"draft_id": draft.id},
        user_id=draft.user_id,
    )
    db.commit()
    return to_draft_response(draft, draft.user.email)


@app.post("/api/drafts/{draft_id}/send", response_model=SendDraftResponse)
def send_draft(draft_id: int, payload: SendDraftRequest, db: Session = Depends(get_db)) -> SendDraftResponse:
    draft = find_draft_by_id(db, draft_id)
    if not draft or draft.user.email != payload.email:
        raise HTTPException(status_code=404, detail="Draft not found.")
    if draft.status == DraftStatus.rejected.value:
        raise HTTPException(status_code=400, detail="Rejected drafts cannot be sent.")

    try:
        result = draft_workflow_service.send_draft(
            db,
            user=draft.user,
            draft=draft,
            idempotency_key=payload.idempotency_key,
        )
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        db.commit()
        raise HTTPException(status_code=502, detail=f"Send failed after retries: {exc}") from exc

    db.commit()
    return SendDraftResponse.model_validate(result)


@app.get("/api/logs", response_model=list[AuditLogResponse])
def get_logs(limit: int = 100, db: Session = Depends(get_db)) -> list[AuditLogResponse]:
    return [AuditLogResponse.model_validate(log) for log in list_logs(db, limit=limit)]
