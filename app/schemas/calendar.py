from datetime import date, time
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field
from pydantic.functional_validators import BeforeValidator


def _parse_hour_minute_time(value):
    """
    Normaliza horários recebidos pela API para objetos `time`.

    Compatibilidades mantidas:
    - aceita `HH:MM` (novo formato preferencial para agendamento);
    - continua aceitando formatos já suportados como `HH:MM:SS`
      e `HH:MM:SS.sssZ`.

    Observação:
    Quando o cliente envia apenas `HH:MM`, o valor é convertido
    internamente para `HH:MM:00`, preservando o fluxo existente da API,
    que depois monta o datetime ISO em `starts_at` e `ends_at`.
    """
    if isinstance(value, time):
        return value.replace(tzinfo=None)

    if isinstance(value, str):
        raw_value = value.strip()

        if not raw_value:
            raise ValueError("Horário inválido")

        normalized_value = raw_value[:-1] if raw_value.endswith("Z") else raw_value

        if len(normalized_value) == 5:
            normalized_value = f"{normalized_value}:00"

        try:
            return time.fromisoformat(normalized_value).replace(tzinfo=None)
        except ValueError as exc:
            raise ValueError("Horário inválido. Use o formato HH:MM.") from exc

    return value


ApiTime = Annotated[
    time,
    BeforeValidator(_parse_hour_minute_time),
]


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
    appointment_time: ApiTime = Field(
        examples=["17:56"],
        description="Horário no formato HH:MM.",
    )
    customer_name: str
    customer_phone: str | None = None
    customer_email: EmailStr | None = None
    notes: str | None = None




class PatientCreate(BaseModel):
    full_name: str
    phone: str
    email: EmailStr | None = None
    notes: str | None = None


class PatientUpdate(BaseModel):
    full_name: str
    phone: str
    email: EmailStr | None = None
    notes: str | None = None
    is_active: bool = True


class PatientResponse(BaseModel):
    id: UUID
    full_name: str
    phone: str
    email: EmailStr | None = None
    notes: str | None = None
    is_active: bool


class AppointmentReschedule(BaseModel):
    appointment_id: UUID
    new_date: date
    new_time: ApiTime = Field(
        examples=["17:56"],
        description="Horário no formato HH:MM.",
    )


class AppointmentCancel(BaseModel):
    appointment_id: UUID
    reason: str | None = None


class CurrentDateResponse(BaseModel):
    date: str
    weekday: str


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
