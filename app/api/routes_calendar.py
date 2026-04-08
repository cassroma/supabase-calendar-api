from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_api_key
from app.db.session import get_db
from app.models.professional import Professional
from app.models.service import Service
from app.models.weekly_availability import WeeklyAvailability
from app.schemas.calendar import (
    AppointmentCancel,
    AppointmentCreate,
    AppointmentReschedule,
    ProfessionalCreate,
    ServiceCreate,
    WeeklyAvailabilityCreate,
)
from app.services.calendar_service import (
    cancel_appointment,
    create_appointment,
    get_availability_by_service_date,
    list_day_slots,
    list_professionals,
    list_service_names,
    list_services,
    reschedule_appointment,
)

router = APIRouter(prefix="/calendar", tags=["calendar"], dependencies=[Depends(require_api_key)])


@router.post("/professionals", dependencies=[Depends(get_current_user)])
async def create_professional(payload: ProfessionalCreate, db: AsyncSession = Depends(get_db)):
    item = Professional(**payload.model_dump())
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


@router.post("/services", dependencies=[Depends(get_current_user)])
async def create_service(payload: ServiceCreate, db: AsyncSession = Depends(get_db)):
    item = Service(**payload.model_dump())
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


@router.get("/professionals/list", operation_id="getListProfessionals")
async def get_list_professionals(db: AsyncSession = Depends(get_db)):
    professionals = await list_professionals(db)
    return {
        "total": len(professionals),
        "professionals": [p.display_name for p in professionals],
    }


@router.get("/services/list", operation_id="getListServices")
async def get_list_services(db: AsyncSession = Depends(get_db)):
    services = await list_service_names(db)
    return {
        "total": len(services),
        "services": [s.name for s in services],
    }


@router.get("/services")
async def get_services(db: AsyncSession = Depends(get_db)):
    services = await list_services(db)
    return [
        {
            "id": str(s.id),
            "professional_id": str(s.professional_id),
            "name": s.name,
            "duration_minutes": s.duration_minutes,
            "price": float(s.price) if s.price is not None else None,
        }
        for s in services
    ]


@router.post("/availability", dependencies=[Depends(get_current_user)])
async def create_weekly_availability(payload: WeeklyAvailabilityCreate, db: AsyncSession = Depends(get_db)):
    if payload.start_time >= payload.end_time:
        raise HTTPException(status_code=400, detail="start_time deve ser menor que end_time")
    item = WeeklyAvailability(**payload.model_dump())
    db.add(item)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Faixa semanal já cadastrada") from exc
    await db.refresh(item)
    return item


@router.get("/availability/by-service-date", operation_id="getAvailabilityByServiceDate")
async def get_availability_by_service_date_route(
    service_name: str = Query(..., description="Nome do serviço"),
    target_date: date = Query(..., description="YYYY-MM-DD"),
    db: AsyncSession = Depends(get_db),
):
    return await get_availability_by_service_date(db, service_name, target_date)


@router.get("/availability")
async def get_availability(
    professional_id: UUID,
    service_id: UUID,
    target_date: date = Query(..., description="YYYY-MM-DD"),
    db: AsyncSession = Depends(get_db),
):
    slots = await list_day_slots(db, professional_id, service_id, target_date)
    return {
        "professional_id": str(professional_id),
        "service_id": str(service_id),
        "date": target_date.isoformat(),
        "total": len(slots),
        "slots": slots,
    }


@router.post("/appointments")
async def schedule(payload: AppointmentCreate, db: AsyncSession = Depends(get_db)):
    appointment = await create_appointment(db, payload)
    return {
        "id": str(appointment.id),
        "status": appointment.status,
        "starts_at": appointment.starts_at.isoformat(),
        "ends_at": appointment.ends_at.isoformat(),
    }


@router.post("/appointments/reschedule")
async def reschedule(payload: AppointmentReschedule, db: AsyncSession = Depends(get_db)):
    appointment = await reschedule_appointment(db, payload)
    return {
        "id": str(appointment.id),
        "status": appointment.status,
        "starts_at": appointment.starts_at.isoformat(),
        "ends_at": appointment.ends_at.isoformat(),
    }


@router.post("/appointments/cancel")
async def cancel(payload: AppointmentCancel, db: AsyncSession = Depends(get_db)):
    appointment = await cancel_appointment(db, payload.appointment_id)
    return {
        "id": str(appointment.id),
        "status": appointment.status,
    }
