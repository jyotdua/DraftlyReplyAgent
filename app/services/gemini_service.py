from __future__ import annotations

from google import genai
from google.genai import types

from app.config import get_settings


class GeminiDraftService:
    def __init__(self) -> None:
        self.model = "gemini-2.5-flash"
        self._client: genai.Client | None = None

    @property
    def client(self) -> genai.Client:
        if self._client is None:
            settings = get_settings()
            if not settings.google_gemini_api_key:
                raise RuntimeError("GOOGLE_GEMINI_API_KEY is not configured.")
            self._client = genai.Client(api_key=settings.google_gemini_api_key)
        return self._client

    def generate_reply(
        self,
        *,
        tone: str,
        signature: str | None,
        extra_instructions: str | None,
        thread_summary: str,
        latest_message: str,
        style_samples: str,
    ) -> str:
        prompt = f"""
You are Draftly, an email reply assistant.

Write a reply email based on:
- requested tone: {tone}
- latest inbound email:
{latest_message}

- thread context:
{thread_summary}

- style samples from recent sent emails:
{style_samples or "No prior style samples available."}

- extra instructions:
{extra_instructions or "None"}

Requirements:
1. Keep the response ready to send.
2. Match the user's likely style without copying exact phrases.
3. Be clear, concise, and helpful.
4. Do not invent facts not present in the thread.
5. Do not include a subject line.
6. End with the user's signature if provided.
"""
        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction="You generate polished email replies for Gmail users.",
                temperature=0.7,
            ),
        )
        body = (response.text or "").strip()
        if signature and signature not in body:
            body = f"{body}\n\n{signature}".strip()
        return body


gemini_service = GeminiDraftService()
