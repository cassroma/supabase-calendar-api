from datetime import datetime, timedelta
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

from app.models import Service, Professional, WeeklyAvailability
from app.core.config import settings
from app.utils.timezone import TZ

# mantém função existente, só adiciona parâmetro opcional
async def list_day_slots(
    db: AsyncSession,
    professional_id,
    service_id,
    target_date,
    apply_min_notice: bool = True,
):
    from app.models import Appointment

    # serviço
    service_result = await db.execute(
        select(Service).where(Service.id == service_id)
    )
    service = service_result.scalar_one()

    duration = timedelta(minutes=service.duration_minutes)

    # disponibilidade semanal
    weekday = target_date.weekday()
    windows_result = await db.execute(
        select(WeeklyAvailability).where(
            WeeklyAvailability.professional_id == professional_id,
            WeeklyAvailability.weekday == weekday,
        )
    )
    windows = windows_result.scalars().all()

    if not windows:
        return []

    # agendamentos existentes
    start_day = datetime.combine(target_date, datetime.min.time()).replace(tzinfo=TZ)
    end_day = datetime.combine(target_date, datetime.max.time()).replace(tzinfo=TZ)

    appointments_result = await db.execute(
        select(Appointment).where(
            Appointment.professional_id == professional_id,
            Appointment.starts_at < end_day,
            Appointment.ends_at > start_day,
        )
    )
    appointments = appointments_result.scalars().all()

    min_notice = datetime.now(TZ) + timedelta(minutes=settings.booking_min_notice_minutes)

    slots = []

    for window in windows:
        cursor = datetime.combine(target_date, window.start_time).replace(tzinfo=TZ)
        window_end = datetime.combine(target_date, window.end_time).replace(tzinfo=TZ)

        while cursor + duration <= window_end:
            candidate_end = cursor + duration

            overlaps = any(
                a.starts_at < candidate_end and a.ends_at > cursor
                for a in appointments
            )

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


async def get_availability_by_service_date(
    db: AsyncSession,
    service_name: str,
    target_date,
):
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
        .order_by(Professional.display_name.asc(), Service.created_at.asc())
    )

    rows = result.unique().all()

    if not rows:
        raise HTTPException(
            status_code=404,
            detail="Serviço não encontrado para a data informada",
        )

    professionals = []
    total_slots = 0
    seen = set()

    for service, professional in rows:
        key = (service.id, professional.id)

        if key in seen:
            continue
        seen.add(key)

        slots = await list_day_slots(
            db,
            professional.id,
            service.id,
            target_date,
            apply_min_notice=False,  # 🔥 correção principal
        )

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