create extension if not exists pgcrypto;

-- profiles table
create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  display_name text,
  role text default 'user',
  created_at timestamptz default now()
);

-- reports table
create table if not exists public.reports (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references public.profiles(id) on delete cascade,
  title text not null,
  description text,
  category text not null check (category in ('Plastic','Sewage','Air','Noise','Other')),
  severity text not null check (severity in ('Low','Medium','High')),
  lat double precision not null,
  lon double precision not null,
  address text,
  image_url text not null,
  thumb_url text not null,
  status text not null default 'Open' check (status in ('Open','Under Review','Resolved')),
  created_at timestamptz default now()
);

-- status history table
create table if not exists public.report_status_history (
  id bigserial primary key,
  report_id uuid references public.reports(id) on delete cascade,
  changed_by uuid references public.profiles(id),
  from_status text,
  to_status text,
  changed_at timestamptz default now()
);

-- Enable RLS
alter table public.profiles enable row level security;
alter table public.reports enable row level security;
alter table public.report_status_history enable row level security;

-- Policies (NO IF NOT EXISTS ALLOWED)
create policy "profiles_self_select"
  on public.profiles for select
  using (auth.uid() = id);

create policy "profiles_admin_select"
  on public.profiles for select
  using (exists (
    select 1 from public.profiles p
    where p.id = auth.uid() and p.role in ('admin','moderator')
  ));

create policy "reports_insert_own"
  on public.reports for insert
  with check (auth.uid() = user_id);

create policy "reports_public_select"
  on public.reports for select
  using (true);

create policy "reports_owner_update_open"
  on public.reports for update
  using (auth.uid() = user_id and status = 'Open');

create policy "reports_owner_delete_open"
  on public.reports for delete
  using (auth.uid() = user_id and status = 'Open');

create policy "reports_admin_update"
  on public.reports for update
  using (exists (
    select 1 from public.profiles p
    where p.id = auth.uid() and p.role in ('admin','moderator')
  ));

create policy "history_admin_read"
  on public.report_status_history for select
  using (exists (
    select 1 from public.profiles p
    where p.id = auth.uid() and p.role in ('admin','moderator')
  ));

create policy "history_insert_any"
  on public.report_status_history for insert
  with check (true);

-- Rate limit function
create or replace function public.can_submit_report(p_user_id uuid)
returns boolean
language plpgsql
as $$
begin
  return (
    select count(*) from public.reports
    where user_id = p_user_id
      and created_at > now() - interval '1 hour'
  ) < 5;
end;
$$;

-- Status transition function
create or replace function public.set_report_status(
  p_report_id uuid,
  p_new_status text,
  p_changed_by uuid
)
returns void
language plpgsql
as $$
declare
  v_old text;
begin
  select status into v_old from public.reports
  where id = p_report_id;

  if v_old is null then
    raise exception 'Report not found';
  end if;

  if p_new_status not in ('Open','Under Review','Resolved') then
    raise exception 'Invalid status';
  end if;

  if v_old = p_new_status then
    return;
  end if;

  update public.reports
  set status = p_new_status
  where id = p_report_id;

  insert into public.report_status_history
    (report_id, changed_by, from_status, to_status)
  values
    (p_report_id, p_changed_by, v_old, p_new_status);
end;
$$;