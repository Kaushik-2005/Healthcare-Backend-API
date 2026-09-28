import logging
import time
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Query
from starlette.requests import Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.database import Base, engine, get_db
from app.models import Booking, BookingStatus, CentreTest, DiagnosticCentre, DiagnosticTest, Payment, User
from app.schemas import BookingCreate, BookingResponse, CentreResponse, CentreTestResponse, LoginRequest, PaymentCreate, PaymentResponse, TestResponse, TokenResponse, UserCreate, UserResponse, WebhookRequest
from app.security import create_access_token, get_current_user, hash_password, verify_password
from app.services import create_booking, get_owned_booking, process_payment, process_webhook, transition_booking
from app.logging_config import configure_logging
from app.rate_limit import check_rate_limit

logger = configure_logging()
app = FastAPI(title="Healthcare Backend API", version="0.1.0")


@app.middleware("http")
async def log_requests(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", uuid4().hex)
    started = time.perf_counter()
    rate_limit_response, rate_limit_headers = check_rate_limit(request)
    if rate_limit_response is not None:
        rate_limit_response.headers["X-Request-ID"] = request_id
        return rate_limit_response
    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "request_failed",
            extra={"event": "http_request_failed", "request_id": request_id, "method": request.method, "path": request.url.path},
        )
        raise
    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "request_completed",
        extra={
            "event": "http_request",
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
        },
    )
    for name, value in rate_limit_headers.items():
        response.headers[name] = value
    return response


@app.on_event("startup")
def startup() -> None:
    Base.metadata.create_all(bind=engine)
    with Session(engine) as db:
        if db.scalar(select(DiagnosticCentre.id)) is None:
            centre = DiagnosticCentre(name="EVE Diagnostics", location="Bengaluru")
            test = DiagnosticTest(name="Complete Blood Count", description="CBC blood test")
            db.add_all([centre, test])
            db.flush()
            db.add(CentreTest(centre_id=centre.id, test_id=test.id, price=500))
            db.commit()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/auth/signup", response_model=UserResponse, status_code=201)
def signup(payload: UserCreate, db: Session = Depends(get_db)) -> User:
    if db.scalar(select(User).where(User.email == payload.email.lower())) is not None:
        raise HTTPException(status_code=409, detail="Email is already registered")
    user = User(email=payload.email.lower(), password_hash=hash_password(payload.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Email is already registered")
    db.refresh(user)
    return user


@app.post("/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return TokenResponse(access_token=create_access_token(user.id))


@app.get("/centres", response_model=list[CentreResponse])
def list_centres(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0), db: Session = Depends(get_db)) -> list[DiagnosticCentre]:
    statement = select(DiagnosticCentre).order_by(DiagnosticCentre.id).offset(offset).limit(limit)
    return list(db.scalars(statement))


@app.get("/centres/{centre_id}", response_model=CentreResponse)
def get_centre(centre_id: int, db: Session = Depends(get_db)) -> DiagnosticCentre:
    centre = db.get(DiagnosticCentre, centre_id)
    if centre is None:
        raise HTTPException(status_code=404, detail="Diagnostic centre not found")
    return centre


@app.get("/centres/{centre_id}/tests", response_model=list[CentreTestResponse])
def list_centre_tests(centre_id: int, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0), db: Session = Depends(get_db)) -> list[CentreTestResponse]:
    if db.get(DiagnosticCentre, centre_id) is None:
        raise HTTPException(status_code=404, detail="Diagnostic centre not found")
    rows = db.scalars(select(CentreTest).where(CentreTest.centre_id == centre_id).offset(offset).limit(limit)).all()
    return [CentreTestResponse(id=row.test.id, name=row.test.name, description=row.test.description, price=row.price) for row in rows]


@app.get("/tests", response_model=list[TestResponse])
def list_tests(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0), db: Session = Depends(get_db)) -> list[DiagnosticTest]:
    statement = select(DiagnosticTest).order_by(DiagnosticTest.id).offset(offset).limit(limit)
    return list(db.scalars(statement))


@app.post("/bookings", response_model=BookingResponse, status_code=201)
def create_booking_endpoint(payload: BookingCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Booking:
    return create_booking(db, user, payload.centre_id, payload.test_id, payload.appointment_at)


@app.get("/bookings", response_model=list[BookingResponse])
def list_bookings(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0), user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[Booking]:
    statement = select(Booking).where(Booking.user_id == user.id).order_by(Booking.id).offset(offset).limit(limit)
    return list(db.scalars(statement))


@app.get("/bookings/{booking_id}", response_model=BookingResponse)
def get_booking(booking_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Booking:
    return get_owned_booking(db, booking_id, user)


@app.post("/bookings/{booking_id}/cancel", response_model=BookingResponse)
def cancel_booking(booking_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Booking:
    booking = get_owned_booking(db, booking_id, user)
    transition_booking(booking, BookingStatus.CANCELLED.value)
    db.commit()
    db.refresh(booking)
    logger.info("booking_cancelled", extra={"event": "booking_cancelled", "booking_id": booking.id, "user_id": user.id})
    return booking


@app.post("/payments/", response_model=PaymentResponse, status_code=201)
def create_payment(payload: PaymentCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Payment:
    return process_payment(db, user, payload.booking_id, payload.simulate)


@app.post("/payments/webhook/", response_model=PaymentResponse)
def payment_webhook(payload: WebhookRequest, db: Session = Depends(get_db)) -> Payment:
    return process_webhook(db, payload.event_id, payload.payment_id, payload.status)
