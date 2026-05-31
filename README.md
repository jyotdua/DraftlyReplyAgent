# Draftly Reply Agent

Draftly Reply Agent is a backend-first AI email assistant that connects to Gmail, reads email and thread context, generates reply drafts with Google Gemini, stores draft workflow state in SQLite, and only sends replies after explicit user approval.

The project was built as a FastAPI service with a modular design so it can later support a frontend dashboard, background workers, and richer analytics without a major rewrite.

## Features

- Gmail OAuth2 connect, callback, status check, and logout flow
- Inbox and thread retrieval using the Gmail API
- Gemini-powered reply draft generation with:
  - tone selection
  - optional signature injection
  - additional instructions
  - lightweight style learning from recent sent emails
- Draft review workflow with approve, edit, and reject actions
- Safe send flow with idempotency keys, retries, and audit logs
- SQLite persistence for users, preferences, drafts, send attempts, and logs
- Encrypted storage for Gmail credentials and user preferences

## Tech Stack

- Python 3.9+
- FastAPI
- SQLAlchemy
- SQLite
- Gmail API
- Google OAuth2
- Google Gemini via `google-genai`
- Tenacity
- Cryptography

## Project Structure

```text
app/
  main.py
  config.py
  db.py
  models.py
  schemas.py
  security.py
  utils.py
  services/
    draft_service.py
    gemini_service.py
    gmail_service.py
    repositories.py
tests/
design/
reports/
```

## Setup

1. Create and activate a virtual environment.

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Install dependencies.

```bash
pip install -r requirements.txt
```

3. Copy the environment template.

```bash
cp .env.example .env
```

4. Set the required values in `.env`.

```env
GOOGLE_GEMINI_API_KEY=your_gemini_api_key
GOOGLE_OAUTH_CLIENT_PATH=google-oauth-client.json
GOOGLE_REDIRECT_URI=http://localhost:8000/api/auth/google/callback
```

5. Download your Google OAuth client JSON from Google Cloud and place it in the project root as `google-oauth-client.json`.

## Run the Server

```bash
source .venv/bin/activate
uvicorn app.main:app --reload
```

The API will be available at `http://localhost:8000`.

## Main API Endpoints

### Health

- `GET /health`

### Auth

- `GET /api/auth/google/start?email_hint=you@example.com`
- `GET /api/auth/google/callback?state=...&code=...`
- `GET /api/auth/status?email=you@example.com`
- `POST /api/auth/logout?email=you@example.com`

### Preferences

- `GET /api/preferences?email=you@example.com`
- `PUT /api/preferences?email=you@example.com`

Example request body:

```json
{
  "signature": "Best,\nJyot",
  "preferred_tone": "professional",
  "extra_instructions": "Reply in under 80 words."
}
```

### Email Access

- `GET /api/emails?email=you@example.com`
- `GET /api/threads/{thread_id}?email=you@example.com`

### Draft Generation

- `POST /api/drafts/generate`

Example request body:

```json
{
  "email": "you@example.com",
  "source_message_id": "19e2f59e4987f103",
  "tone": "professional",
  "signature": "Best,\nJyot",
  "additional_instructions": "Reply in under 80 words."
}
```

### Draft Review

- `GET /api/drafts?email=you@example.com`
- `GET /api/drafts/{draft_id}`
- `POST /api/drafts/{draft_id}/review`

Approve example:

```json
{
  "action": "approve"
}
```

Edit example:

```json
{
  "action": "edit",
  "edited_body": "Thanks for the note. Tuesday at 3 PM works well for me."
}
```

Reject example:

```json
{
  "action": "reject",
  "rejection_reason": "Need to respond manually."
}
```

### Send Draft

- `POST /api/drafts/{draft_id}/send`

Example request body:

```json
{
  "email": "you@example.com",
  "idempotency_key": "send-draft-42-attempt-1"
}
```

### Audit Logs

- `GET /api/logs`

## Expected Flow

1. Connect Gmail using the auth start endpoint.
2. Save signature and tone preferences.
3. Fetch inbox emails.
4. Generate a draft for a selected email.
5. Review the generated draft.
6. Approve or edit the draft.
7. Send the approved draft through Gmail.

## Reports and Design Assets

- `reports/` contains the full project report, Word document, PDF, and diagram assets.
- `design/` contains the one-pager submission exports.

## Testing

Run tests with:

```bash
source .venv/bin/activate
pytest -q
```

## Security Notes

- Gmail credentials and stored preferences are encrypted before being saved.
- Local development may generate `data/.draftly.key` if `ENCRYPTION_KEY` is not provided.
- Local secrets such as `.env`, SQLite files, and OAuth client JSON are intentionally excluded from version control.

## Current Limitations

- This project is backend-first and does not yet include a production frontend.
- Gmail and Gemini flows require valid Google credentials to test end to end.
- SQLite is suitable for development and demos, but production would benefit from a managed database.

## Future Improvements

- Add a frontend dashboard for inbox browsing and draft review
- Add background workers for retries and token refresh handling
- Add richer personalization and reusable reply templates
- Add deployment automation and observability support
