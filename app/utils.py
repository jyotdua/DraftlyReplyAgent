from __future__ import annotations

import base64
import hashlib
import re
from datetime import datetime, timezone
from email.mime.text import MIMEText
from typing import Iterable


def make_idempotency_key(*parts: str) -> str:
    joined = "::".join(parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def encode_gmail_message(message: MIMEText) -> str:
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
    return raw.rstrip("=")


def html_to_text(value: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", value, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+\n", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def epoch_ms_to_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc)


def compact_style_samples(samples: Iterable[str]) -> str:
    cleaned = [sample.strip() for sample in samples if sample and sample.strip()]
    return "\n\n---\n\n".join(cleaned[:5])
