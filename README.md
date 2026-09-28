# Healthcare Backend API
Backend service for diagnostic-centre test bookings and simulated payments.

## Overview

The service supports:

- User signup, login, password hashing, and JWT authentication.
- Diagnostic-centre and diagnostic-test retrieval.
- Centre-specific test pricing.
- Authenticated booking creation, retrieval, and cancellation.
- Deterministic simulated successful and failed payments.
- Idempotent payment webhooks.
- Ownership checks and validation for user-owned bookings.

The application uses FastAPI routes, service functions, SQLAlchemy models, and Pydantic schemas.

## Tech stack

- Python 3.12+
- FastAPI and Uvicorn
- SQLAlchemy 2
- PostgreSQL-compatible schema via psycopg
- SQLite by default for local development and tests
- Alembic migrations
- JWT with PyJWT
- Argon2 password hashing through `pwdlib`
- pytest and FastAPI `TestClient`

## Local setup

On Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[test]"
```

Copy `.env.example` to `.env` and update the values when using PostgreSQL. Without a `.env` file, the application uses `sqlite:///./eve_healthcare.db`.

Apply migrations:

```powershell
alembic upgrade head
```

Start the API:

```powershell
uvicorn app.main:app --reload
```

### Run with Docker Compose

Docker Compose starts PostgreSQL, waits for its health check, runs the Alembic migration, and starts the API:

```powershell
docker compose up --build
```

The API is then available at `http://127.0.0.1:8000`. Stop the services with `Ctrl+C`, or run `docker compose down`. Add `-v` to `docker compose down -v` only when you intentionally want to remove the PostgreSQL data volume.

The interactive API documentation is available at `http://127.0.0.1:8000/docs`; ReDoc is available at `/redoc`.

Documentation:

- [User Guide](USER_GUIDE.md): setup and API usage.
- [Design](DESIGN.md): architecture, modules, database, flows, and constraints.

Quick endpoint reference:

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/health` | API health check. |
| `POST` | `/auth/signup` | Create a user account. |
| `POST` | `/auth/login` | Return a JWT token. |
| `GET` | `/centres` | List diagnostic centres. |
| `GET` | `/centres/{centre_id}` | Retrieve one centre. |
| `GET` | `/centres/{centre_id}/tests` | List tests and prices for a centre. |
| `GET` | `/tests` | List diagnostic tests. |
| `POST` | `/bookings` | Create an authenticated user booking. |
| `GET` | `/bookings` | List the current user’s bookings. |
| `GET` | `/bookings/{booking_id}` | Retrieve an owned booking. |
| `POST` | `/bookings/{booking_id}/cancel` | Cancel an owned booking. |
| `POST` | `/payments/` | Process a simulated payment. |
| `POST` | `/payments/webhook/` | Process an idempotent payment webhook. |

## API endpoints

### Authentication

`POST /auth/signup`

```json
{"email": "patient@example.com", "password": "password123"}
```

`POST /auth/login` accepts the same fields and returns a bearer token:

```json
{"access_token": "<jwt>", "token_type": "bearer"}
```

Use `Authorization: Bearer <jwt>` for protected endpoints.

### Centres and tests

- `GET /centres`
- `GET /centres/{centre_id}`
- `GET /centres/{centre_id}/tests`
- `GET /tests`

The centre-test response includes the price for that specific centre. A small seed dataset is created on application startup when no centre exists.

### Bookings

- `POST /bookings`
- `GET /bookings`
- `GET /bookings/{booking_id}`
- `POST /bookings/{booking_id}/cancel`

Create a booking with:

```json
{
  "centre_id": 1,
  "test_id": 1,
  "appointment_at": "2026-10-02T10:30:00Z"
}
```

The server determines the authenticated user and reads the amount from `CentreTest`. The client cannot set `user_id` or `amount`. New bookings start as `PENDING`.

### Payments and webhooks

`POST /payments/`

```json
{
  "booking_id": 1,
  "simulate": "SUCCESS"
}
```

`simulate` can be `SUCCESS` or `FAILED`. A successful payment confirms the booking; a failed payment marks it failed.

`POST /payments/webhook/`

```json
{
  "event_id": "evt_123",
  "payment_id": 1,
  "status": "SUCCESS"
}
```

Repeated webhook requests with the same `event_id` return the existing payment without applying the event again.

## Database design

The schema contains:

- `users`: unique email and password hash.
- `diagnostic_centres`: centre name and location.
- `diagnostic_tests`: test name and description, without a universal price.
- `centre_tests`: many-to-many centre/test relationship with the authoritative price.
- `bookings`: user, centre, test, appointment, amount snapshot, and status.
- `payments`: one payment per booking, provider reference, amount, and status.
- `webhook_events`: processed event IDs with a database-level unique constraint.

Money uses fixed-precision `NUMERIC(10, 2)` values rather than floating point. Foreign keys and uniqueness constraints enforce important invariants at the database level.

## Booking lifecycle

```text
PENDING ── payment success ──> CONFIRMED
PENDING ── payment failure ──> FAILED
PENDING ── cancellation ────> CANCELLED
CONFIRMED ── cancellation ───> CANCELLED
```

Invalid transitions, such as `FAILED` to `CONFIRMED`, are rejected with `409 Conflict`.

## Webhook idempotency

Webhook handling first checks for an existing event. New events update the payment and booking together and record the event in the same transaction. `WebhookEvent.event_id` is also `UNIQUE`, which protects against concurrent duplicate requests. A uniqueness conflict is treated as an idempotent no-op.

## Validation, authorization, and errors

The API handles invalid payloads, duplicate signup, invalid credentials or JWTs, past appointments, missing resources, unavailable centre/test combinations, unauthorized booking access, cancelled or already-paid bookings, failed payments, unknown webhook payments, and repeated webhooks.

Typical responses are:

- `400`: invalid business request.
- `401`: missing or invalid authentication.
- `403`: authenticated but not authorized, where applicable.
- `404`: resource does not exist or is not owned by the current user.
- `409`: duplicate resource or invalid state transition.
- `422`: request schema validation failure.

## Running tests

```powershell
pytest
```

The tests cover authentication, centre/test retrieval, price snapshots, booking validation, ownership, successful and failed payments, cancellation rules, unknown webhooks, and repeated webhook idempotency.

Application logs are emitted as structured JSON lines. Each request includes a request ID, method, path, status code, and duration. Business events include booking creation, payment processing, cancellation, and webhook handling. Passwords, JWTs, request bodies, and authorization headers are never logged.

Example request log:

```json
{
  "timestamp": "2026-09-27T14:58:53.779620+00:00",
  "level": "INFO",
  "logger": "healthcare",
  "message": "request_completed",
  "event": "http_request",
  "request_id": "f6533d2e9a314d81901c9c0eb359d6c3",
  "method": "GET",
  "path": "/health",
  "status_code": 200,
  "duration_ms": 1.38
}
```

## Pagination

List endpoints support optional pagination without changing their response shape. Supported endpoints are:

```text
GET /centres?limit=20&offset=0
GET /centres/{centre_id}/tests?limit=20&offset=0
GET /tests?limit=20&offset=20
GET /bookings?limit=10&offset=0
```

`limit` defaults to `20` and accepts values between `1` and `100`. `offset` defaults to `0` and controls how many records are skipped. Invalid values return `422 Unprocessable Entity`.

## Rate limiting

Authentication, payment, and webhook endpoints have lightweight process-local limits:

| Endpoint | Limit |
|---|---:|
| `POST /auth/signup` | 20 requests/minute |
| `POST /auth/login` | 20 requests/minute |
| `POST /payments/` | 30 requests/minute |
| `POST /payments/webhook/` | 60 requests/minute |

Responses include `X-RateLimit-Limit`, `X-RateLimit-Remaining`, and `X-RateLimit-Reset`. Requests over the limit receive `429 Too Many Requests` and a `Retry-After` header. The limiter is process-local; a distributed deployment should replace it with Redis-backed rate limiting.

Example payment log:

```json
{
  "level": "INFO",
  "event": "payment_processed",
  "booking_id": 1,
  "payment_id": 1,
  "result": "SUCCESS"
}
```

Example duplicate webhook log:

```json
{
  "level": "INFO",
  "event": "webhook_duplicate",
  "event_id": "evaluation-success-event",
  "payment_id": 1
}
```

Run the automated API evaluation:

```powershell
python scripts\evaluate.py
```

The script executes the API workflow using a temporary SQLite database and prints each step and result. It does not run pytest. Run `pytest` separately for the test suite.
