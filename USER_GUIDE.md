# Healthcare Backend User Guide

This guide explains how to install, start, and use the API. Architecture and database details are in [DESIGN.md](DESIGN.md).

## 1. Install

From the project folder, run:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[test]"
```

If PowerShell blocks activation:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

## 2. Configure

For local SQLite, no configuration is required. To use PostgreSQL:

```powershell
Copy-Item .env.example .env
```

Set `DATABASE_URL` in `.env`.

## 3. Initialize the database

```powershell
alembic upgrade head
```

## 4. Start the API

```powershell
uvicorn app.main:app --reload
```

Open these URLs:

```text
API:     http://127.0.0.1:8000
Swagger: http://127.0.0.1:8000/docs
ReDoc:   http://127.0.0.1:8000/redoc
Health:  http://127.0.0.1:8000/health
```

Swagger lets you send requests from the browser. For protected endpoints, click **Authorize** and enter `Bearer <access_token>`.

## 5. Run with Docker

Docker Compose starts the API and PostgreSQL:

```powershell
docker compose up --build
```

The API container waits for PostgreSQL, runs the migration, and starts Uvicorn.

Stop the containers:

```powershell
docker compose down
```

Remove the PostgreSQL volume as well:

```powershell
docker compose down -v
```

## 6. Endpoint reference

| Method | Endpoint | Authentication | Purpose |
|---|---|---|---|
| `GET` | `/health` | No | Check whether the API is running. |
| `POST` | `/auth/signup` | No | Create a user account. |
| `POST` | `/auth/login` | No | Verify credentials and return a JWT. |
| `GET` | `/centres` | No | List diagnostic centres. |
| `GET` | `/centres/{centre_id}` | No | Get one centre. |
| `GET` | `/centres/{centre_id}/tests` | No | List tests and prices for a centre. |
| `GET` | `/tests` | No | List diagnostic tests. |
| `POST` | `/bookings` | Yes | Create a booking. |
| `GET` | `/bookings` | Yes | List the current user's bookings. |
| `GET` | `/bookings/{booking_id}` | Yes | Get one owned booking. |
| `POST` | `/bookings/{booking_id}/cancel` | Yes | Cancel an owned booking. |
| `POST` | `/payments/` | Yes | Process a simulated payment. |
| `POST` | `/payments/webhook/` | No JWT | Process a payment provider event. |

Protected requests use:

```text
Authorization: Bearer <access_token>
```

## 7. Signup

Request:

```http
POST /auth/signup
```

```json
{
  "email": "patient@example.com",
  "password": "password123"
}
```

Response:

```json
{
  "id": 1,
  "email": "patient@example.com"
}
```

Passwords must contain at least eight characters.

## 8. Login

Request:

```http
POST /auth/login
```

```json
{
  "email": "patient@example.com",
  "password": "password123"
}
```

Response:

```json
{
  "access_token": "<jwt>",
  "token_type": "bearer"
}
```

Use the returned token for booking and payment requests.

## 9. Browse centres and tests

Request:

```http
GET /centres/1/tests
```

Response:

```json
[
  {
    "id": 1,
    "name": "Complete Blood Count",
    "description": "CBC blood test",
    "price": "500.00"
  }
]
```

The price belongs to the centre/test combination.

## 10. Create a booking

Request:

```http
POST /bookings
```

```json
{
  "centre_id": 1,
  "test_id": 1,
  "appointment_at": "2099-10-02T10:30:00Z"
}
```

Response:

```json
{
  "id": 1,
  "user_id": 1,
  "centre_id": 1,
  "test_id": 1,
  "appointment_at": "2099-10-02T10:30:00",
  "amount": "500.00",
  "status": "PENDING"
}
```

The server determines the user and amount. The client cannot provide either value.

## 11. View and cancel bookings

List bookings:

```http
GET /bookings
```

Get one booking:

```http
GET /bookings/1
```

Cancel a booking:

```http
POST /bookings/1/cancel
```

Example cancellation response:

```json
{
  "id": 1,
  "status": "CANCELLED"
}
```

Users can access only their own bookings.

## 12. Process a simulated payment

Successful payment request:

```http
POST /payments/
```

```json
{
  "booking_id": 1,
  "simulate": "SUCCESS"
}
```

Response:

```json
{
  "id": 1,
  "booking_id": 1,
  "provider_reference": "mock_<generated-value>",
  "amount": "500.00",
  "status": "SUCCESS"
}
```

The booking changes from `PENDING` to `CONFIRMED`.

For a failed payment, use:

```json
{
  "booking_id": 2,
  "simulate": "FAILED"
}
```

The booking changes from `PENDING` to `FAILED`.

## 13. Process a webhook

Request:

```http
POST /payments/webhook/
```

```json
{
  "event_id": "evt_123",
  "payment_id": 1,
  "status": "SUCCESS"
}
```

Response:

```json
{
  "id": 1,
  "booking_id": 1,
  "provider_reference": "mock_<generated-value>",
  "amount": "500.00",
  "status": "SUCCESS"
}
```

Sending the same `event_id` again does not create another webhook event.

## 14. Pagination

List endpoints accept `limit` and `offset`:

```text
GET /centres?limit=10&offset=0
GET /tests?limit=10&offset=10
GET /bookings?limit=10&offset=0
```

`limit` defaults to `20` and accepts values from `1` to `100`. `offset` defaults to `0`.

## 15. Rate limiting

The following routes have process-local limits:

```text
POST /auth/signup        20 requests/minute
POST /auth/login         20 requests/minute
POST /payments/          30 requests/minute
POST /payments/webhook/  60 requests/minute
```

When a limit is exceeded, the API returns `429` and a `Retry-After` header.

## 16. Structured logs

The API writes JSON logs to the terminal or Docker logs. Example:

```json
{
  "level": "INFO",
  "event": "http_request",
  "request_id": "abc123",
  "method": "GET",
  "path": "/health",
  "status_code": 200,
  "duration_ms": 1.38
}
```

Passwords, password hashes, JWTs, request bodies, and authorization headers are not printed.

## 17. Automated evaluation

Run the narrated API evaluation:

```powershell
python scripts\evaluate.py
```

The script uses a temporary SQLite database and checks authentication, retrieval, bookings, authorization, payments, webhooks, invalid requests, pagination, rate-limit headers, and database record counts.

Run the test suite separately:

```powershell
pytest
```

## 18. Troubleshooting

Python not found:

```powershell
Remove-Item .venv -Recurse -Force
py -3.12 -m venv .venv
```

Port 8000 already in use:

```powershell
uvicorn app.main:app --reload --port 8001
```

Database connection failure: check `DATABASE_URL` in `.env`, or remove it to use SQLite.

