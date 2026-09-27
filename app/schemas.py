from datetime import datetime
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserResponse(BaseModel):
    id: int
    email: EmailStr
    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginRequest(UserCreate):
    pass


class TestResponse(BaseModel):
    id: int
    name: str
    description: str | None
    model_config = ConfigDict(from_attributes=True)


class CentreTestResponse(TestResponse):
    price: Decimal


class CentreResponse(BaseModel):
    id: int
    name: str
    location: str
    model_config = ConfigDict(from_attributes=True)


class BookingCreate(BaseModel):
    centre_id: int = Field(gt=0)
    test_id: int = Field(gt=0)
    appointment_at: datetime


class BookingResponse(BaseModel):
    id: int
    user_id: int
    centre_id: int
    test_id: int
    appointment_at: datetime
    amount: Decimal
    status: str
    model_config = ConfigDict(from_attributes=True)


class PaymentCreate(BaseModel):
    booking_id: int = Field(gt=0)
    simulate: Literal["SUCCESS", "FAILED"] = "SUCCESS"


class PaymentResponse(BaseModel):
    id: int
    booking_id: int
    provider_reference: str
    amount: Decimal
    status: str
    model_config = ConfigDict(from_attributes=True)


class WebhookRequest(BaseModel):
    event_id: str = Field(min_length=1, max_length=150)
    payment_id: int = Field(gt=0)
    status: Literal["SUCCESS", "FAILED"]

