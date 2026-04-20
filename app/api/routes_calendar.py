from datetime import date, datetime, timedelta
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
    get_appointment_id_by_phone_number,
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

    if current_user.role.lower() == "professional":
        allowed_professional_ids = await _list_current_user_professional_ids(db, current_user)
        if professional.id in allowed_professional_ids:
            return professional

    raise HTTPException(status_code=403, detail="Usuário sem permissão para este profissional")


async def _list_current_user_professional_ids(db: AsyncSession, current_user: User) -> list[UUID]:
    result = await db.execute(
        select(Professional.id)
        .where(Professional.user_id == current_user.id, Professional.is_active.is_(True))
        .order_by(Professional.created_at.asc(), Professional.display_name.asc())
    )
    return list(result.scalars().all())


async def _list_current_user_professionals(db: AsyncSession, current_user: User) -> list[Professional]:
    result = await db.execute(
        select(Professional)
        .where(
            Professional.user_id == current_user.id,
            Professional.is_active.is_(True),
        )
        .order_by(Professional.created_at.asc(), Professional.display_name.asc())
    )
    return list(result.scalars().all())


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
async def get_availability_by_service_date_list_route(
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




@public_router.get("/appointments/get-idappointment-by-phone", operation_id="appointmentId-by-phonenumber")
async def appointment_id_by_phone_number(
    phone_number: str = Query(..., description="Telefone do cliente para localizar o agendamento"),
    db: AsyncSession = Depends(get_db),
):
    appointment = await get_appointment_id_by_phone_number(db, phone_number)
    return {
        "phone_number": phone_number,
        "appointment_id": str(appointment.id),
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
    role = (current_user.role or "").lower()

    if role == "professional":
        items = [
            {"professional_id": str(item.id), "display_name": item.display_name}
            for item in await _list_current_user_professionals(db, current_user)
        ]
        return {"items": items}

    result = await db.execute(
        select(Professional)
        .where(Professional.is_active.is_(True))
        .order_by(Professional.display_name.asc())
    )
    items = [
        {"professional_id": str(item.id), "display_name": item.display_name}
        for item in result.scalars().all()
        if item.display_name
    ]

    return {"items": items}


@panel_router.get("/appointments")
async def panel_list_appointments(
    professional_id: UUID | None = None,
    target_date: date | None = None,
    period: str = Query("day", description="Período da consulta: day ou week"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_professional: Professional | None = Depends(get_current_professional),
):
    period_normalized = (period or "day").strip().lower()
    if period_normalized not in {"day", "week"}:
        raise HTTPException(status_code=400, detail="period deve ser 'day' ou 'week'")

    reference_date = target_date or date.today()

    stmt = select(Appointment).order_by(Appointment.starts_at.asc())

    filter_start = None
    filter_end = None
    week_start = None
    week_end = None

    if period_normalized == "week":
        week_start = reference_date - timedelta(days=reference_date.weekday())
        week_end = week_start + timedelta(days=6)
        filter_start = datetime.combine(week_start, datetime.min.time())
        filter_end = datetime.combine(week_end + timedelta(days=1), datetime.min.time())
        stmt = stmt.where(Appointment.starts_at >= filter_start, Appointment.starts_at < filter_end)
    elif target_date:
        filter_start = datetime.combine(reference_date, datetime.min.time())
        filter_end = datetime.combine(reference_date + timedelta(days=1), datetime.min.time())
        stmt = stmt.where(Appointment.starts_at >= filter_start, Appointment.starts_at < filter_end)

    current_role = (current_user.role or "").lower()
    if current_role == "professional":
        professional_ids = await _list_current_user_professional_ids(db, current_user)
        if not professional_ids:
            return {"total": 0, "items": []}
        stmt = stmt.where(Appointment.professional_id.in_(professional_ids))
    elif professional_id:
        stmt = stmt.where(Appointment.professional_id == professional_id)

    try:
        result = await db.execute(stmt)
        appointments = result.scalars().all()

        professional_ids = list({item.professional_id for item in appointments if item.professional_id})
        service_ids = list({item.service_id for item in appointments if item.service_id})

        professionals_by_id = {}
        services_by_id = {}

        if professional_ids:
            prof_result = await db.execute(select(Professional).where(Professional.id.in_(professional_ids)))
            professionals_by_id = {item.id: item for item in prof_result.scalars().all()}

        if service_ids:
            svc_result = await db.execute(select(Service).where(Service.id.in_(service_ids)))
            services_by_id = {item.id: item for item in svc_result.scalars().all()}

        items = []
        for appointment in appointments:
            professional = professionals_by_id.get(appointment.professional_id)
            service = services_by_id.get(appointment.service_id)
            items.append(
                {
                    "appointment_id": str(appointment.id),
                    "professional_id": str(appointment.professional_id) if appointment.professional_id else None,
                    "professional_name": professional.display_name if professional and professional.display_name else "Profissional",
                    "service_id": str(appointment.service_id) if appointment.service_id else None,
                    "service_name": service.name if service and service.name else "Serviço",
                    "customer_name": appointment.customer_name,
                    "customer_phone": appointment.customer_phone,
                    "customer_email": appointment.customer_email,
                    "status": appointment.status,
                    "starts_at": appointment.starts_at.isoformat() if appointment.starts_at else None,
                    "ends_at": appointment.ends_at.isoformat() if appointment.ends_at else None,
                    "notes": appointment.notes,
                }
            )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Falha ao carregar agendamentos: {exc}") from exc

    response = {
        "total": len(items),
        "period": period_normalized,
        "reference_date": reference_date.isoformat(),
        "items": items,
    }

    if filter_start and filter_end and period_normalized == "day":
        response["day"] = reference_date.isoformat()

    if week_start and week_end:
        response["week_start"] = week_start.isoformat()
        response["week_end"] = week_end.isoformat()

    return response


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

    current_role = (current_user.role or "").lower()

    if current_role == "professional":
        professional_ids = await _list_current_user_professional_ids(db, current_user)
        if appointment.professional_id not in professional_ids:
            raise HTTPException(status_code=403, detail="Usuário sem permissão para este agendamento")

    await cancel_appointment(db, appointment_id)
    return {"message": "Agendamento cancelado com sucesso"}


@panel_router.get("/availabilities")
async def panel_list_availabilities(
    professional_id: UUID | None = None,
    weekday: int | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_professional: Professional | None = Depends(get_current_professional),
):
    stmt = select(WeeklyAvailability).order_by(
        WeeklyAvailability.weekday.asc(),
        WeeklyAvailability.start_time.asc(),
    )

    current_role = (current_user.role or "").lower()

    if current_role == "professional":
        professional_ids = await _list_current_user_professional_ids(db, current_user)
        if not professional_ids:
            return {"total": 0, "items": []}
        stmt = stmt.where(WeeklyAvailability.professional_id.in_(professional_ids))
    elif professional_id:
        stmt = stmt.where(WeeklyAvailability.professional_id == professional_id)

    if weekday is not None:
        stmt = stmt.where(WeeklyAvailability.weekday == weekday)

    try:
        result = await db.execute(stmt)
        availabilities = result.scalars().all()

        professional_ids = list({item.professional_id for item in availabilities if item.professional_id})
        professionals_by_id = {}
        if professional_ids:
            prof_result = await db.execute(select(Professional).where(Professional.id.in_(professional_ids)))
            professionals_by_id = {item.id: item for item in prof_result.scalars().all()}

        items = []
        for availability in availabilities:
            professional = professionals_by_id.get(availability.professional_id)
            items.append(
                {
                    "availability_id": str(availability.id),
                    "professional_id": str(availability.professional_id) if availability.professional_id else None,
                    "professional_name": professional.display_name if professional and professional.display_name else "Profissional",
                    "weekday": availability.weekday,
                    "start_time": availability.start_time.strftime("%H:%M:%S") if availability.start_time else None,
                    "end_time": availability.end_time.strftime("%H:%M:%S") if availability.end_time else None,
                }
            )

        items.sort(key=lambda item: ((item.get("professional_name") or ""), item.get("weekday") or 0, item.get("start_time") or ""))
        return {"total": len(items), "items": items}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Falha ao carregar horários de atendimento: {exc}") from exc


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
    summary="Get Service Id By Name",
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
    summary="Get Professional Id By Name",
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