create extension if not exists pgcrypto;

create table if not exists public.users (
    id uuid primary key default gen_random_uuid(),
    username varchar(80) not null unique,
    full_name varchar(150) not null,
    email varchar(150) unique,
    password_hash varchar(255) not null,
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.professionals (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references public.users(id) on delete cascade,
    display_name varchar(120) not null,
    timezone varchar(80) not null default 'America/Sao_Paulo',
    is_active boolean not null default true,
    created_at timestamptz not null default now()
);

create table if not exists public.services (
    id uuid primary key default gen_random_uuid(),
    professional_id uuid not null references public.professionals(id) on delete cascade,
    name varchar(120) not null,
    description text,
    duration_minutes integer not null check (duration_minutes > 0),
    price numeric(10,2),
    is_active boolean not null default true,
    created_at timestamptz not null default now()
);

create table if not exists public.weekly_availabilities (
    id uuid primary key default gen_random_uuid(),
    professional_id uuid not null references public.professionals(id) on delete cascade,
    weekday integer not null check (weekday between 0 and 6),
    start_time time not null,
    end_time time not null,
    created_at timestamptz not null default now(),
    constraint ck_weekly_window check (start_time < end_time),
    constraint uq_weekly_availability_slot unique (professional_id, weekday, start_time, end_time)
);

create table if not exists public.appointments (
    id uuid primary key default gen_random_uuid(),
    professional_id uuid not null references public.professionals(id) on delete cascade,
    service_id uuid not null references public.services(id) on delete restrict,
    customer_name varchar(120) not null,
    customer_phone varchar(30),
    customer_email varchar(150),
    status varchar(20) not null default 'scheduled',
    notes text,
    starts_at timestamptz not null,
    ends_at timestamptz not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint ck_appointment_window check (starts_at < ends_at),
    constraint ck_appointment_status check (status in ('scheduled', 'rescheduled', 'cancelled', 'completed')),
    constraint uq_appointment_professional_start unique (professional_id, starts_at)
);

create index if not exists idx_professionals_user_id on public.professionals(user_id);
create index if not exists idx_services_professional_id on public.services(professional_id);
create index if not exists idx_weekly_professional_weekday on public.weekly_availabilities(professional_id, weekday);
create index if not exists idx_appointments_professional_starts_at on public.appointments(professional_id, starts_at);
create index if not exists idx_appointments_service_id on public.appointments(service_id);

create or replace function public.handle_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists trg_users_updated_at on public.users;
create trigger trg_users_updated_at
before update on public.users
for each row execute function public.handle_updated_at();

drop trigger if exists trg_appointments_updated_at on public.appointments;
create trigger trg_appointments_updated_at
before update on public.appointments
for each row execute function public.handle_updated_at();

alter table public.users enable row level security;
alter table public.professionals enable row level security;
alter table public.services enable row level security;
alter table public.weekly_availabilities enable row level security;
alter table public.appointments enable row level security;

drop policy if exists service_role_all_users on public.users;
create policy service_role_all_users on public.users
for all
using (auth.role() = 'service_role')
with check (auth.role() = 'service_role');

drop policy if exists service_role_all_professionals on public.professionals;
create policy service_role_all_professionals on public.professionals
for all
using (auth.role() = 'service_role')
with check (auth.role() = 'service_role');

drop policy if exists service_role_all_services on public.services;
create policy service_role_all_services on public.services
for all
using (auth.role() = 'service_role')
with check (auth.role() = 'service_role');

drop policy if exists service_role_all_weekly_availabilities on public.weekly_availabilities;
create policy service_role_all_weekly_availabilities on public.weekly_availabilities
for all
using (auth.role() = 'service_role')
with check (auth.role() = 'service_role');

drop policy if exists service_role_all_appointments on public.appointments;
create policy service_role_all_appointments on public.appointments
for all
using (auth.role() = 'service_role')
with check (auth.role() = 'service_role');
