-- Supabase SQL for email alerts only.
-- À coller dans Supabase > SQL Editor > New query > Run.

create extension if not exists pgcrypto;

-- Email alert filters created from the public dashboard.
create table if not exists public.alert_filters (
  id uuid primary key default gen_random_uuid(),
  created_at timestamp with time zone default now(),
  updated_at timestamp with time zone default now(),
  email text not null,
  label text,
  keywords jsonb not null default '[]'::jsonb,
  match_mode text not null default 'any' check (match_mode in ('any', 'all')),
  scope text not null default 'all' check (scope in ('all', 'top_100', 'national', 'local')),
  active boolean not null default true,
  last_checked_at timestamp with time zone default now(),
  constraint alert_filters_email_shape check (email ~* '^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$'),
  constraint alert_filters_keywords_array check (jsonb_typeof(keywords) = 'array'),
  constraint alert_filters_keywords_size check (jsonb_array_length(keywords) between 1 and 12)
);

create table if not exists public.alert_deliveries (
  filter_id uuid not null references public.alert_filters(id) on delete cascade,
  article_uid text not null references public.articles(uid) on delete cascade,
  sent_at timestamp with time zone default now(),
  primary key (filter_id, article_uid)
);

create index if not exists idx_alert_filters_active on public.alert_filters(active, last_checked_at);
create index if not exists idx_alert_deliveries_filter on public.alert_deliveries(filter_id, sent_at desc);

alter table public.alert_filters enable row level security;
alter table public.alert_deliveries enable row level security;

drop policy if exists "Public create alert filters" on public.alert_filters;
create policy "Public create alert filters"
on public.alert_filters
for insert
to anon
with check (
  active = true
  and jsonb_typeof(keywords) = 'array'
  and jsonb_array_length(keywords) between 1 and 12
  and match_mode in ('any', 'all')
  and scope in ('all', 'top_100', 'national', 'local')
);

-- Alert filters and deliveries stay private after creation. GitHub Actions uses service_role.
grant insert on public.alert_filters to anon;
grant select, insert, update, delete on public.alert_filters to service_role;
grant select, insert, update, delete on public.alert_deliveries to service_role;

