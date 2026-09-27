from datetime import datetime, timezone
from uuid import uuid4
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.models import Booking, BookingStatus, CentreTest, DiagnosticCentre, DiagnosticTest, Payment, PaymentStatus, User, WebhookEvent

ALLOWED_TRANSITIONS = {
    BookingStatus.PENDING.value: {BookingStatus.CONFIRMED.value, BookingStatus.FAILED.value, BookingStatus.CANCELLED.value},
    BookingStatus.CONFIRMED.value: {BookingStatus.CANCELLED.value},
    BookingStatus.FAILED.value: set(),
    BookingStatus.CANCELLED.value: set(),
}


def transition_booking(booking: Booking, target: str) -> None:
    if target not in ALLOWED_TRANSITIONS.get(booking.status, set()):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Cannot transition booking from {booking.status} to {target}")
    booking.status = target


def get_owned_booking(db: Session, booking_id: int, user: User) -> Booking:
    booking = db.scalar(select(Booking).where(Booking.id == booking_id, Booking.user_id == user.id))
    if booking is None:
        raise HTTPException(status_code=404, detail="Booking not found")
    return booking


def create_booking(db: Session, user: User, centre_id: int, test_id: int, appointment_at: datetime) -> Booking:
    if appointment_at.tzinfo is None:
        appointment_at = appointment_at.replace(tzinfo=timezone.utc)
    if appointment_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Appointment must be in the future")
    if db.get(DiagnosticCentre, centre_id) is None:
        raise HTTPException(status_code=404, detail="Diagnostic centre not found")
    if db.get(DiagnosticTest, test_id) is None:
        raise HTTPException(status_code=404, detail="Diagnostic test not found")
    centre_test = db.scalar(select(CentreTest).where(CentreTest.centre_id == centre_id, CentreTest.test_id == test_id))
    if centre_test is None:
        raise HTTPException(status_code=400, detail="Centre does not offer this test")
    booking = Booking(user_id=user.id, centre_id=centre_id, test_id=test_id, appointment_at=appointment_at, amount=centre_test.price, status=BookingStatus.PENDING.value)
    db.add(booking)
    db.commit()
    db.refresh(booking)
    return booking


def process_payment(db: Session, user: User, booking_id: int, simulate: str) -> Payment:
    booking = get_owned_booking(db, booking_id, user)
    if booking.status != BookingStatus.PENDING.value:
        raise HTTPException(status_code=409, detail="Booking is not payable")
    if booking.payment is not None:
        raise HTTPException(status_code=409, detail="Booking already has a payment")
    payment = Payment(booking_id=booking.id, provider_reference=f"mock_{uuid4().hex}", amount=booking.amount, status=simulate)
    db.add(payment)
    transition_booking(booking, BookingStatus.CONFIRMED.value if simulate == PaymentStatus.SUCCESS.value else BookingStatus.FAILED.value)
    db.commit()
    db.refresh(payment)
    return payment


def process_webhook(db: Session, event_id: str, payment_id: int, event_status: str) -> Payment:
    existing = db.scalar(select(WebhookEvent).where(WebhookEvent.event_id == event_id))
    if existing is not None:
        payment = db.get(Payment, existing.payment_id)
        if payment is None:
            raise HTTPException(status_code=404, detail="Payment not found")
        return payment
    payment = db.get(Payment, payment_id)
    if payment is None:
        raise HTTPException(status_code=404, detail="Payment not found")
    target = BookingStatus.CONFIRMED.value if event_status == PaymentStatus.SUCCESS.value else BookingStatus.FAILED.value
    if payment.status != event_status:
        payment.status = event_status
        if payment.booking.status != target:
            transition_booking(payment.booking, target)
    db.add(WebhookEvent(event_id=event_id, payment_id=payment.id, event_type=f"payment.{event_status.lower()}"))
    try:
        db.commit()
    except IntegrityError:
        # A concurrent duplicate can pass the read above. The unique
        # constraint is the final guard; treat its loser as an idempotent no-op.
        db.rollback()
        existing = db.scalar(select(WebhookEvent).where(WebhookEvent.event_id == event_id))
        if existing is None:
            raise
        payment = db.get(Payment, existing.payment_id)
        if payment is None:
            raise HTTPException(status_code=404, detail="Payment not found")
    db.refresh(payment)
    return payment
