# EVE Healthcare Backend User Guide

This guide explains how to run, use, understand, and extend the EVE Healthcare backend assignment.

## 1. What the project does

The backend supports this flow:

```text
User signup/login
        ↓
Browse diagnostic centres and tests
        ↓
Create a booking
        ↓
Process a simulated payment
        ↓
Update the booking through payment/webhook events
```

The project is intentionally a small modular monolith. It keeps the required business logic in one application and avoids optional infrastructure such as Redis, Celery, queues, and microservices.

## 2. Prerequisites

- Python 3.12 or newer
- PowerShell on Windows
- PostgreSQL if using a PostgreSQL database; SQLite is used by default for local development

## 3. Installation

From the repository root:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[test]"
```

If PowerShell blocks activation, run:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Then activate the environment again.

## 4. Configuration

Copy the example configuration:

```powershell
Copy-Item .env.example .env
```

Important settings:

```text
DATABASE_URL=postgresql+psycopg://eve:eve@localhost:5432/eve_healthcare
JWT_SECRET_KEY=change-me-in-development
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
```

If `DATABASE_URL` is not set, the application uses `sqlite:///./eve_healthcare.db`.

## 5. Database setup

Run the migration:

```powershell
alembic upgrade head
```

The migration creates these tables:

```text
users
diagnostic_centres
diagnostic_tests
centre_tests
bookings
payments
webhook_events
```

The application also creates tables on startup for local convenience and seeds one diagnostic centre and one test when no centre exists.

### Docker Compose setup

Docker Compose provides a PostgreSQL database and API container:

```powershell
docker compose up --build
```

The API container waits for the database health check, runs `alembic upgrade head`, and starts Uvicorn. Open `http://127.0.0.1:8000/docs` after the containers start.

Stop the containers without deleting database data:

```powershell
docker compose down
```

To remove the PostgreSQL volume as well, use this only when a clean database is intended:

```powershell
docker compose down -v
```

## 6. Start the application

```powershell
uvicorn app.main:app --reload
```

Useful URLs:

- API: `http://127.0.0.1:8000`
- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`
- Health check: `http://127.0.0.1:8000/health`

Swagger UI is the easiest way to try the API interactively.

## 7. Using the API

## Endpoint reference

| Method | Endpoint | Authentication | Purpose |
|---|---|---|---|
| `GET` | `/health` | No | Confirms that the API process is running. |
| `POST` | `/auth/signup` | No | Creates a new user account and securely hashes the password. |
| `POST` | `/auth/login` | No | Verifies credentials and returns a JWT bearer token. |
| `GET` | `/centres` | No | Lists all diagnostic centres. |
| `GET` | `/centres/{centre_id}` | No | Retrieves one diagnostic centre by ID. |
| `GET` | `/centres/{centre_id}/tests` | No | Lists tests offered by a centre, including centre-specific prices. |
| `GET` | `/tests` | No | Lists all diagnostic tests. |
| `POST` | `/bookings` | Yes | Creates a pending booking for the authenticated user. |
| `GET` | `/bookings` | Yes | Lists only the authenticated user’s bookings. |
| `GET` | `/bookings/{booking_id}` | Yes | Retrieves one owned booking. |
| `POST` | `/bookings/{booking_id}/cancel` | Yes | Cancels an owned booking when its current state permits cancellation. |
| `POST` | `/payments/` | Yes | Creates a deterministic simulated payment and updates the booking state. |
| `POST` | `/payments/webhook/` | No JWT | Applies a provider payment-status event and safely ignores duplicate event IDs. |

Protected endpoints require this header:

```text
Authorization: Bearer <access_token>
```

### 7.1 Create a user

`POST /auth/signup`

```json
{
  "email": "patient@example.com",
  "password": "password123"
}
```

Passwords must be at least eight characters. Password hashes are stored; plaintext passwords are never returned.

### 7.2 Log in

`POST /auth/login`

```json
{
  "email": "patient@example.com",
  "password": "password123"
}
```

Copy the returned `access_token`. In Swagger, click **Authorize** and enter:

```text
Bearer <access_token>
```

### 7.3 Browse centres and tests

Use:

```text
GET /centres
GET /centres/{centre_id}
GET /centres/{centre_id}/tests
GET /tests
```

`GET /centres/{centre_id}/tests` returns the tests offered by that centre and the centre-specific price.

### 7.4 Create a booking

`POST /bookings`

```json
{
  "centre_id": 1,
  "test_id": 1,
  "appointment_at": "2099-10-02T10:30:00Z"
}
```

The authenticated user is taken from the JWT. The client cannot provide `user_id` or `amount`. The server reads the price from `centre_tests` and stores an amount snapshot on the booking.

New bookings have status `PENDING`.

### 7.5 View bookings

```text
GET /bookings
GET /bookings/{booking_id}
```

Users only see their own bookings. Accessing another user’s booking returns `404` so the API does not reveal whether the resource exists.

### 7.6 Cancel a booking

`POST /bookings/{booking_id}/cancel`

Cancellation is allowed from `PENDING` or `CONFIRMED`. A `FAILED` or already `CANCELLED` booking cannot be transitioned again.

### 7.7 Process a simulated payment

`POST /payments/`

Successful payment:

```json
{
  "booking_id": 1,
  "simulate": "SUCCESS"
}
```

Failed payment:

```json
{
  "booking_id": 2,
  "simulate": "FAILED"
}
```

Only the booking owner can pay. A booking must be `PENDING` and can have only one payment.

Payment results update the booking:

```text
SUCCESS → CONFIRMED
FAILED  → FAILED
```

### 7.8 Process a payment webhook

`POST /payments/webhook/`

```json
{
  "event_id": "evt_123",
  "payment_id": 1,
  "status": "SUCCESS"
}
```

The webhook does not require a user JWT because it represents a provider callback. The same `event_id` can be submitted repeatedly. Only one `WebhookEvent` is stored and repeated requests become no-ops.

## 8. Booking state machine

Allowed transitions:

```text
PENDING   → CONFIRMED
PENDING   → FAILED
PENDING   → CANCELLED
CONFIRMED → CANCELLED
```

Invalid transitions such as `FAILED → CONFIRMED` and `CANCELLED → PENDING` return `409 Conflict`.

## 9. Project structure

```text
app/
├── __init__.py
├── config.py
├── database.py
├── main.py
├── models.py
├── schemas.py
├── security.py
└── services.py

alembic/
├── env.py
├── script.py.mako
└── versions/
    └── 0001_initial.py

tests/
├── conftest.py
├── test_auth.py
├── test_bookings.py
├── test_centres.py
├── test_payments.py
└── test_webhooks.py

scripts/
└── evaluate.py

.env.example
.gitignore
.dockerignore
Dockerfile
docker-compose.yml
AGENTS.md
alembic.ini
Assignment.pdf
README.md
pyproject.toml
roadmap.md
USER_GUIDE.md
```

## 10. What each application file does

### `app/main.py`

Creates the FastAPI application, registers endpoints, creates the local schema at startup, and seeds initial data.

Routes are intentionally thin. They parse requests, resolve dependencies, call service functions, and return responses.

### `app/config.py`

Defines environment-backed settings such as the database URL and JWT configuration.

### `app/database.py`

Creates the SQLAlchemy engine, declarative base, session factory, and `get_db()` dependency.

### `app/models.py`

Defines the database entities and relationships:

- `User`
- `DiagnosticCentre`
- `DiagnosticTest`
- `CentreTest`
- `Booking`
- `Payment`
- `WebhookEvent`

It also defines booking/payment status values and UTC timestamp handling.

### `app/schemas.py`

Defines Pydantic request and response models. This is where request validation occurs, including email validation, password length, positive IDs, allowed payment statuses, and required webhook fields.

### `app/security.py`

Handles password hashing, password verification, JWT creation, and the `get_current_user()` authentication dependency.

### `app/services.py`

Contains business rules:

- Booking validation and price lookup
- Ownership checks
- State transition validation
- Payment processing
- Webhook idempotency and transactional updates

This is the main service layer and keeps business logic out of routes.

## 11. Database design

`CentreTest` owns the price because the same test can cost different amounts at different centres.

`Booking.amount` stores a snapshot because future price changes must not change an existing booking.

`Payment.booking_id` is unique because this implementation allows one payment per booking.

`WebhookEvent.event_id` is unique at the database level so concurrent duplicate webhook requests cannot create multiple event records.

All monetary values use fixed-precision numeric columns rather than floating-point values.

## 12. Test structure

Run all tests:

```powershell
pytest
```

Test files:

- `test_auth.py`: signup, duplicate email, login, invalid credentials, and JWT enforcement.
- `test_centres.py`: centre/test retrieval and centre-specific pricing.
- `test_bookings.py`: amount snapshots, pending status, date validation, and ownership.
- `test_payments.py`: successful/failed payments, cancellation, and payment restrictions.
- `test_webhooks.py`: repeated webhook idempotency and unknown payment handling.

The test fixture uses a separate SQLite database and resets its data before each test.

## Structured logging

The application writes dependency-free structured JSON logs to standard output. Request logs include the HTTP method, path, status code, duration, and an `X-Request-ID` response header. If a client sends an `X-Request-ID` header, the same value is returned and logged; otherwise the application generates one.

Business events are logged for booking creation, payment processing, cancellation, successful webhook processing, and duplicate webhook suppression. Passwords, JWTs, request bodies, and authorization headers are intentionally excluded from logs.

Example request log:

```json
{
  "timestamp": "2026-09-27T14:58:53.779620+00:00",
  "level": "INFO",
  "logger": "healthcare",
  "message": "request_completed",
  "event": "http_request",
  "request_id": "f6533d2e9a314d81901c9c0eb359d6d3",
  "method": "GET",
  "path": "/health",
  "status_code": 200,
  "duration_ms": 1.38
}
```

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

## 13. Automating the evaluation

Run the narrated automated API evaluation from the repository root:

```powershell
python scripts\evaluate.py
```

The script prints each workflow step, result, and visual data-flow path such as `CLIENT -> ROUTER -> SERVICE -> DATABASE`, then reports `AUTOMATED EVALUATION PASSED`. It uses a temporary SQLite database and checks authentication, centre/test retrieval, price snapshots, booking ownership, successful and failed payments, cancellation rules, repeated webhooks, invalid appointments, and unknown payments. It does not run pytest.

Run the test suite separately with:

```powershell
pytest
```

The temporary evaluation database is removed automatically when the script completes.

## 14. Troubleshooting

### Python cannot be found

Install Python 3.12 and recreate the virtual environment:

```powershell
Remove-Item .venv -Recurse -Force
py -3.12 -m venv .venv
```

### PowerShell refuses to activate the environment

Run:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

### Database connection fails

Check `DATABASE_URL` in `.env`. For local evaluation, remove or unset it to use SQLite.

### Port 8000 is already in use

Start on another port:

```powershell
uvicorn app.main:app --reload --port 8001
```

## 15. Recommended evaluation flow

1. Create the virtual environment.
2. Install dependencies.
3. Run `alembic upgrade head`.
4. Run `pytest`.
5. Start Uvicorn.
6. Open `/docs`.
7. Signup and login.
8. Browse centres/tests.
9. Create a booking.
10. Process a successful payment.
11. Submit the same webhook three times.
12. Verify the booking remains confirmed.
13. Test a failed payment and unauthorized access.
