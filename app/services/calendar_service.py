from __future__ import annotations

"""
Serviço de calendário da aplicação.

Este módulo concentra as regras de negócio relacionadas a:
- listagem de profissionais e serviços ativos;
- validação de vínculo entre profissional e serviço;
- cálculo de slots disponíveis por data;
- criação, remarcação e cancelamento de agendamentos;
- consulta de disponibilidade por nome do serviço e data.

A documentação foi escrita em português para facilitar a manutenção
do projeto e o entendimento do fluxo por outros desenvolvedores.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.appointment import Appointment
from app.models.professional import Professional
from app.models.service import Service
from app.models.weekly_availability import WeeklyAvailability
from app.schemas.calendar import AppointmentCreate, AppointmentReschedule

# Timezone oficial da aplicação, usada para montar e comparar datas/horários.
TZ = ZoneInfo(settings.app_timezone)

# Status considerados válidos como "ocupando agenda".
# Agendamentos cancelados, por exemplo, não entram em conflito.
VALID_STATUSES = {"scheduled", "rescheduled"}


async def list_professionals(db: AsyncSession):
    """
    Retorna todos os profissionais ativos ordenados por nome de exibição.

    Objetivo:
    - fornecer a lista de profissionais disponíveis no sistema;
    - evitar retorno de registros inativos.

    Parâmetros:
    - db: sessão assíncrona do SQLAlchemy.

    Retorno:
    - lista de objetos Professional.
    """
    result = await db.execute(
        select(Professional).where(Professional.is_active.is_(True)).order_by(Professional.display_name.asc())
    )
    return result.scalars().all()


async def list_service_names(db: AsyncSession):
    """
    Retorna os serviços ativos ordenados por nome.

    Observação:
    Apesar do nome da função sugerir apenas "nomes", ela atualmente
    retorna os objetos Service completos, mantendo o comportamento
    já utilizado no projeto.

    Parâmetros:
    - db: sessão assíncrona do SQLAlchemy.

    Retorno:
    - lista de objetos Service ativos.
    """
    result = await db.execute(select(Service).where(Service.is_active.is_(True)).order_by(Service.name.asc()))
    return result.scalars().all()


async def list_services(db: AsyncSession):
    """
    Retorna todos os serviços ativos ordenados por nome.

    Esta função é semelhante à list_service_names, mas foi mantida
    separadamente para preservar o padrão e a interface já adotados
    no projeto.

    Parâmetros:
    - db: sessão assíncrona do SQLAlchemy.

    Retorno:
    - lista de objetos Service ativos.
    """
    result = await db.execute(select(Service).where(Service.is_active.is_(True)).order_by(Service.name.asc()))
    return result.scalars().all()


async def get_service(db: AsyncSession, service_id):
    """
    Busca um serviço ativo pelo identificador.

    Regras:
    - somente serviços ativos podem ser retornados;
    - se o serviço não existir, lança HTTP 404.

    Parâmetros:
    - db: sessão assíncrona do SQLAlchemy.
    - service_id: identificador do serviço.

    Retorno:
    - objeto Service.

    Exceções:
    - HTTPException(404): quando o serviço não é encontrado.
    """
    result = await db.execute(select(Service).where(Service.id == service_id, Service.is_active.is_(True)))
    service = result.scalar_one_or_none()
    if not service:
        raise HTTPException(status_code=404, detail="Serviço não encontrado")
    return service


async def get_professional(db: AsyncSession, professional_id):
    """
    Busca um profissional ativo pelo identificador.

    Regras:
    - somente profissionais ativos podem ser retornados;
    - se o profissional não existir, lança HTTP 404.

    Parâmetros:
    - db: sessão assíncrona do SQLAlchemy.
    - professional_id: identificador do profissional.

    Retorno:
    - objeto Professional.

    Exceções:
    - HTTPException(404): quando o profissional não é encontrado.
    """
    result = await db.execute(
        select(Professional).where(Professional.id == professional_id, Professional.is_active.is_(True))
    )
    professional = result.scalar_one_or_none()
    if not professional:
        raise HTTPException(status_code=404, detail="Profissional não encontrado")
    return professional


async def _get_windows_for_date(
    db: AsyncSession,
    professional_id,
    target_date,
    fallback_to_any_weekday: bool = False,
):
    """
    Busca as janelas de disponibilidade semanal de um profissional para uma data.

    Esta função trata uma inconsistência comum entre duas convenções de dia da semana:
    - Python weekday(): 0=segunda ... 6=domingo
    - ISO isoweekday(): 1=segunda ... 7=domingo

    Fluxo:
    1. Calcula os dois possíveis valores de weekday da data.
    2. Procura disponibilidades do profissional usando qualquer uma das convenções.
    3. Se não encontrar nada e o fallback estiver habilitado, retorna qualquer
       disponibilidade cadastrada do profissional, independentemente do weekday.

    O fallback foi mantido apenas para cenários específicos, como o endpoint
    by-service-date, em que é preferível retornar slots mesmo diante de cadastro
    inconsistente no banco.

    Parâmetros:
    - db: sessão assíncrona do SQLAlchemy.
    - professional_id: identificador do profissional.
    - target_date: data desejada para consulta dos horários.
    - fallback_to_any_weekday: quando True, tenta retornar qualquer janela
      do profissional se não houver correspondência exata de weekday.

    Retorno:
    - lista de objetos WeeklyAvailability.
    """
    weekday_python = target_date.weekday()      # 0=segunda ... 6=domingo
    weekday_iso = target_date.isoweekday()      # 1=segunda ... 7=domingo

    candidates = []
    for value in (weekday_python, weekday_iso):
        if value not in candidates:
            candidates.append(value)

    windows_result = await db.execute(
        select(WeeklyAvailability).where(
            WeeklyAvailability.professional_id == professional_id,
            WeeklyAvailability.weekday.in_(candidates),
        ).order_by(WeeklyAvailability.start_time.asc())
    )
    windows = windows_result.scalars().all()

    if windows:
        return windows

    if fallback_to_any_weekday:
        fallback_result = await db.execute(
            select(WeeklyAvailability).where(
                WeeklyAvailability.professional_id == professional_id,
            ).order_by(WeeklyAvailability.start_time.asc())
        )
        return fallback_result.scalars().all()

    return []


async def list_day_slots(db: AsyncSession, professional_id, service_id, target_date):
    """
    Calcula os slots disponíveis de um profissional para um serviço em uma data.

    Regras aplicadas:
    - valida se o serviço pertence ao profissional;
    - busca as janelas de disponibilidade semanal compatíveis com a data;
    - busca agendamentos ativos no dia para evitar conflitos;
    - respeita a antecedência mínima configurada em booking_min_notice_minutes;
    - avança os horários usando o tamanho padrão de slot definido em settings.

    Importante:
    Esta função é a regra padrão do projeto para consulta de horários.
    Por isso, ela aplica min_notice e não faz fallback amplo de weekday.

    Parâmetros:
    - db: sessão assíncrona do SQLAlchemy.
    - professional_id: identificador do profissional.
    - service_id: identificador do serviço.
    - target_date: data em que os slots devem ser calculados.

    Retorno:
    - lista de dicionários no formato:
      {
          "start": datetime ISO,
          "end": datetime ISO,
          "label": "HH:MM"
      }

    Exceções:
    - HTTPException(400): quando o serviço não pertence ao profissional.
    """
    professional = await get_professional(db, professional_id)
    service = await get_service(db, service_id)

    if service.professional_id != professional.id:
        raise HTTPException(status_code=400, detail="Serviço não pertence ao profissional")

    windows = await _get_windows_for_date(
        db,
        professional.id,
        target_date,
        fallback_to_any_weekday=False,
    )

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


async def _list_day_slots_by_service_date(db: AsyncSession, professional_id, service_id, target_date):
    """
    Calcula slots para o endpoint by-service-date.

    Diferença principal em relação a list_day_slots:
    - permite fallback para qualquer weekday cadastrado do profissional;
    - não aplica a regra de antecedência mínima (min_notice).

    Motivo:
    O endpoint by-service-date foi ajustado para continuar retornando
    horários em cenários onde o cadastro de weekday esteja inconsistente
    no banco, sem alterar o comportamento padrão das demais rotas.

    Parâmetros:
    - db: sessão assíncrona do SQLAlchemy.
    - professional_id: identificador do profissional.
    - service_id: identificador do serviço.
    - target_date: data consultada.

    Retorno:
    - lista de slots disponíveis para o endpoint by-service-date.
    """
    professional = await get_professional(db, professional_id)
    service = await get_service(db, service_id)

    if service.professional_id != professional.id:
        return []

    windows = await _get_windows_for_date(
        db,
        professional.id,
        target_date,
        fallback_to_any_weekday=True,
    )

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

    for window in windows:
        cursor = datetime.combine(target_date, window.start_time).replace(tzinfo=TZ)
        window_end = datetime.combine(target_date, window.end_time).replace(tzinfo=TZ)

        while cursor + duration <= window_end:
            candidate_end = cursor + duration
            overlaps = any(a.starts_at < candidate_end and a.ends_at > cursor for a in appointments)

            if not overlaps:
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
    """
    Cria um novo agendamento.

    Validações executadas:
    - o serviço precisa pertencer ao profissional;
    - o horário precisa estar dentro da disponibilidade semanal cadastrada;
    - não pode existir conflito com outro agendamento ativo.

    Fluxo:
    1. Busca profissional e serviço.
    2. Monta starts_at e ends_at usando a duração do serviço.
    3. Valida se o horário está contido em uma janela semanal.
    4. Valida conflitos de agenda.
    5. Cria e persiste o Appointment.

    Parâmetros:
    - db: sessão assíncrona do SQLAlchemy.
    - payload: schema com os dados do agendamento.

    Retorno:
    - objeto Appointment persistido.

    Exceções:
    - HTTPException(400): serviço não pertence ao profissional.
    - HTTPException(400): horário fora da disponibilidade semanal.
    - HTTPException(409): conflito de horário detectado.
    """
    professional = await get_professional(db, payload.professional_id)
    service = await get_service(db, payload.service_id)

    if service.professional_id != professional.id:
        raise HTTPException(status_code=400, detail="Serviço não pertence ao profissional")

    starts_at = datetime.combine(payload.appointment_date, payload.appointment_time).replace(tzinfo=TZ)
    ends_at = starts_at + timedelta(minutes=service.duration_minutes)

    weekday_python = payload.appointment_date.weekday()
    weekday_iso = payload.appointment_date.isoweekday()
    weekday_candidates = []
    for value in (weekday_python, weekday_iso):
        if value not in weekday_candidates:
            weekday_candidates.append(value)

    availability_result = await db.execute(
        select(WeeklyAvailability).where(
            WeeklyAvailability.professional_id == professional.id,
            WeeklyAvailability.weekday.in_(weekday_candidates),
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
    """
    Remarca um agendamento existente.

    Regras:
    - o agendamento precisa existir;
    - o novo horário não pode conflitar com outro agendamento ativo
      do mesmo profissional;
    - o próprio agendamento atual é desconsiderado na busca de conflito.

    Fluxo:
    1. Busca o agendamento pelo id.
    2. Busca o serviço para obter a duração.
    3. Calcula novo intervalo de início e fim.
    4. Verifica conflito de agenda.
    5. Atualiza datas e marca o status como "rescheduled".

    Parâmetros:
    - db: sessão assíncrona do SQLAlchemy.
    - payload: schema com id do agendamento e nova data/hora.

    Retorno:
    - objeto Appointment atualizado.

    Exceções:
    - HTTPException(404): agendamento não encontrado.
    - HTTPException(409): novo horário conflita com outro agendamento.
    """
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
    """
    Cancela um agendamento existente.

    Em vez de excluir o registro do banco, a função apenas altera
    o status para "cancelled", preservando histórico e rastreabilidade.

    Parâmetros:
    - db: sessão assíncrona do SQLAlchemy.
    - appointment_id: identificador do agendamento.

    Retorno:
    - objeto Appointment atualizado.

    Exceções:
    - HTTPException(404): agendamento não encontrado.
    """
    result = await db.execute(select(Appointment).where(Appointment.id == appointment_id))
    appointment = result.scalar_one_or_none()

    if not appointment:
        raise HTTPException(status_code=404, detail="Agendamento não encontrado")

    appointment.status = "cancelled"

    await db.commit()
    await db.refresh(appointment)
    return appointment


async def get_availability_by_service_date(db: AsyncSession, service_name: str, target_date):
    """
    Retorna a disponibilidade agrupada por serviço e data.

    Este endpoint foi pensado para receber apenas:
    - service_name
    - target_date

    Regra principal:
    - o profissional correto é resolvido a partir de Service.professional_id;
    - a consulta ignora profissionais que não estejam vinculados ao serviço;
    - os slots são calculados por uma função auxiliar específica para este caso.

    Fluxo:
    1. Busca todos os serviços ativos com o nome informado.
    2. Junta com o profissional ativo vinculado ao serviço.
    3. Para cada par serviço/profissional, calcula slots da data.
    4. Soma o total geral e retorna a estrutura final.

    Parâmetros:
    - db: sessão assíncrona do SQLAlchemy.
    - service_name: nome do serviço informado na query string.
    - target_date: data desejada para consulta.

    Retorno:
    - dicionário no formato:
      {
          "service_name": str,
          "date": "YYYY-MM-DD",
          "total": int,
          "professionals": [
              {
                  "professional_id": str,
                  "display_name": str,
                  "service_id": str,
                  "service_name": str,
                  "slots": list,
                  "total": int
              }
          ]
      }

    Exceções:
    - HTTPException(404): quando nenhum serviço ativo com o nome informado é encontrado.
    """
    normalized_name = service_name.strip().lower()

    result = await db.execute(
        select(Service, Professional)
        .join(Professional, Professional.id == Service.professional_id)
        .where(
            func.lower(Service.name) == normalized_name,
            Service.is_active.is_(True),
            Professional.is_active.is_(True),
        )
        .order_by(Professional.display_name.asc(), Service.created_at.asc(), Service.id.asc())
    )

    rows = result.all()

    if not rows:
        raise HTTPException(status_code=404, detail="Serviço não encontrado")

    professionals = []
    total_slots = 0
    seen = set()

    for service, professional in rows:
        key = (service.id, professional.id)
        if key in seen:
            continue
        seen.add(key)

        slots = await _list_day_slots_by_service_date(
            db,
            professional.id,
            service.id,
            target_date,
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


async def get_id_service_by_name(db: AsyncSession, nameservice: str):
    """
    Retorna os IDs dos serviços ativos filtrando pelo nome.

    Regras:
    - busca parcial (ILIKE) para permitir flexibilidade;
    - considera apenas serviços ativos;
    - retorna lista de IDs em formato string.

    Parâmetros:
    - db: sessão do banco
    - nameservice: nome (ou parte do nome) do serviço

    Retorno:
    - dict com total, lista e versões formatadas
    """
    result = await db.execute(
        select(Service)
        .where(Service.is_active.is_(True))
        .where(Service.name.ilike(f"%{nameservice}%"))
        .order_by(Service.name.asc())
    )

    services = result.scalars().all()

    slots = [str(service.id) for service in services]

    return {
        "total": len(slots),
        "slots": slots,
        "slots_text": ", ".join(slots),
        "slots_list": "\n".join([f"- {slot}" for slot in slots])
    }


async def get_id_professional_by_name(db: AsyncSession, nameprofessional: str):
    """
    Retorna os IDs dos profissionais ativos filtrando pelo nome.

    Regras:
    - busca parcial (ILIKE);
    - considera apenas profissionais ativos;
    - utiliza display_name.

    Parâmetros:
    - db: sessão do banco
    - nameprofessional: nome (ou parte do nome)

    Retorno:
    - dict com total e listas formatadas
    """
    result = await db.execute(
        select(Professional)
        .where(Professional.is_active.is_(True))
        .where(Professional.display_name.ilike(f"%{nameprofessional}%"))
        .order_by(Professional.display_name.asc())
    )

    professionals = result.scalars().all()

    slots = [str(prof.id) for prof in professionals]

    return {
        "total": len(slots),
        "slots": slots,
        "slots_text": ", ".join(slots),
        "slots_list": "\n".join([f"- {slot}" for slot in slots])
    }