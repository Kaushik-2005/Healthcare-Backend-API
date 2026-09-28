# Healthcare Backend Design

## 1. Scope

The application provides user authentication, diagnostic-centre and test retrieval, diagnostic-test bookings, simulated payments, payment webhooks, authorization, validation, pagination, rate limiting, and structured logging.

## 2. High-level architecture

```text
Client
  |
  v
FastAPI routes and middleware
  |
  v
Service layer
  |
  v
SQLAlchemy ORM
  |
  v
PostgreSQL or SQLite
```

The application is a modular monolith. Routes handle HTTP concerns. Middleware handles request logging and rate limiting. Services implement business rules. SQLAlchemy models map to database tables.

## 3. Project structure

```text
app/
├── config.py
├── database.py
├── logging_config.py
├── main.py
├── models.py
├── rate_limit.py
├── schemas.py
├── security.py
└── services.py

alembic/
├── env.py
├── script.py.mako
└── versions/0001_initial.py

scripts/evaluate.py
tests/
├── conftest.py
├── test_auth.py
├── test_bookings.py
├── test_centres.py
├── test_logging.py
├── test_payments.py
└── test_webhooks.py
```

## 4. Application modules

### `app/main.py`

Creates the FastAPI application and defines API routes. It also defines request logging middleware, startup table creation, and seed data.

### `app/config.py`

Loads database and JWT settings from environment variables and `.env`.

### `app/database.py`

Creates the SQLAlchemy engine, declarative base, session factory, and database dependency.

### `app/models.py`

Defines the SQLAlchemy entities, relationships, status values, constraints, monetary columns, and timestamps.

### `app/schemas.py`

Defines request and response validation models using Pydantic.

### `app/security.py`

Hashes and verifies passwords, creates JWTs, and resolves the authenticated user.

### `app/services.py`

Implements booking creation, ownership queries, state transitions, payment processing, and webhook processing.

### `app/logging_config.py`

Formats application events as JSON lines and writes them to standard output.

### `app/rate_limit.py`

Applies process-local request limits to signup, login, payment, and webhook routes.

## 5. Low-level request flow

For a protected request:

```text
HTTP request
  -> request logging middleware
  -> rate-limit middleware logic
  -> JWT dependency
  -> route function
  -> service function
  -> SQLAlchemy session
  -> database
  -> response logging
  -> HTTP response
```

Routes do not accept a client-provided user ID for user-owned operations. The user ID is read from the JWT.

## 6. Entity relationship model

```text
User 1 -------- N Booking N -------- 1 DiagnosticCentre
                       |
                       N
                       1 DiagnosticTest

DiagnosticCentre 1 --- N CentreTest N --- 1 DiagnosticTest

Booking 1 ------------ 0..1 Payment

Payment 1 ------------ N WebhookEvent
```

### Entity table

| Entity | Important fields | Constraints and purpose |
|---|---|---|
| `User` | `id`, `email`, `password_hash`, `created_at` | Email is unique. Password hashes are stored. |
| `DiagnosticCentre` | `id`, `name`, `location`, `created_at` | Stores centre information. |
| `DiagnosticTest` | `id`, `name`, `description` | Does not store price. |
| `CentreTest` | `centre_id`, `test_id`, `price` | Composite primary key. Stores centre-specific price. |
| `Booking` | `user_id`, `centre_id`, `test_id`, `appointment_at`, `amount`, `status` | Stores price snapshot and booking state. |
| `Payment` | `booking_id`, `provider_reference`, `amount`, `status` | One payment per booking. |
| `WebhookEvent` | `event_id`, `payment_id`, `event_type`, `processed_at` | `event_id` is unique for idempotency. |

Money uses `NUMERIC(10, 2)` columns.

## 7. Booking state machine

```text
PENDING   -- payment success --> CONFIRMED
PENDING   -- payment failure --> FAILED
PENDING   -- cancellation ----> CANCELLED
CONFIRMED -- cancellation ----> CANCELLED
```

The allowed transitions are centralized in `app/services.py`. Invalid transitions return `409 Conflict`.

## 8. Payment flow

```text
Authenticated user
  -> find owned booking
  -> confirm booking is PENDING
  -> create Payment
  -> set payment status to SUCCESS or FAILED
  -> transition booking to CONFIRMED or FAILED
  -> commit transaction
```

The payment amount is copied from the booking amount. The client cannot provide an amount.

## 9. Webhook flow and idempotency

```text
Webhook request
  -> validate event payload
  -> look up event_id
  -> return existing payment if already processed
  -> load payment
  -> update payment and booking
  -> insert WebhookEvent
  -> commit transaction
```

`WebhookEvent.event_id` has a database-level unique constraint. If concurrent requests race, the uniqueness constraint prevents duplicate event records.

## 10. Authorization

Booking queries are scoped by both booking ID and authenticated user ID. This applies to:

- Booking retrieval
- Booking cancellation
- Payment processing
- Booking listing

Unauthorized booking access returns `404` to avoid revealing whether another user's booking exists.

## 11. Pagination

The following list endpoints accept `limit` and `offset`:

```text
GET /centres
GET /centres/{centre_id}/tests
GET /tests
GET /bookings
```

`limit` defaults to `20` and accepts `1` through `100`. `offset` defaults to `0`. The response remains a JSON list.

## 12. Rate limiting

Rate limits are maintained in process memory and keyed by client IP and route:

| Route | Limit |
|---|---:|
| `POST /auth/signup` | 20 per minute |
| `POST /auth/login` | 20 per minute |
| `POST /payments/` | 30 per minute |
| `POST /payments/webhook/` | 60 per minute |

Exceeding a limit returns `429` with `Retry-After` and rate-limit headers. A multi-process deployment requires shared storage such as Redis.

## 13. Transactions and migrations

Alembic migration `0001_initial.py` creates the schema. Payment and webhook operations update related records in one database transaction. The application also calls `create_all` on startup for local development.

## 14. Docker deployment layout

```text
docker compose
├── api
│   ├── FastAPI
│   ├── Alembic migration
│   └── Uvicorn
└── db
    └── PostgreSQL 16
```

The API waits for the PostgreSQL health check before starting. PostgreSQL data is stored in the `postgres_data` volume.

