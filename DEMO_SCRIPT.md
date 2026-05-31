# Draftly Demo Script

Use this script to record a project demo in under 5 minutes.

## 1. Introduction (20-30 seconds)

- Introduce the project name: Draftly Reply Agent
- Explain the problem briefly: writing repetitive email replies takes time
- Explain the solution briefly: Draftly connects to Gmail, reads context, generates Gemini-based drafts, and keeps the user in control before sending

## 2. Repository Overview (30-40 seconds)

- Open the GitHub repository
- Show the main folders:
  - `app/`
  - `tests/`
  - `design/`
  - `reports/`
- Mention that the backend is built with FastAPI and uses Gmail API plus Gemini

## 3. Run the Application (30-45 seconds)

- Show either:
  - local run using `uvicorn app.main:app --reload`
  - or Docker run using `docker compose up --build`
- Open `http://localhost:8000/health`
- Show the success response

## 4. Authentication Flow (30-40 seconds)

- Show the `/api/auth/google/start` endpoint in Postman or browser
- Explain that Gmail is connected through OAuth2, not raw credentials
- Mention that tokens are stored securely in encrypted form

## 5. Core Workflow Demo (90-120 seconds)

- Show the inbox fetch endpoint: `/api/emails`
- Show the thread fetch endpoint: `/api/threads/{thread_id}`
- Show the draft generation request: `/api/drafts/generate`
- Explain the payload:
  - email
  - source message id
  - tone
  - signature
  - additional instructions
- Show the generated draft response
- Show review flow:
  - approve
  - edit
  - reject
- Show send flow:
  - `/api/drafts/{draft_id}/send`

## 6. Design and Documentation (30-40 seconds)

- Open the one-pager from `design/`
- Open the report from `reports/word/draftly-report.docx` or `reports/draftly-report.pdf`
- Mention that the report includes:
  - HLD
  - LLD
  - entity design
  - workflows
  - security considerations

## 7. Closing (20-30 seconds)

- Summarize the project in one line
- Mention future scope:
  - frontend UI
  - background workers
  - better production deployment

## Suggested Recording Order

1. GitHub repo
2. README
3. Running app
4. Postman endpoints
5. Report and one-pager
6. Final summary
