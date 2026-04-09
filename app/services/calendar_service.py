from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.appointment import Appointment
from app.models.professional import Professional
from app.models.service import Service
from app.models.weekly_availability import WeeklyAvailability
from app.schemas.calendar import AppointmentCreate, AppointmentReschedule

TZ = ZoneInfo(settings.app_timezone)
VALID_STATUSES = {"scheduled", "rescheduled"}

async def list_professionals(db: AsyncSession):
    result = await db.execute(
        select(Professional).where(Professional.is_active.is_(True)).order_by(Professional.display_name.asc())
    )
    return result.scalars().all()


async def list_service_names(db: AsyncSession):
    result = await db.execute(select(Service).where(Service.is_active.is_(True)).order_by(Service.name.asc()))
    return result.scalars().all()


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


async def _build_day_slots(db: AsyncSession, professional, service, target_date, apply_min_notice: bool = True):
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
            if not overlaps and (not apply_min_notice or cursor >= min_notice):
                slots.append(
                    {
                        "start": cursor.isoformat(),
                        "end": candidate_end.isoformat(),
                        "label": cursor.strftime("%H:%M"),
                    }
                )
            cursor += timedelta(minutes=settings.default_slot_minutes)

    return slots


async def list_day_slots(db: AsyncSession, professional_id, service_id, target_date):
    professional = await get_professional(db, professional_id)
    service = await get_service(db, service_id)
    if service.professional_id != professional.id:
        raise HTTPException(status_code=400, detail="Serviço não pertence ao profissional")

    return await _build_day_slots(db, professional, service, target_date, apply_min_notice=True)


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


async def get_availability_by_service_date(db: AsyncSession, service_name: str, target_date):
    normalized_name = service_name.strip().lower()
    weekday = target_date.weekday()

    result = await db.execute(
        select(Service, Professional)
        .join(Professional, Professional.id == Service.professional_id)
        .join(
            WeeklyAvailability,
            WeeklyAvailability.professional_id == Service.professional_id,
        )
        .where(
            func.lower(Service.name) == normalized_name,
            Service.is_active.is_(True),
            Professional.is_active.is_(True),
            WeeklyAvailability.weekday == weekday,
        )
        .order_by(Professional.display_name.asc(), Service.created_at.asc(), Service.id.asc())
    )

    rows = result.unique().all()
    if not rows:
        raise HTTPException(status_code=404, detail="Serviço não encontrado para a data informada")

    professionals = []
    total_slots = 0
    seen_pairs = set()

    for service, professional in rows:
        pair_key = (service.id, professional.id)
        if pair_key in seen_pairs:
            continue
        seen_pairs.add(pair_key)

        slots = await _build_day_slots(db, professional, service, target_date, apply_min_notice=False)
        total_slots += len(slots)
        professionals.append(
            {
                "professional_id": str(professional.id),
                "display_name": professional.display_name,
                "service_id": str(service.id),
                "service_name": service.name,
                "slots": slots,
                "total": len(slots),
            }
        )

    return {
        "service_name": rows[0][0].name,
        "date": target_date.isoformat(),
        "total": total_slots,
        "professionals": professionals,
    }