from datetime import date, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_current_professional,
    get_current_user,
    require_api_key,
    require_manychat_integration_token,
    require_roles,
)
from app.core.security import get_password_hash, normalize_role
from app.db.session import get_db
from app.models.appointment import Appointment
from app.models.professional import Professional
from app.models.service import Service
from app.models.user import User
from app.models.weekly_availability import WeeklyAvailability
from app.schemas.calendar import (
    AppointmentCancel,
    AppointmentCreate,
    AppointmentReschedule,
    ProfessionalCreate,
    ServiceCreate,
    UserProfessionalCreate,
    UserProfessionalUpdate,
    WeeklyAvailabilityCreate,
)
from app.services.auth_service import username_or_email_exists
from app.services.calendar_service import (
    cancel_appointment,
    create_appointment,
    get_availability_by_service_date,
    get_professional,
    list_day_slots,
    list_professionals,
    list_service_names,
    list_services,
    reschedule_appointment,
    get_id_service_by_name,
    get_id_professional_by_name
)

public_router = APIRouter(
    prefix="/calendar",
    tags=["calendar"],
    dependencies=[Depends(require_api_key), Depends(require_manychat_integration_token)],
)

panel_router = APIRouter(prefix="/panel", tags=["panel"], dependencies=[Depends(get_current_user)])


async def _ensure_professional_access(
    db: AsyncSession,
    current_user: User,
    current_professional: Professional | None,
    professional_id: UUID,
) -> Professional:
    professional = await get_professional(db, professional_id)

    if current_user.role.lower() in {"master", "admin", "attendant"}:
        return professional

    if current_user.role.lower() == "professional" and current_professional and current_professional.id == professional.id:
        return professional

    raise HTTPException(status_code=403, detail="Usuário sem permissão para este profissional")


@public_router.post("/professionals", dependencies=[Depends(require_roles("master", "admin"))])
async def create_professional(payload: ProfessionalCreate, db: AsyncSession = Depends(get_db)):
    item = Professional(**payload.model_dump())
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


@public_router.post("/services", dependencies=[Depends(require_roles("master", "admin"))])
async def create_service(payload: ServiceCreate, db: AsyncSession = Depends(get_db)):
    item = Service(**payload.model_dump())
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


@public_router.get("/professionals/list", operation_id="getListProfessionals")
async def get_list_professionals(db: AsyncSession = Depends(get_db)):
    professionals = await list_professionals(db)
    names = [p.display_name for p in professionals]
    return {
        "total": len(names),
        "professionals": names,
        "professionals_text": ", ".join(names)
    }
 

@public_router.get("/availability/by-service-date/list", operation_id="getAvailabilityByServiceDate")
async def get_availability_by_service_date_route(
    service_name: str = Query(..., description="Nome do serviço"),
    target_date: date = Query(..., description="YYYY-MM-DD"),
    db: AsyncSession = Depends(get_db),
):
    data = await get_availability_by_service_date(db, service_name, target_date)
 
   
    slots = []
    for p in data["professionals"]:
        for slot in p["slots"]:
            slots.append(slot["label"])  
 
    return {
        "total": len(slots),
        "slots": slots,
        "slots_text": ", ".join(slots),
        "slots_list": "\n".join([f"- {slot}" for slot in slots])
    }

 
@public_router.get("/services/list", operation_id="getListServices")
async def get_list_services(db: AsyncSession = Depends(get_db)):
    services = await list_service_names(db)
    names = [s.name for s in services]
 
    return {
        "total": len(names),
        "services": names,
        "services_text": ", ".join(names)
    }


@public_router.get("/services")
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


@public_router.post("/availability", dependencies=[Depends(require_roles("master", "admin", "professional"))])
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


@public_router.get("/availability/by-service-date", operation_id="getAvailabilityByServiceDate")
async def get_availability_by_service_date_route(
    service_name: str = Query(..., description="Nome do serviço"),
    target_date: date = Query(..., description="YYYY-MM-DD"),
    db: AsyncSession = Depends(get_db),
):
    return await get_availability_by_service_date(db, service_name, target_date)


@public_router.get("/availability")
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


@public_router.post("/appointments")
async def schedule(payload: AppointmentCreate, db: AsyncSession = Depends(get_db)):
    appointment = await create_appointment(db, payload)
    return {
        "id": str(appointment.id),
        "status": appointment.status,
        "starts_at": appointment.starts_at.isoformat(),
        "ends_at": appointment.ends_at.isoformat(),
    }


@public_router.post("/appointments/reschedule")
async def reschedule(payload: AppointmentReschedule, db: AsyncSession = Depends(get_db)):
    appointment = await reschedule_appointment(db, payload)
    return {
        "id": str(appointment.id),
        "status": appointment.status,
        "starts_at": appointment.starts_at.isoformat(),
        "ends_at": appointment.ends_at.isoformat(),
    }


@public_router.post("/appointments/cancel")
async def cancel(payload: AppointmentCancel, db: AsyncSession = Depends(get_db)):
    appointment = await cancel_appointment(db, payload.appointment_id)
    return {
        "id": str(appointment.id),
        "status": appointment.status,
    }


@panel_router.get("/users-professionals")
async def list_users_professionals(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("master", "admin")),
):
    result = await db.execute(
        select(User, Professional)
        .outerjoin(Professional, Professional.user_id == User.id)
        .order_by(User.created_at.desc())
    )

    rows = result.all()
    items = []
    for user, professional in rows:
        items.append(
            {
                "user_id": str(user.id),
                "username": user.username,
                "full_name": user.full_name,
                "email": user.email,
                "role": user.role,
                "user_is_active": user.is_active,
                "professional_id": str(professional.id) if professional else None,
                "display_name": professional.display_name if professional else None,
                "timezone": professional.timezone if professional else None,
                "professional_is_active": professional.is_active if professional else None,
            }
        )
    return {"total": len(items), "items": items}


@panel_router.post("/users-professionals")
async def create_user_professional(
    payload: UserProfessionalCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("master", "admin")),
):
    if await username_or_email_exists(db, payload.username, payload.email):
        raise HTTPException(status_code=409, detail="Usuário ou e-mail já cadastrado")

    user = User(
        username=payload.username,
        full_name=payload.full_name,
        email=payload.email,
        role=normalize_role(payload.role),
        is_active=payload.user_is_active,
        password_hash=get_password_hash(payload.password),
    )
    db.add(user)
    await db.flush()

    professional = Professional(
        user_id=user.id,
        display_name=payload.display_name,
        timezone=payload.timezone,
        is_active=payload.professional_is_active,
    )
    db.add(professional)
    await db.commit()
    await db.refresh(user)
    await db.refresh(professional)

    return {
        "user_id": str(user.id),
        "professional_id": str(professional.id),
        "message": "Usuário/profissional cadastrado com sucesso",
    }


@panel_router.put("/users-professionals/{user_id}")
async def update_user_professional(
    user_id: UUID,
    payload: UserProfessionalUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("master", "admin")),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    prof_result = await db.execute(select(Professional).where(Professional.user_id == user.id))
    professional = prof_result.scalar_one_or_none()
    if not professional:
        raise HTTPException(status_code=404, detail="Profissional não encontrado")

    if await username_or_email_exists(db, payload.username, payload.email, exclude_user_id=user.id):
        raise HTTPException(status_code=409, detail="Usuário ou e-mail já cadastrado")

    user.username = payload.username
    user.full_name = payload.full_name
    user.email = payload.email
    user.role = normalize_role(payload.role)
    user.is_active = payload.user_is_active
    if payload.password:
        user.password_hash = get_password_hash(payload.password)

    professional.display_name = payload.display_name
    professional.timezone = payload.timezone
    professional.is_active = payload.professional_is_active

    await db.commit()
    return {"message": "Usuário/profissional atualizado com sucesso"}


@panel_router.delete("/users-professionals/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_professional(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("master", "admin")),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    await db.delete(user)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@panel_router.get("/professionals/options")
async def panel_professionals_options(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_professional: Professional | None = Depends(get_current_professional),
):
    if current_user.role.lower() == "professional":
        if not current_professional:
            return {"items": []}
        return {
            "items": [
                {
                    "professional_id": str(current_professional.id),
                    "display_name": current_professional.display_name,
                }
            ]
        }

    professionals = await list_professionals(db)
    return {
        "items": [
            {"professional_id": str(item.id), "display_name": item.display_name}
            for item in professionals
        ]
    }


@panel_router.get("/appointments")
async def panel_list_appointments(
    professional_id: UUID | None = None,
    target_date: date | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_professional: Professional | None = Depends(get_current_professional),
):
    stmt = (
        select(Appointment, Professional, Service)
        .join(Professional, Professional.id == Appointment.professional_id)
        .join(Service, Service.id == Appointment.service_id)
        .order_by(Appointment.starts_at.desc())
    )

    if target_date:
        start_dt = datetime.combine(target_date, datetime.min.time())
        end_dt = datetime.combine(target_date, datetime.max.time())
        stmt = stmt.where(Appointment.starts_at >= start_dt, Appointment.starts_at <= end_dt)

    if current_user.role.lower() == "professional":
        if not current_professional:
            return {"total": 0, "items": []}
        stmt = stmt.where(Appointment.professional_id == current_professional.id)
    elif professional_id:
        stmt = stmt.where(Appointment.professional_id == professional_id)

    result = await db.execute(stmt)
    rows = result.all()
    items = []
    for appointment, professional, service in rows:
        items.append(
            {
                "appointment_id": str(appointment.id),
                "professional_id": str(professional.id),
                "professional_name": professional.display_name,
                "service_id": str(service.id),
                "service_name": service.name,
                "customer_name": appointment.customer_name,
                "customer_phone": appointment.customer_phone,
                "customer_email": appointment.customer_email,
                "status": appointment.status,
                "starts_at": appointment.starts_at.isoformat(),
                "ends_at": appointment.ends_at.isoformat(),
                "notes": appointment.notes,
            }
        )
    return {"total": len(items), "items": items}


@panel_router.delete("/appointments/{appointment_id}")
async def panel_cancel_appointment(
    appointment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_professional: Professional | None = Depends(get_current_professional),
):
    result = await db.execute(select(Appointment).where(Appointment.id == appointment_id))
    appointment = result.scalar_one_or_none()
    if not appointment:
        raise HTTPException(status_code=404, detail="Agendamento não encontrado")

    if current_user.role.lower() == "professional":
        if not current_professional or current_professional.id != appointment.professional_id:
            raise HTTPException(status_code=403, detail="Usuário sem permissão para este agendamento")

    appointment.status = "cancelled"
    await db.commit()
    return {"message": "Agendamento cancelado com sucesso"}


@panel_router.get("/availabilities")
async def panel_list_availabilities(
    professional_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_professional: Professional | None = Depends(get_current_professional),
):
    stmt = (
        select(WeeklyAvailability, Professional)
        .join(Professional, Professional.id == WeeklyAvailability.professional_id)
        .order_by(Professional.display_name.asc(), WeeklyAvailability.weekday.asc(), WeeklyAvailability.start_time.asc())
    )

    if current_user.role.lower() == "professional":
        if not current_professional:
            return {"total": 0, "items": []}
        stmt = stmt.where(WeeklyAvailability.professional_id == current_professional.id)
    elif professional_id:
        stmt = stmt.where(WeeklyAvailability.professional_id == professional_id)

    result = await db.execute(stmt)
    rows = result.all()
    items = []
    for availability, professional in rows:
        items.append(
            {
                "availability_id": str(availability.id),
                "professional_id": str(professional.id),
                "professional_name": professional.display_name,
                "weekday": availability.weekday,
                "start_time": availability.start_time.strftime("%H:%M:%S"),
                "end_time": availability.end_time.strftime("%H:%M:%S"),
            }
        )
    return {"total": len(items), "items": items}


@panel_router.post("/availabilities")
async def panel_create_availability(
    payload: WeeklyAvailabilityCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_professional: Professional | None = Depends(get_current_professional),
):
    await _ensure_professional_access(db, current_user, current_professional, payload.professional_id)

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
    return {
        "availability_id": str(item.id),
        "message": "Horário de atendimento cadastrado com sucesso",
    }


@panel_router.delete("/availabilities/{availability_id}")
async def panel_delete_availability(
    availability_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_professional: Professional | None = Depends(get_current_professional),
):
    result = await db.execute(select(WeeklyAvailability).where(WeeklyAvailability.id == availability_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Horário de atendimento não encontrado")

    await _ensure_professional_access(db, current_user, current_professional, item.professional_id)
    await db.delete(item)
    await db.commit()
    return {"message": "Horário de atendimento excluído com sucesso"}


@public_router.get(
    "/get-idservice-by-name",
    summary="Buscar IDs de serviços pelo nome",
    description="Retorna os IDs dos serviços ativos com base no nome informado.",
)
async def get_idservice_by_name(
    nameservice: str = Query(..., description="Nome do serviço"),
    db: AsyncSession = Depends(get_db),
):
    """
    Endpoint para busca de IDs de serviços por nome.

    Headers obrigatórios:
    - API_KEY
    - MANYCHAT_INTEGRATION_TOKEN
    """
    return await get_id_service_by_name(db, nameservice)


@public_router.get(
    "/get-idprofessional-by-name",
    summary="Buscar IDs de profissionais pelo nome",
    description="Retorna os IDs dos profissionais ativos com base no nome informado.",
)
async def get_idprofessional_by_name(
    nameprofessional: str = Query(..., description="Nome do profissional"),
    db: AsyncSession = Depends(get_db),
):
    """
    Endpoint para busca de IDs de profissionais por nome.

    Headers obrigatórios:
    - API_KEY
    - MANYCHAT_INTEGRATION_TOKEN
    """
    return await get_id_professional_by_name(db, nameprofessional)