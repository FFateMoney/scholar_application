# AutoScholar Auth, Database, and Token Design

## 1. Goal

This document defines the V1 design for adding user accounts, database-backed job persistence, and token-based authentication to the current AutoScholar service.

The goal is not to implement the feature immediately. The goal is to provide a decision-complete implementation document that can later be executed without re-opening core product or architecture choices.

This design must fit the current stack:

- `FastAPI` backend
- local workspace-based AutoScholar job execution
- local `codex` CLI integration
- static frontend served separately

## 2. Default Decisions

This document fixes the following defaults for V1:

- database: `SQLite`
- auth mode: `JWT access token + refresh token`
- registration mode: `open signup`
- password hashing: `argon2`
- current anonymous job model becomes authenticated job ownership
- workspace files under `backend/runtime/jobs/<job_id>` remain the artifact source of truth for generated files
- database stores metadata, ownership, status, and session records

These defaults are chosen for single-machine deployment and low operational overhead.

## 3. Current System Baseline

The current backend is a local FastAPI service with these properties:

- no database
- no account system
- no persistent auth
- job state tracked in memory and mirrored into `backend/runtime/state/*.json`
- job artifacts stored in per-job workspaces under `backend/runtime/jobs/<job_id>`

The current frontend is an anonymous single-page UI with:

- idea report submission
- reference bib submission
- polling-based job status refresh
- optional development-only Codex debug console

This means the new design must introduce user identity and persistence without breaking the current workspace-driven workflow engine.

## 4. Data Model

At minimum, V1 should introduce three tables.

### 4.1 `users`

Purpose:

- store account identity
- store login credentials safely
- support account status checks

Recommended columns:

| column | type | notes |
| --- | --- | --- |
| `id` | `TEXT` | primary key, UUID string |
| `username` | `TEXT` | unique, indexed |
| `password_hash` | `TEXT` | Argon2 hash only, never plaintext |
| `display_name` | `TEXT` | nullable |
| `status` | `TEXT` | `active` or `disabled` |
| `created_at` | `TEXT` | ISO timestamp |
| `updated_at` | `TEXT` | ISO timestamp |
| `last_login_at` | `TEXT` | nullable |

Constraints:

- `username` must be unique
- `status` should be constrained to known values

### 4.2 `jobs`

Purpose:

- persist job ownership
- persist job lifecycle state
- allow frontend recovery after refresh or backend restart
- index workspace metadata without moving artifact files into the database

Recommended columns:

| column | type | notes |
| --- | --- | --- |
| `id` | `TEXT` | primary key, reuses current `job_id` |
| `user_id` | `TEXT` | foreign key to `users.id`, indexed |
| `job_type` | `TEXT` | `idea_report` or `reference_bib` |
| `status` | `TEXT` | `queued`, `running`, `succeeded`, `failed` |
| `stage` | `TEXT` | current detailed workflow stage |
| `message` | `TEXT` | current human-readable progress message |
| `error` | `TEXT` | nullable |
| `workspace_dir` | `TEXT` | absolute local workspace path |
| `input_summary_json` | `TEXT` | serialized request summary for UI recovery |
| `primary_artifact_key` | `TEXT` | nullable |
| `created_at` | `TEXT` | ISO timestamp |
| `updated_at` | `TEXT` | ISO timestamp |
| `started_at` | `TEXT` | nullable |
| `finished_at` | `TEXT` | nullable |

Constraints:

- `user_id` must reference `users.id`
- `job_type` should be constrained to known values
- `status` should be constrained to known values

### 4.3 `refresh_tokens`

Purpose:

- support refresh-token-based login persistence
- support logout and token revocation
- prevent long-lived anonymous browser sessions from being the only recovery mechanism

Recommended columns:

| column | type | notes |
| --- | --- | --- |
| `id` | `TEXT` | primary key, UUID string |
| `user_id` | `TEXT` | foreign key to `users.id`, indexed |
| `token_id` | `TEXT` | JWT `jti`, unique |
| `expires_at` | `TEXT` | ISO timestamp |
| `revoked_at` | `TEXT` | nullable |
| `created_at` | `TEXT` | ISO timestamp |
| `user_agent` | `TEXT` | nullable |
| `ip_address` | `TEXT` | nullable |

Constraints:

- `token_id` must be unique
- a revoked token must never be accepted again

## 5. Authentication and Token Strategy

### 5.1 Token Model

V1 will use two tokens:

1. `access_token`
   short-lived JWT used in `Authorization: Bearer <token>`
2. `refresh_token`
   longer-lived JWT used only at refresh/logout boundaries

Recommended lifetimes:

- access token: `15 minutes`
- refresh token: `7 days`

Reasoning:

- access tokens stay short to limit replay risk
- refresh tokens allow page refresh and multi-minute job tracking without forcing constant logins

### 5.2 Password Handling

Passwords must never be stored or logged in plaintext.

V1 should use:

- `argon2` for password hashing
- constant-time verification through a dedicated password service

Recommended validation rules:

- minimum length: `8`
- maximum length: `128`
- usernames normalized before lookup

### 5.3 JWT Claims

Access token payload should include:

- `sub`: user id
- `username`
- `type`: `access`
- `exp`
- `iat`

Refresh token payload should include:

- `sub`: user id
- `type`: `refresh`
- `jti`
- `exp`
- `iat`

### 5.4 Refresh Rotation

V1 should support refresh token rotation.

Recommended behavior:

1. client sends refresh token to `/auth/refresh`
2. backend validates token signature and token record
3. backend marks old refresh token revoked
4. backend creates a new refresh token record
5. backend returns a new access token and a new refresh token

This must happen transactionally to avoid concurrent double-acceptance.

## 6. Backend API Design

### 6.1 Auth Endpoints

#### `POST /auth/register`

Purpose:

- create a new account

Request body:

```json
{
  "username": "alice",
  "password": "strong-password",
  "display_name": "Alice"
}
```

Response:

```json
{
  "user": {
    "id": "uuid",
    "username": "alice",
    "display_name": "Alice",
    "status": "active"
  }
}
```

Behavior:

- open registration is enabled
- duplicate usernames return `409`

#### `POST /auth/login`

Purpose:

- exchange username/password for tokens

Request body:

```json
{
  "username": "alice",
  "password": "strong-password"
}
```

Response:

```json
{
  "access_token": "jwt",
  "refresh_token": "jwt",
  "token_type": "bearer",
  "user": {
    "id": "uuid",
    "username": "alice",
    "display_name": "Alice",
    "status": "active"
  }
}
```

Behavior:

- disabled users cannot log in
- invalid credentials return `401`

#### `POST /auth/refresh`

Purpose:

- refresh login state after page reload or access token expiry

Request body:

```json
{
  "refresh_token": "jwt"
}
```

Response:

```json
{
  "access_token": "jwt",
  "refresh_token": "jwt",
  "token_type": "bearer"
}
```

#### `POST /auth/logout`

Purpose:

- revoke the current refresh token

Request body:

```json
{
  "refresh_token": "jwt"
}
```

Response:

```json
{
  "ok": true
}
```

#### `GET /auth/me`

Purpose:

- return the authenticated user profile

Headers:

- `Authorization: Bearer <access_token>`

Response:

```json
{
  "id": "uuid",
  "username": "alice",
  "display_name": "Alice",
  "status": "active"
}
```

### 6.2 Job Endpoints

Existing job endpoints remain, but all must require authentication and must enforce ownership.

Required endpoints:

- `POST /jobs/idea-report`
- `POST /jobs/reference-bib`
- `GET /jobs`
- `GET /jobs/{job_id}`
- `GET /jobs/{job_id}/result`
- `GET /jobs/{job_id}/files/{artifact_key}`
- `GET /jobs/{job_id}/logs/{artifact_key}`

#### `GET /jobs`

Purpose:

- allow frontend task recovery after refresh
- show recent jobs for the current user

Recommended query parameters:

- `limit`
- `offset`
- optional `status`
- optional `job_type`

Recommended response:

```json
{
  "items": [
    {
      "job_id": "abc123",
      "job_type": "idea_report",
      "status": "running",
      "stage": "citation_search_retry",
      "message": "Search round 2 left 7 failed queries.",
      "created_at": "2026-04-10T00:12:16Z",
      "updated_at": "2026-04-10T00:18:12Z",
      "primary_artifact_key": "final_idea_report"
    }
  ],
  "total": 1
}
```

### 6.3 Access Control Rules

Rules:

- all auth endpoints except `register` and `login` require valid token context
- all job endpoints require authenticated users
- users may only access their own jobs
- artifact and log downloads must perform owner checks before file resolution
- for unauthorized job access, return `404` rather than `403`

Reasoning:

- `404` avoids leaking whether another user’s job id exists

### 6.4 Debug Log Rule

The debug log endpoints may remain available in production code, but:

- they must still require authentication
- they must still enforce owner checks
- the frontend must hide the debug console unless `debugMode` is enabled

## 7. Backend Persistence Design

### 7.1 Required Layers

The backend should introduce a persistence layer rather than embedding raw SQL inside routers or job threads.

Recommended structure:

```text
backend/app/
  repositories/
    users.py
    jobs.py
    tokens.py
  services/
    auth.py
    job_state.py
```

Alternative naming such as `persistence/` is acceptable, but the separation of responsibility should remain.

### 7.2 Repository Responsibilities

`UserRepository`

- `create_user(...)`
- `get_user_by_username(...)`
- `get_user_by_id(...)`
- `update_last_login(...)`

`JobRepository`

- `create_job(...)`
- `get_job_by_id(...)`
- `list_jobs_for_user(...)`
- `mark_job_running(...)`
- `update_job_progress(...)`
- `mark_job_succeeded(...)`
- `mark_job_failed(...)`

`RefreshTokenRepository`

- `create_refresh_token(...)`
- `get_by_token_id(...)`
- `revoke_token(...)`
- `revoke_all_for_user(...)` optional

### 7.3 Service Responsibilities

`AuthService`

- password hashing and verification
- JWT creation and validation
- register/login/refresh/logout orchestration

`JobStateService`

- create job metadata row
- update stage transitions
- update completion/failure timestamps
- bridge current in-memory runtime flow with durable database state

### 7.4 Source of Truth

V1 design should treat the database as the source of truth for:

- user identity
- job ownership
- job lifecycle state
- task listing
- session and token validity

Workspace directories remain the source of truth for:

- artifacts
- generated markdown
- bib files
- Codex logs
- intermediate AutoScholar files

### 7.5 Runtime State Compatibility

Current `backend/runtime/state/*.json` files may remain temporarily for development compatibility and inspection, but they should not be treated as the durable source of truth once the database exists.

Recommended migration posture:

- continue writing them during transitional implementation if useful
- read job listings from the database only
- allow state JSON to be removed later without changing public API behavior

## 8. Transaction and Consistency Rules

### 8.1 Job Creation

Job creation consists of:

1. generating a `job_id`
2. creating the workspace directory path
3. inserting the database row
4. starting the background thread

Required consistency rule:

- the database row and workspace initialization must be handled as one logical unit

If workspace creation fails:

- do not leave a running job row behind

If the database insert fails:

- do not start the worker thread

### 8.2 Job Progress Updates

Every lifecycle change must be written through a single service path.

Allowed pattern:

- worker thread calls `update_job_progress(job_id, stage, message, status=None)`

Disallowed pattern:

- ad hoc mutation of in-memory objects without persistent write-through

### 8.3 Auth Transactions

Refresh token rotation and logout must be transaction-backed.

Required guarantees:

- old refresh token cannot remain valid after successful refresh
- logout must revoke the provided refresh token before returning success

## 9. Frontend Product Changes

### 9.1 New Screens

The anonymous frontend should evolve into an authenticated frontend with these views:

- registration page
- login page
- main workspace page
- my jobs page
- job detail page

### 9.2 Login Flow

Recommended flow:

1. user opens login page
2. user logs in
3. frontend stores access token in memory
4. frontend stores refresh token in `localStorage`
5. frontend redirects to main workspace
6. frontend loads `/auth/me`
7. frontend loads recent jobs from `GET /jobs`

### 9.3 Refresh Recovery

After browser refresh:

1. frontend starts with no in-memory access token
2. frontend reads refresh token from `localStorage`
3. frontend calls `/auth/refresh`
4. if successful, access token is restored
5. frontend calls `/auth/me`
6. frontend calls `GET /jobs`
7. frontend restores the most recent job selection or job detail route

This is the mechanism that fixes the current “page refresh loses the tracked job” issue.

### 9.4 Token Storage Policy

V1 storage choice:

- access token: memory only
- refresh token: `localStorage`

Reasoning:

- avoids long-lived access token persistence
- allows page refresh recovery
- keeps the implementation compatible with the current static frontend architecture

Tradeoff:

- `localStorage` is less secure than httpOnly cookies, but acceptable for the current local single-machine deployment target

### 9.5 Frontend Request Behavior

Authenticated requests must attach:

```http
Authorization: Bearer <access_token>
```

On `401`:

1. frontend attempts one refresh operation
2. if refresh succeeds, original request is retried once
3. if refresh fails, frontend clears auth state and routes to login

### 9.6 UI Behavior Changes

The current “input snapshot” and “final result” panels should remain.

What changes:

- the current user’s identity is visible in the UI
- the recent jobs list is database-backed
- job detail view is loadable from persisted backend state
- current active job can be re-opened after refresh
- debug console is shown only if the user is authenticated and `debugMode` is enabled

## 10. Migration and Implementation Notes

This document does not require immediate implementation, but it defines the expected build direction.

Recommended future implementation steps:

1. add SQLite database bootstrap and migration file(s)
2. add repositories and service layer
3. add auth endpoints
4. add authenticated current-user dependency
5. add ownership checks to job endpoints
6. switch job creation and progress updates to database-backed persistence
7. add `GET /jobs`
8. add frontend login/register and recent jobs pages
9. add token refresh recovery logic

## 11. Acceptance and Test Scenarios

### 11.1 Authentication

Must pass:

- new user can register
- registered user can log in
- wrong password returns `401`
- disabled user cannot log in
- access token expiry can be recovered via refresh
- logout revokes refresh token

### 11.2 Authorization

Must pass:

- unauthenticated access to job endpoints returns `401`
- user A cannot access user B’s job detail
- user A cannot download user B’s artifact or debug log
- unauthorized owner checks return `404`

### 11.3 Job Persistence

Must pass:

- created job row stores correct `user_id`
- job moves from `queued` to `running` to terminal state with durable updates
- terminal states persist after backend restart
- frontend can reload and still fetch the user’s job list
- frontend can reopen a completed job and download its artifact

### 11.4 Compatibility

Must pass:

- existing workspace artifact paths still work
- idea report and reference bib workflows keep current output formats
- adding auth/db does not require changing AutoScholar artifact schemas

## 12. Security and Scope Boundaries

Included in V1:

- local account registration
- password hashing
- token authentication
- refresh token revocation
- job ownership enforcement

Explicitly deferred:

- email verification
- password reset flow
- RBAC
- multi-tenant org model
- OAuth
- SSO
- database sharding
- replacing the workspace artifact model with blob storage

## 13. Final Position

The recommended V1 path is:

- keep AutoScholar workspace execution unchanged
- add user identity and job ownership through SQLite-backed persistence
- use JWT access and refresh tokens for frontend login state
- make database state authoritative for jobs and sessions
- keep filesystem workspaces as authoritative for artifacts and logs

This design is intentionally conservative. It fixes the missing product foundations needed for multi-session and multi-user use, while preserving the current local execution model that already works for idea reports and reference bib generation.
