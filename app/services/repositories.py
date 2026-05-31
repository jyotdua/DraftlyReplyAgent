from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models import AuditLog, DraftStatus, EmailDraft, OAuthState, SendAttempt, SendStatus, UserAccount
from app.security import secret_box


def get_user_by_email(db: Session, email: str) -> UserAccount | None:
    return db.scalar(select(UserAccount).where(UserAccount.email == email))


def upsert_user_credentials(db: Session, email: str, credentials: dict) -> UserAccount:
    user = get_user_by_email(db, email)
    encrypted = secret_box.encrypt_json(credentials)
    if user:
        user.encrypted_credentials = encrypted
    else:
        user = UserAccount(email=email, encrypted_credentials=encrypted)
        db.add(user)
    db.flush()
    return user


def get_user_credentials(user: UserAccount) -> dict:
    return secret_box.decrypt_json(user.encrypted_credentials)


def save_preferences(db: Session, user: UserAccount, preferences: dict) -> UserAccount:
    user.encrypted_preferences = secret_box.encrypt_json(preferences)
    db.flush()
    return user


def get_preferences(user: UserAccount) -> dict:
    return secret_box.decrypt_json(user.encrypted_preferences)


def create_oauth_state(
    db: Session,
    state: str,
    redirect_uri: str,
    email_hint: str | None = None,
    user: UserAccount | None = None,
) -> OAuthState:
    oauth_state = OAuthState(
        state=state,
        redirect_uri=redirect_uri,
        user_email_hint=email_hint,
        user_id=user.id if user else None,
    )
    db.add(oauth_state)
    db.flush()
    return oauth_state


def consume_oauth_state(db: Session, state: str) -> OAuthState | None:
    oauth_state = db.scalar(select(OAuthState).where(OAuthState.state == state))
    if oauth_state:
        db.delete(oauth_state)
        db.flush()
    return oauth_state


def create_draft(
    db: Session,
    *,
    user: UserAccount,
    source_message_id: str,
    thread_id: str,
    reply_to_message_id: str,
    subject: str,
    tone: str,
    prompt_context: dict,
    generated_body: str,
    idempotency_key: str,
    metadata: dict,
) -> EmailDraft:
    draft = EmailDraft(
        user_id=user.id,
        source_message_id=source_message_id,
        thread_id=thread_id,
        reply_to_message_id=reply_to_message_id,
        subject=subject,
        tone=tone,
        prompt_context=prompt_context,
        generated_body=generated_body,
        idempotency_key=idempotency_key,
        draft_metadata=metadata,
    )
    db.add(draft)
    db.flush()
    return draft


def find_draft_by_id(db: Session, draft_id: int) -> EmailDraft | None:
    return db.scalar(select(EmailDraft).where(EmailDraft.id == draft_id))


def find_draft_by_idempotency_key(db: Session, key: str) -> EmailDraft | None:
    return db.scalar(select(EmailDraft).where(EmailDraft.idempotency_key == key))


def list_drafts_for_email(db: Session, email: str) -> list[EmailDraft]:
    stmt = (
        select(EmailDraft)
        .join(UserAccount, UserAccount.id == EmailDraft.user_id)
        .where(UserAccount.email == email)
        .order_by(desc(EmailDraft.created_at))
    )
    return list(db.scalars(stmt).all())


def update_draft_review_state(
    db: Session,
    draft: EmailDraft,
    *,
    action: str,
    edited_body: str | None = None,
    rejection_reason: str | None = None,
) -> EmailDraft:
    if action == "approve":
        draft.status = DraftStatus.approved.value
        draft.approved_at = datetime.now(timezone.utc)
    elif action == "edit":
        draft.status = DraftStatus.edited.value
        draft.edited_body = edited_body
    elif action == "reject":
        draft.status = DraftStatus.rejected.value
        draft.rejection_reason = rejection_reason
    db.flush()
    return draft


def create_send_attempt(db: Session, draft: EmailDraft, idempotency_key: str) -> SendAttempt:
    existing = db.scalar(select(SendAttempt).where(SendAttempt.idempotency_key == idempotency_key))
    if existing:
        return existing
    attempt_count = len(draft.send_attempts) + 1
    attempt = SendAttempt(
        draft_id=draft.id,
        attempt_number=attempt_count,
        idempotency_key=idempotency_key,
        status=SendStatus.pending.value,
    )
    db.add(attempt)
    db.flush()
    return attempt


def mark_send_attempt(
    db: Session,
    attempt: SendAttempt,
    *,
    status: str,
    error_message: str | None = None,
    gmail_message_id: str | None = None,
    gmail_thread_id: str | None = None,
) -> SendAttempt:
    attempt.status = status
    attempt.error_message = error_message
    attempt.gmail_message_id = gmail_message_id
    attempt.gmail_thread_id = gmail_thread_id
    db.flush()
    return attempt


def mark_draft_sent(
    db: Session,
    draft: EmailDraft,
    *,
    gmail_message_id: str,
    gmail_thread_id: str,
) -> EmailDraft:
    draft.status = DraftStatus.sent.value
    draft.gmail_sent_message_id = gmail_message_id
    draft.gmail_sent_thread_id = gmail_thread_id
    draft.sent_at = datetime.now(timezone.utc)
    db.flush()
    return draft


def mark_draft_sending(db: Session, draft: EmailDraft) -> EmailDraft:
    draft.status = DraftStatus.sending.value
    db.flush()
    return draft


def mark_draft_failed(db: Session, draft: EmailDraft) -> EmailDraft:
    draft.status = DraftStatus.failed.value
    db.flush()
    return draft


def add_audit_log(db: Session, event_type: str, message: str, payload: dict | None = None, user_id: int | None = None) -> AuditLog:
    log = AuditLog(user_id=user_id, event_type=event_type, message=message, payload=payload)
    db.add(log)
    db.flush()
    return log


def list_logs(db: Session, limit: int = 100) -> list[AuditLog]:
    stmt = select(AuditLog).order_by(desc(AuditLog.created_at)).limit(limit)
    return list(db.scalars(stmt).all())
