from datetime import date, time
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class ProfessionalCreate(BaseModel):
    user_id: UUID
    display_name: str
    timezone: str = "America/Sao_Paulo"


class ServiceCreate(BaseModel):
    professional_id: UUID
    name: str
    description: str | None = None
    duration_minutes: int = Field(gt=0)
    price: float | None = None


class WeeklyAvailabilityCreate(BaseModel):
    professional_id: UUID
    weekday: int = Field(ge=0, le=6)
    start_time: time
    end_time: time


class AppointmentCreate(BaseModel):
    professional_id: UUID
    service_id: UUID
    appointment_date: date
    appointment_time: time
    customer_name: str
    customer_phone: str | None = None
    customer_email: EmailStr | None = None
    notes: str | None = None


class AppointmentReschedule(BaseModel):
    appointment_id: UUID
    new_date: date
    new_time: time


class AppointmentCancel(BaseModel):
    appointment_id: UUID
    reason: str | None = None


class UserProfessionalCreate(BaseModel):
    username: str
    full_name: str
    email: EmailStr | None = None
    password: str = Field(min_length=6)
    role: str = "professional"
    display_name: str
    timezone: str = "America/Sao_Paulo"
    professional_is_active: bool = True
    user_is_active: bool = True


class UserProfessionalUpdate(BaseModel):
    username: str
    full_name: str
    email: EmailStr | None = None
    password: str | None = Field(default=None, min_length=6)
    role: str
    display_name: str
    timezone: str = "America/Sao_Paulo"
    professional_is_active: bool = True
    user_is_active: bool = True
