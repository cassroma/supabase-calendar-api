create extension if not exists pgcrypto;

create table if not exists public.patients (
    id uuid primary key default gen_random_uuid(),
    full_name varchar(120) not null,
    phone varchar(30) not null,
    phone_normalized varchar(20) not null unique,
    email varchar(150),
    notes text,
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

alter table if exists public.appointments
    add column if not exists patient_id uuid references public.patients(id) on delete restrict;

create index if not exists idx_patients_phone on public.patients(phone);
create index if not exists idx_patients_phone_normalized on public.patients(phone_normalized);
create index if not exists idx_appointments_patient_id on public.appointments(patient_id);

create or replace function public.handle_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists trg_patients_updated_at on public.patients;
create trigger trg_patients_updated_at
before update on public.patients
for each row execute function public.handle_updated_at();

alter table public.patients enable row level security;

drop policy if exists service_role_all_patients on public.patients;
create policy service_role_all_patients on public.patients
for all
using (auth.role() = 'service_role')
with check (auth.role() = 'service_role');

insert into public.patients (full_name, phone, phone_normalized, email, notes, is_active)
select distinct on (regexp_replace(coalesce(a.customer_phone, ''), '[^0-9]', '', 'g'))
    a.customer_name,
    a.customer_phone,
    regexp_replace(coalesce(a.customer_phone, ''), '[^0-9]', '', 'g') as phone_normalized,
    a.customer_email,
    a.notes,
    true
from public.appointments a
where coalesce(regexp_replace(coalesce(a.customer_phone, ''), '[^0-9]', '', 'g'), '') <> ''
on conflict (phone_normalized) do update
set
    full_name = excluded.full_name,
    phone = excluded.phone,
    email = excluded.email,
    notes = excluded.notes;

update public.appointments a
set patient_id = p.id
from public.patients p
where a.customer_phone is not null
  and regexp_replace(a.customer_phone, '[^0-9]', '', 'g') = p.phone_normalized
  and a.patient_id is null;
