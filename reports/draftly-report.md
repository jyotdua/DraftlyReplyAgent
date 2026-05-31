# Draftly Project Report

## 1. Introduction

Draftly is a backend-first Gmail AI reply agent designed to reduce the time users spend drafting repetitive email responses. The system integrates with Gmail using OAuth2, reads inbox and thread context, generates tone-aware reply drafts using Gemini, stores the generated drafts and audit data in SQLite, and only sends replies after explicit user approval.

The project was implemented as a FastAPI service with a modular architecture so that the backend can later support a web dashboard, background workers, or analytics without major restructuring.

## 2. Problem Statement

Professionals often spend a significant amount of time writing routine responses such as follow-ups, acknowledgements, scheduling confirmations, and polite clarifications. Although these responses are repetitive, they still require context-awareness, correct threading, and appropriate tone. A practical AI email assistant must therefore do more than text generation:

- understand the current Gmail thread
- adapt to the user's tone and preferences
- preserve reply metadata such as thread IDs and headers
- keep the user in control before sending
- maintain operational safety with retries, logging, and auditability

Draftly addresses this gap through a backend workflow that combines Gmail integration, LLM-based drafting, persistence, review controls, and send reliability mechanisms.

## 3. Objectives

The primary objectives of the project were:

- connect securely to Gmail using OAuth2
- fetch inbox messages and thread context through REST APIs
- generate AI-assisted reply drafts using Gemini
- personalize drafts using tone, signature, and recent sent-email style patterns
- store drafts, preferences, and logs in a database
- require approve/edit/reject before sending
- send approved replies back through Gmail with correct thread continuity
- include idempotency and retry handling for send actions

## 4. Scope

### In scope

- backend APIs for auth, inbox access, draft generation, review workflow, sending, and logs
- Gmail API integration
- Gemini API integration
- SQLite persistence
- encrypted storage for sensitive data
- report-level design documentation

### Out of scope

- production-grade frontend
- background job system
- multi-user team dashboard
- deployment automation and cloud hosting
- advanced analytics and monitoring dashboards

## 5. Technology Stack

- **Backend framework:** FastAPI
- **Language:** Python 3.9
- **ORM / DB access:** SQLAlchemy
- **Database:** SQLite
- **LLM provider:** Google Gemini via `google-genai`
- **Email provider:** Gmail API via `google-api-python-client`
- **Auth:** OAuth2 using `google-auth-oauthlib`
- **Retry handling:** Tenacity
- **Secrets protection:** Fernet encryption from `cryptography`

## 6. Functional Requirements

- Connect a user’s Gmail account using OAuth2.
- Check whether a Gmail account is currently connected.
- Disconnect Gmail access and revoke the stored token.
- Fetch unread or recent emails from Gmail with relevant metadata.
- Fetch thread-level message history for a selected email.
- Save user preferences such as signature and preferred tone.
- Generate a reply draft using thread context and user preferences.
- Learn lightweight stylistic patterns from recent sent emails.
- Allow a user to approve, edit, or reject a generated draft.
- Send only approved or edited drafts.
- Record send attempts, draft status transitions, and audit logs.

## 7. Non-Functional Requirements

- Maintain separation between routing, business logic, and persistence layers.
- Store credentials and preferences securely.
- Keep sending idempotent to reduce duplicate replies.
- Retry send failures automatically for transient errors.
- Keep the codebase modular enough for future UI or worker integration.
- Provide traceability through logs and persisted draft states.

## 8. High-Level Design (HLD)

### 8.1 System Overview

At a high level, Draftly follows a service-oriented backend flow:

1. A client calls FastAPI endpoints.
2. The API layer validates requests and delegates work to service classes.
3. The Gmail service handles mailbox access and reply sending.
4. The Gemini service handles AI draft generation.
5. The draft workflow service coordinates Gmail data retrieval, prompt composition, draft storage, and sending.
6. Repository helpers interact with the database models.
7. SQLite stores users, preferences, drafts, send attempts, and logs.

### 8.2 HLD Components

- **Client / Postman / Future UI**
  Sends REST requests to the backend.

- **FastAPI Application**
  Exposes endpoints for auth, preferences, emails, threads, drafts, send, and logs.

- **Gmail Service**
  Manages OAuth2 flows, profile lookup, message listing, thread retrieval, draft creation, and send execution.

- **Gemini Service**
  Builds prompts and calls the Gemini model for response generation.

- **Draft Workflow Service**
  Coordinates end-to-end draft lifecycle logic from source email to sent reply.

- **Repository Layer**
  Performs data persistence and status transitions using SQLAlchemy sessions.

- **Database**
  Stores user accounts, OAuth state, drafts, send attempts, and audit logs.

### 8.3 HLD Diagram Summary

```text
Client
  -> FastAPI Routes
     -> Gmail Service
     -> Gemini Service
     -> Draft Workflow Service
     -> Repository Layer
        -> SQLite Database

Draft Workflow Service also orchestrates Gmail Service + Gemini Service together.
```

## 9. Low-Level Design (LLD)

### 9.1 API Layer

The API layer is implemented in `app/main.py`.

Main endpoint groups:

- `/health`
- `/api/auth/...`
- `/api/preferences`
- `/api/emails`
- `/api/threads/{thread_id}`
- `/api/drafts/generate`
- `/api/drafts`
- `/api/drafts/{draft_id}`
- `/api/drafts/{draft_id}/review`
- `/api/drafts/{draft_id}/send`
- `/api/logs`

Responsibilities:

- request validation through Pydantic schemas
- dependency injection for database sessions
- error handling and HTTP status mapping
- serialization of ORM/domain objects to response models

### 9.2 Configuration Layer

`app/config.py` centralizes settings such as:

- app host and port
- database URL
- Gmail OAuth client path
- Gmail redirect URI
- Gemini API key
- Gmail fetch defaults
- encryption key resolution

This design keeps deployment/config changes out of business logic.

### 9.3 Database Layer

`app/db.py` sets up:

- SQLAlchemy engine
- session factory
- `Base` declarative model
- `get_db()` dependency for request-scoped sessions

### 9.4 Data Model Design

The project uses the following main entities:

#### UserAccount
- stores user email
- stores encrypted OAuth credentials
- stores encrypted preferences

#### OAuthState
- stores temporary OAuth state values for the auth callback flow

#### EmailDraft
- stores source message ID and thread ID
- stores generated and edited body
- stores review/sending status
- stores Gmail draft and sent message references
- stores prompt context and draft metadata

#### SendAttempt
- stores send-attempt history for idempotent and retry-aware sending

#### AuditLog
- stores important system events such as auth, draft generation, review, and sending

### 9.5 Repository Layer

`app/services/repositories.py` contains helper functions for:

- user lookup and upsert
- encrypting/decrypting credentials and preferences
- draft creation and retrieval
- review state updates
- send attempt creation and updates
- draft sent/failed transitions
- audit log creation and listing

This keeps persistence logic out of the route layer and reduces duplication.

### 9.6 Gmail Service Design

`app/services/gmail_service.py` encapsulates all Gmail-specific behavior:

- create OAuth flow
- generate authorization URL
- exchange auth code for credentials
- refresh credentials when needed
- build Gmail API client
- get user profile
- revoke credentials
- list inbox messages
- fetch individual messages
- fetch thread history
- sample recent sent emails for style learning
- create Gmail drafts
- send Gmail messages

Important implementation details:

- thread continuity is preserved using `threadId`
- reply semantics are preserved using `In-Reply-To` and `References`
- message content is normalized into a backend-friendly structure

### 9.7 Gemini Service Design

`app/services/gemini_service.py` is intentionally narrow:

- initializes a Gemini client lazily
- validates the presence of the API key
- builds a structured prompt using tone, latest message, thread summary, style samples, and extra instructions
- calls Gemini to generate a ready-to-send reply body

This module isolates prompt logic from routing and persistence logic.

### 9.8 Draft Workflow Design

`app/services/draft_service.py` is the orchestration core of the project.

#### Draft generation flow

1. Compute or accept an idempotency key.
2. Return an existing draft if the same generation request already exists.
3. Load user credentials and preferences.
4. Fetch the source Gmail message.
5. Fetch thread history.
6. Fetch recent sent emails for style learning.
7. Build the Gemini prompt.
8. Generate the draft.
9. Persist the draft in the database.
10. Create a Gmail-side draft.
11. Record audit logs.

#### Send flow

1. Verify draft status is approved/edited.
2. Reuse existing successful send result if already sent.
3. Create or reuse a send-attempt record.
4. Mark draft as sending.
5. Build reply payload from edited or generated content.
6. Send through Gmail using retry logic.
7. Persist send status and Gmail message IDs.
8. Update draft status to sent or failed.
9. Write audit log entry.

### 9.9 Utility and Security Design

#### `app/utils.py`
- idempotency key generation
- Gmail raw message encoding
- HTML-to-text cleanup
- timestamp conversion
- style sample compaction

#### `app/security.py`
- Fernet-based JSON encryption/decryption
- used for stored credentials and preferences

## 10. End-to-End Workflow

### 10.1 Authentication Workflow

1. User calls `/api/auth/google/start`.
2. Backend creates OAuth state and returns a Google consent URL.
3. User completes consent.
4. Google redirects to `/api/auth/google/callback`.
5. Backend exchanges code for credentials and stores encrypted token data.

### 10.2 Draft Creation Workflow

1. User fetches emails.
2. User chooses a source message.
3. User calls `/api/drafts/generate`.
4. Backend fetches Gmail message + thread.
5. Backend fetches recent sent messages.
6. Gemini generates the reply body.
7. Backend stores the draft and creates a Gmail draft.

### 10.3 Review Workflow

1. User lists drafts.
2. User opens one draft.
3. User approves, edits, or rejects it through `/review`.
4. Backend updates status and writes logs.

### 10.4 Sending Workflow

1. User calls `/send` for an approved draft.
2. Backend creates a send-attempt record.
3. Gmail send is executed with retries.
4. Draft and send-attempt statuses are updated.
5. Logs capture the final result.

## 11. Security Design

Security-related decisions include:

- OAuth2-based Gmail access instead of raw credentials
- encrypted storage of user credentials and preferences
- explicit approval before send
- idempotency keys to reduce duplicate sends
- logout path with token revocation support
- audit logs for traceability

Current limitations:

- encryption key defaults to a local generated key if not configured
- CORS is currently permissive for development
- SQLite is suitable for development but not ideal for larger production deployments

## 12. Testing and Verification

The project was verified through:

- unit tests for core utilities
- FastAPI health check validation
- local server startup validation
- live Gemini smoke test
- Gmail OAuth start-route validation

Functional checks covered:

- API boot success
- health endpoint success
- Gemini response generation success
- OAuth start URL generation success once client secrets were configured

## 13. Challenges and Trade-offs

### Challenge 1: Gmail threading correctness
Replies needed the correct thread and header metadata to maintain conversation continuity.

### Challenge 2: Human control vs automation
Direct autonomous sending was intentionally avoided because the requirement emphasizes user approval.

### Challenge 3: Personalization quality
Instead of building a heavy personalization engine, the project uses recent sent emails and stored preferences as lightweight style inputs.

### Challenge 4: Simplicity vs production readiness
SQLite and synchronous request-driven logic keep implementation simple, but production systems would likely add queues, workers, and managed persistence.

## 14. Future Enhancements

- Add a frontend dashboard for inbox browsing and review
- Add background jobs for retries and token maintenance
- Introduce async processing or task queues
- Add observability dashboards and metrics
- Support richer prompt profiles and custom templates
- Add automated classification to identify emails worth drafting automatically
- Upgrade database and deployment architecture for production use

## 15. Conclusion

Draftly demonstrates a complete backend architecture for a practical Gmail AI reply assistant. The solution integrates Gmail, Gemini, review controls, encrypted persistence, and reliable send handling into a single cohesive workflow. From a design perspective, the project balances usability, modularity, and safety by keeping AI generation helpful while preserving explicit human approval before sending.

The implemented architecture is intentionally extensible: the current backend can serve as the foundation for a future frontend product, a productionized deployment pipeline, or richer email automation features.
