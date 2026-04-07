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
