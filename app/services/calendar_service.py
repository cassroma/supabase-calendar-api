from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.appointment import Appointment
from app.models.professional import Professional
from app.models.service import Service
from app.models.weekly_availability import WeeklyAvailability
from app.schemas.calendar import AppointmentCreate, AppointmentReschedule

TZ = ZoneInfo(settings.app_timezone)
VALID_STATUSES = {"scheduled", "rescheduled"}


async def list_services(db: AsyncSession):
    result = await db.execute(select(Service).where(Service.is_active.is_(True)).order_by(Service.name.asc()))
    return result.scalars().all()


async def get_service(db: AsyncSession, service_id):
    result = await db.execute(select(Service).where(Service.id == service_id, Service.is_active.is_(True)))
    service = result.scalar_one_or_none()
    if not service:
        raise HTTPException(status_code=404, detail="Serviço não encontrado")
    return service


async def get_professional(db: AsyncSession, professional_id):
    result = await db.execute(
        select(Professional).where(Professional.id == professional_id, Professional.is_active.is_(True))
    )
    professional = result.scalar_one_or_none()
    if not professional:
        raise HTTPException(status_code=404, detail="Profissional não encontrado")
    return professional


async def list_day_slots(db: AsyncSession, professional_id, service_id, target_date):
    professional = await get_professional(db, professional_id)
    service = await get_service(db, service_id)
    if service.professional_id != professional.id:
        raise HTTPException(status_code=400, detail="Serviço não pertence ao profissional")

    weekday = target_date.weekday()
    windows_result = await db.execute(
        select(WeeklyAvailability).where(
            WeeklyAvailability.professional_id == professional.id,
            WeeklyAvailability.weekday == weekday,
        )
    )
    windows = windows_result.scalars().all()
    if not windows:
        return []

    start_of_day = datetime.combine(target_date, datetime.min.time()).replace(tzinfo=TZ)
    end_of_day = start_of_day + timedelta(days=1)

    appointments_result = await db.execute(
        select(Appointment).where(
            Appointment.professional_id == professional.id,
            Appointment.status.in_(VALID_STATUSES),
            Appointment.starts_at < end_of_day,
            Appointment.ends_at > start_of_day,
        )
    )
    appointments = appointments_result.scalars().all()

    slots = []
    duration = timedelta(minutes=service.duration_minutes)
    min_notice = datetime.now(TZ) + timedelta(minutes=settings.booking_min_notice_minutes)

    for window in windows:
        cursor = datetime.combine(target_date, window.start_time).replace(tzinfo=TZ)
        window_end = datetime.combine(target_date, window.end_time).replace(tzinfo=TZ)

        while cursor + duration <= window_end:
            candidate_end = cursor + duration
            overlaps = any(a.starts_at < candidate_end and a.ends_at > cursor for a in appointments)
            if not overlaps and cursor >= min_notice:
                slots.append(
                    {
                        "start": cursor.isoformat(),
                        "end": candidate_end.isoformat(),
                        "label": cursor.strftime("%H:%M"),
                    }
                )
            cursor += timedelta(minutes=settings.default_slot_minutes)

    return slots


async def create_appointment(db: AsyncSession, payload: AppointmentCreate):
    professional = await get_professional(db, payload.professional_id)
    service = await get_service(db, payload.service_id)
    if service.professional_id != professional.id:
        raise HTTPException(status_code=400, detail="Serviço não pertence ao profissional")

    starts_at = datetime.combine(payload.appointment_date, payload.appointment_time).replace(tzinfo=TZ)
    ends_at = starts_at + timedelta(minutes=service.duration_minutes)

    weekday = payload.appointment_date.weekday()
    availability_result = await db.execute(
        select(WeeklyAvailability).where(
            WeeklyAvailability.professional_id == professional.id,
            WeeklyAvailability.weekday == weekday,
            WeeklyAvailability.start_time <= payload.appointment_time,
            WeeklyAvailability.end_time >= ends_at.timetz().replace(tzinfo=None),
        )
    )
    availability = availability_result.scalar_one_or_none()
    if not availability:
        raise HTTPException(status_code=400, detail="Horário fora da disponibilidade semanal")

    conflict_result = await db.execute(
        select(Appointment).where(
            Appointment.professional_id == professional.id,
            Appointment.status.in_(VALID_STATUSES),
            Appointment.starts_at < ends_at,
            Appointment.ends_at > starts_at,
        )
    )
    conflict = conflict_result.scalar_one_or_none()
    if conflict:
        raise HTTPException(status_code=409, detail="Conflito de horário detectado")

    appointment = Appointment(
        professional_id=professional.id,
        service_id=service.id,
        customer_name=payload.customer_name,
        customer_phone=payload.customer_phone,
        customer_email=payload.customer_email,
        notes=payload.notes,
        starts_at=starts_at,
        ends_at=ends_at,
        status="scheduled",
    )
    db.add(appointment)
    await db.commit()
    await db.refresh(appointment)
    return appointment


async def reschedule_appointment(db: AsyncSession, payload: AppointmentReschedule):
    result = await db.execute(select(Appointment).where(Appointment.id == payload.appointment_id))
    appointment = result.scalar_one_or_none()
    if not appointment:
        raise HTTPException(status_code=404, detail="Agendamento não encontrado")

    service = await get_service(db, appointment.service_id)
    starts_at = datetime.combine(payload.new_date, payload.new_time).replace(tzinfo=TZ)
    ends_at = starts_at + timedelta(minutes=service.duration_minutes)

    conflict_result = await db.execute(
        select(Appointment).where(
            Appointment.professional_id == appointment.professional_id,
            Appointment.id != appointment.id,
            Appointment.status.in_(VALID_STATUSES),
            Appointment.starts_at < ends_at,
            Appointment.ends_at > starts_at,
        )
    )
    conflict = conflict_result.scalar_one_or_none()
    if conflict:
        raise HTTPException(status_code=409, detail="Novo horário conflita com outro agendamento")

    appointment.starts_at = starts_at
    appointment.ends_at = ends_at
    appointment.status = "rescheduled"
    await db.commit()
    await db.refresh(appointment)
    return appointment


async def cancel_appointment(db: AsyncSession, appointment_id):
    result = await db.execute(select(Appointment).where(Appointment.id == appointment_id))
    appointment = result.scalar_one_or_none()
    if not appointment:
        raise HTTPException(status_code=404, detail="Agendamento não encontrado")

    appointment.status = "cancelled"
    await db.commit()
    await db.refresh(appointment)
    return appointment
