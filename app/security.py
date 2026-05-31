from __future__ import annotations

import json

from cryptography.fernet import Fernet

from app.config import get_settings


class SecretBox:
    def __init__(self) -> None:
        settings = get_settings()
        self._fernet = Fernet(settings.resolved_encryption_key)

    def encrypt_json(self, value: dict) -> str:
        encoded = json.dumps(value).encode("utf-8")
        return self._fernet.encrypt(encoded).decode("utf-8")

    def decrypt_json(self, value: str | None) -> dict:
        if not value:
            return {}
        decoded = self._fernet.decrypt(value.encode("utf-8"))
        return json.loads(decoded.decode("utf-8"))


secret_box = SecretBox()
