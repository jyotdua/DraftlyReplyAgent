from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import get_settings
from app.models import DraftStatus, EmailDraft, SendStatus, UserAccount
from app.services.gemini_service import gemini_service
from app.services.gmail_service import gmail_service
from app.services.repositories import (
    add_audit_log,
    create_draft,
    create_send_attempt,
    find_draft_by_idempotency_key,
    get_preferences,
    list_drafts_for_email,
    mark_draft_failed,
    mark_draft_sent,
    mark_draft_sending,
    mark_send_attempt,
)
from app.utils import compact_style_samples, make_idempotency_key


class DraftWorkflowService:
    def __init__(self) -> None:
        self.settings = get_settings()

    def generate_draft(
        self,
        db: Session,
        *,
        user: UserAccount,
        source_message_id: str,
        tone: str,
        signature: str | None,
        additional_instructions: str | None,
        idempotency_key: str | None,
    ) -> EmailDraft:
        draft_key = idempotency_key or make_idempotency_key(user.email, source_message_id, tone)
        existing = find_draft_by_idempotency_key(db, draft_key)
        if existing:
            return existing

        credentials = self._user_credentials(user)
        source_message = gmail_service.get_message(credentials, source_message_id, format_type="full")
        thread = gmail_service.get_thread(credentials, source_message["thread_id"])
        preferences = get_preferences(user)
        style_samples = gmail_service.get_recent_sent_messages(
            credentials, self.settings.recent_sent_style_sample_count
        )
        effective_signature = signature or preferences.get("signature")
        effective_instructions = additional_instructions or preferences.get("extra_instructions")
        body = gemini_service.generate_reply(
            tone=tone or preferences.get("preferred_tone", "professional"),
            signature=effective_signature,
            extra_instructions=effective_instructions,
            thread_summary=self._thread_summary(thread),
            latest_message=source_message["body"] or source_message["snippet"],
            style_samples=compact_style_samples(style_samples),
        )
        draft = create_draft(
            db,
            user=user,
            source_message_id=source_message["id"],
            thread_id=source_message["thread_id"],
            reply_to_message_id=source_message["message_id_header"] or source_message["id"],
            subject=self._reply_subject(source_message["subject"]),
            tone=tone or preferences.get("preferred_tone", "professional"),
            prompt_context={
                "additional_instructions": effective_instructions,
                "style_samples_used": len(style_samples),
            },
            generated_body=body,
            idempotency_key=draft_key,
            metadata={
                "source_from": source_message["from"],
                "source_to": source_message.get("to"),
                "source_snippet": source_message["snippet"],
                "style_learning_enabled": bool(style_samples),
                "signature_applied": bool(effective_signature),
            },
        )
        recipient = self._extract_reply_recipient(source_message["from"])
        gmail_draft = gmail_service.create_gmail_draft(
            credentials,
            to=recipient,
            subject=draft.subject,
            body=draft.generated_body,
            thread_id=draft.thread_id,
            message_id_header=source_message["message_id_header"],
            references_header=source_message["references_header"],
        )
        draft.gmail_draft_id = gmail_draft.get("id")
        add_audit_log(
            db,
            event_type="draft.generated",
            message="AI reply draft generated.",
            payload={"draft_id": draft.id, "gmail_draft_id": draft.gmail_draft_id},
            user_id=user.id,
        )
        db.flush()
        return draft

    def send_draft(self, db: Session, *, user: UserAccount, draft: EmailDraft, idempotency_key: str) -> dict[str, Any]:
        if draft.status not in {DraftStatus.approved.value, DraftStatus.edited.value, DraftStatus.sent.value}:
            raise ValueError("Only approved or edited drafts can be sent.")
        if draft.status == DraftStatus.sent.value and draft.gmail_sent_message_id:
            return {
                "draft_id": draft.id,
                "status": draft.status,
                "gmail_message_id": draft.gmail_sent_message_id,
                "gmail_thread_id": draft.gmail_sent_thread_id,
            }

        attempt = create_send_attempt(db, draft, idempotency_key)
        if attempt.status == SendStatus.sent.value:
            return {
                "draft_id": draft.id,
                "status": draft.status,
                "gmail_message_id": attempt.gmail_message_id,
                "gmail_thread_id": attempt.gmail_thread_id,
            }

        recipient = draft.draft_metadata.get("source_from", "")
        credentials = self._user_credentials(user)
        source_message = gmail_service.get_message(credentials, draft.source_message_id, format_type="full")
        body = draft.edited_body or draft.generated_body
        mark_draft_sending(db, draft)
        try:
            result = self._send_with_retry(
                credentials=credentials,
                to=self._extract_reply_recipient(recipient),
                subject=draft.subject,
                body=body,
                thread_id=draft.thread_id,
                message_id_header=source_message["message_id_header"],
                references_header=source_message["references_header"],
            )
        except Exception as exc:
            mark_send_attempt(db, attempt, status=SendStatus.failed.value, error_message=str(exc))
            mark_draft_failed(db, draft)
            add_audit_log(
                db,
                event_type="draft.send_failed",
                message="Approved draft failed to send.",
                payload={"draft_id": draft.id, "error": str(exc)},
                user_id=user.id,
            )
            raise

        mark_send_attempt(
            db,
            attempt,
            status=SendStatus.sent.value,
            gmail_message_id=result.get("id"),
            gmail_thread_id=result.get("threadId"),
        )
        mark_draft_sent(
            db,
            draft,
            gmail_message_id=result.get("id"),
            gmail_thread_id=result.get("threadId"),
        )
        add_audit_log(
            db,
            event_type="draft.sent",
            message="Approved draft sent through Gmail.",
            payload={"draft_id": draft.id, "gmail_message_id": result.get("id")},
            user_id=user.id,
        )
        return {
            "draft_id": draft.id,
            "status": draft.status,
            "gmail_message_id": result.get("id"),
            "gmail_thread_id": result.get("threadId"),
        }

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    def _send_with_retry(
        self,
        *,
        credentials: dict,
        to: str,
        subject: str,
        body: str,
        thread_id: str,
        message_id_header: str | None,
        references_header: str | None,
    ) -> dict:
        return gmail_service.send_message(
            credentials,
            to=to,
            subject=subject,
            body=body,
            thread_id=thread_id,
            message_id_header=message_id_header,
            references_header=references_header,
        )

    def _thread_summary(self, thread: dict[str, Any]) -> str:
        chunks = []
        for message in thread["messages"][-6:]:
            chunks.append(
                f"From: {message['from']}\nTo: {message.get('to') or ''}\nBody:\n{message['body'] or message['snippet']}"
            )
        return "\n\n---\n\n".join(chunks)

    def _extract_reply_recipient(self, header_value: str) -> str:
        if "<" in header_value and ">" in header_value:
            return header_value.split("<", maxsplit=1)[1].split(">", maxsplit=1)[0].strip()
        return header_value.strip()

    def _reply_subject(self, subject: str) -> str:
        return subject if subject.lower().startswith("re:") else f"Re: {subject}"

    def _user_credentials(self, user: UserAccount) -> dict:
        from app.services.repositories import get_user_credentials

        return get_user_credentials(user)


draft_workflow_service = DraftWorkflowService()
