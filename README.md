# Agenda API com FastAPI + Supabase

Projeto pronto para rodar 100% online, sem Docker, usando FastAPI como API web e Supabase Postgres como banco de dados.

## O que esta versão entrega

- cadastro e login com JWT
- proteção por API Key no header `X-API-Key`
- cadastro de profissionais
- cadastro de serviços
- cadastro de disponibilidade semanal
- consulta de horários disponíveis
- criação de agendamentos
- remarcação de agendamentos
- cancelamento de agendamentos
- prevenção de conflito de horário

## Estrutura

```text
app/
  api/
  core/
  db/
  models/
  schemas/
  services/
sql/
main.py
run.py
.env.example
requirements.txt
```

## Como subir online

1. Crie um projeto no Supabase.
2. No SQL Editor do Supabase, execute o arquivo `sql/supabase_schema.sql`.
3. Faça deploy da API em um host Python online, como Railway, Render, Fly.io ou VPS.
4. Configure as variáveis do `.env.example` no ambiente.
5. Instale as dependências com `pip install -r requirements.txt`.
6. Inicie com `python run.py`.

## Endpoints principais

- `POST /auth/register`
- `POST /auth/login`
- `POST /calendar/professionals`
- `POST /calendar/services`
- `POST /calendar/availability`
- `GET /calendar/services`
- `GET /calendar/availability`
- `POST /calendar/appointments`
- `POST /calendar/appointments/reschedule`
- `POST /calendar/appointments/cancel`

## Fluxo de autenticação para cURL

### 1) Criar usuário

```bash
curl -X POST "https://SUA_API/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "full_name": "Administrador",
    "email": "admin@empresa.com",
    "password": "SenhaForte123"
  }'
```

### 2) Fazer login e receber token

```bash
curl -X POST "https://SUA_API/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "password": "SenhaForte123"
  }'
```

### 3) Criar profissional

```bash
curl -X POST "https://SUA_API/calendar/professionals" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: SUA_API_KEY" \
  -H "Authorization: Bearer SEU_TOKEN" \
  -d '{
    "user_id": "UUID_DO_USUARIO",
    "display_name": "Dra. Maria",
    "timezone": "America/Sao_Paulo"
  }'
```

### 4) Criar serviço

```bash
curl -X POST "https://SUA_API/calendar/services" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: SUA_API_KEY" \
  -H "Authorization: Bearer SEU_TOKEN" \
  -d '{
    "professional_id": "UUID_DO_PROFISSIONAL",
    "name": "Consulta",
    "description": "Consulta inicial",
    "duration_minutes": 60,
    "price": 150
  }'
```

### 5) Cadastrar disponibilidade semanal

```bash
curl -X POST "https://SUA_API/calendar/availability" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: SUA_API_KEY" \
  -H "Authorization: Bearer SEU_TOKEN" \
  -d '{
    "professional_id": "UUID_DO_PROFISSIONAL",
    "weekday": 0,
    "start_time": "08:00:00",
    "end_time": "18:00:00"
  }'
```

### 6) Consultar horários disponíveis

```bash
curl "https://SUA_API/calendar/availability?professional_id=UUID_DO_PROFISSIONAL&service_id=UUID_DO_SERVICO&target_date=2026-04-10" \
  -H "X-API-Key: SUA_API_KEY"
```

### 7) Agendar

```bash
curl -X POST "https://SUA_API/calendar/appointments" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: SUA_API_KEY" \
  -d '{
    "professional_id": "UUID_DO_PROFISSIONAL",
    "service_id": "UUID_DO_SERVICO",
    "appointment_date": "2026-04-10",
    "appointment_time": "09:00:00",
    "customer_name": "João Silva",
    "customer_phone": "+5534999999999",
    "customer_email": "joao@email.com",
    "notes": "Primeira consulta"
  }'
```

### 8) Remarcar

```bash
curl -X POST "https://SUA_API/calendar/appointments/reschedule" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: SUA_API_KEY" \
  -d '{
    "appointment_id": "UUID_DO_AGENDAMENTO",
    "new_date": "2026-04-11",
    "new_time": "10:00:00"
  }'
```

### 9) Cancelar

```bash
curl -X POST "https://SUA_API/calendar/appointments/cancel" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: SUA_API_KEY" \
  -d '{
    "appointment_id": "UUID_DO_AGENDAMENTO",
    "reason": "Solicitação do cliente"
  }'
```

## Observações de produção

- Use uma `JWT_SECRET_KEY` longa.
- Restrinja `CORS_ORIGINS` ao seu domínio em produção.
- Prefira armazenar `API_KEY` e segredos apenas no painel do host.
- Para alta escala, depois você pode adicionar migrations com Alembic e logs estruturados.
