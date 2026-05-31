from __future__ import annotations

import base64
from email.mime.text import MIMEText
from typing import Any

import httpx
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

from app.config import get_settings
from app.utils import encode_gmail_message, epoch_ms_to_datetime, html_to_text


class GmailService:
    def __init__(self) -> None:
        self.settings = get_settings()

    def create_flow(self, state: str) -> Flow:
        flow = Flow.from_client_secrets_file(
            str(self.settings.resolved_oauth_client_path),
            scopes=list(self.settings.gmail_scopes),
            state=state,
        )
        flow.redirect_uri = self.settings.google_redirect_uri
        return flow

    def authorization_url(self, state: str) -> tuple[str, str]:
        flow = self.create_flow(state)
        auth_url, resolved_state = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
        )
        return auth_url, resolved_state

    def exchange_code(self, state: str, code: str) -> dict:
        flow = self.create_flow(state)
        flow.fetch_token(code=code)
        creds = flow.credentials
        return {
            "token": creds.token,
            "refresh_token": creds.refresh_token,
            "token_uri": creds.token_uri,
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
            "scopes": creds.scopes,
        }

    def credentials_from_dict(self, value: dict) -> Credentials:
        credentials = Credentials.from_authorized_user_info(value, scopes=value.get("scopes"))
        if credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
        return credentials

    def build_client(self, credentials_dict: dict):
        credentials = self.credentials_from_dict(credentials_dict)
        return build("gmail", "v1", credentials=credentials)

    def get_profile(self, credentials_dict: dict) -> dict:
        service = self.build_client(credentials_dict)
        return service.users().getProfile(userId="me").execute()

    def revoke_credentials(self, credentials_dict: dict) -> None:
        token = credentials_dict.get("refresh_token") or credentials_dict.get("token")
        if not token:
            return
        httpx.post(
            "https://oauth2.googleapis.com/revoke",
            params={"token": token},
            headers={"content-type": "application/x-www-form-urlencoded"},
            timeout=10.0,
        )

    def list_messages(self, credentials_dict: dict, query: str, limit: int) -> list[dict[str, Any]]:
        service = self.build_client(credentials_dict)
        response = (
            service.users()
            .messages()
            .list(userId="me", q=query, maxResults=limit)
            .execute()
        )
        messages = response.get("messages", [])
        return [self.get_message(credentials_dict, item["id"], format_type="metadata") for item in messages]

    def get_message(self, credentials_dict: dict, message_id: str, format_type: str = "full") -> dict[str, Any]:
        service = self.build_client(credentials_dict)
        message = (
            service.users()
            .messages()
            .get(
                userId="me",
                id=message_id,
                format=format_type,
                metadataHeaders=["Subject", "From", "To", "Message-ID", "References", "In-Reply-To"],
            )
            .execute()
        )
        return self._normalize_message(message)

    def get_thread(self, credentials_dict: dict, thread_id: str) -> dict[str, Any]:
        service = self.build_client(credentials_dict)
        thread = service.users().threads().get(userId="me", id=thread_id, format="full").execute()
        messages = [self._normalize_message(message) for message in thread.get("messages", [])]
        return {"thread_id": thread["id"], "messages": messages}

    def get_recent_sent_messages(self, credentials_dict: dict, limit: int) -> list[str]:
        service = self.build_client(credentials_dict)
        response = service.users().messages().list(userId="me", q="in:sent newer_than:180d", maxResults=limit).execute()
        samples: list[str] = []
        for message in response.get("messages", []):
            payload = (
                service.users()
                .messages()
                .get(userId="me", id=message["id"], format="full")
                .execute()
            )
            normalized = self._normalize_message(payload)
            body = normalized.get("body", "").strip()
            if body:
                samples.append(body[:1500])
        return samples

    def create_gmail_draft(
        self,
        credentials_dict: dict,
        *,
        to: str,
        subject: str,
        body: str,
        thread_id: str,
        message_id_header: str | None,
        references_header: str | None,
    ) -> dict:
        service = self.build_client(credentials_dict)
        mime = self._build_mime_message(
            to=to,
            subject=subject,
            body=body,
            message_id_header=message_id_header,
            references_header=references_header,
        )
        return (
            service.users()
            .drafts()
            .create(
                userId="me",
                body={"message": {"raw": encode_gmail_message(mime), "threadId": thread_id}},
            )
            .execute()
        )

    def send_message(
        self,
        credentials_dict: dict,
        *,
        to: str,
        subject: str,
        body: str,
        thread_id: str,
        message_id_header: str | None,
        references_header: str | None,
    ) -> dict:
        service = self.build_client(credentials_dict)
        mime = self._build_mime_message(
            to=to,
            subject=subject,
            body=body,
            message_id_header=message_id_header,
            references_header=references_header,
        )
        payload = {"raw": encode_gmail_message(mime), "threadId": thread_id}
        return service.users().messages().send(userId="me", body=payload).execute()

    def _build_mime_message(
        self,
        *,
        to: str,
        subject: str,
        body: str,
        message_id_header: str | None,
        references_header: str | None,
    ) -> MIMEText:
        mime = MIMEText(body)
        mime["To"] = to
        mime["Subject"] = subject
        if message_id_header:
            mime["In-Reply-To"] = message_id_header
        references = " ".join(part for part in [references_header, message_id_header] if part)
        if references:
            mime["References"] = references
        return mime

    def _normalize_message(self, message: dict[str, Any]) -> dict[str, Any]:
        payload = message.get("payload", {})
        headers = {item["name"].lower(): item["value"] for item in payload.get("headers", [])}
        return {
            "id": message["id"],
            "thread_id": message.get("threadId"),
            "subject": headers.get("subject", "(No subject)"),
            "from": headers.get("from", ""),
            "to": headers.get("to"),
            "snippet": message.get("snippet", ""),
            "body": self._extract_body(payload),
            "message_id_header": headers.get("message-id"),
            "references_header": headers.get("references"),
            "internal_date": epoch_ms_to_datetime(message.get("internalDate")),
            "unread": "UNREAD" in message.get("labelIds", []),
        }

    def _extract_body(self, payload: dict[str, Any]) -> str:
        body_data = payload.get("body", {}).get("data")
        mime_type = payload.get("mimeType", "")
        if body_data:
            decoded = base64.urlsafe_b64decode(body_data + "===")
            text = decoded.decode("utf-8", errors="ignore")
            return html_to_text(text) if "text/html" in mime_type else text.strip()

        for part in payload.get("parts", []) or []:
            text = self._extract_body(part)
            if text:
                return text
        return ""


gmail_service = GmailService()
