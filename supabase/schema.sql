-- Lumo: accounts and saved progress.
--
-- The Python game server owns sign-in: it hashes passwords (PBKDF2) and talks
-- to these tables with the service key, which never leaves Render. Row level
-- security is on with no policies, so the public anon key can read nothing.
--
-- Apply once: Supabase dashboard -> SQL Editor -> paste this -> Run.
-- Safe to run again.

create table if not exists public.lumo_accounts (
  username    text primary key,          -- lowercase, unique
  display     text not null,             -- as typed at signup
  pass_hash   text not null,
  profile     jsonb not null default '{}'::jsonb,
  rev         integer not null default 0, -- bumps on every save; stale saves are refused
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

create table if not exists public.lumo_sessions (
  token_hash  text primary key,          -- sha256 of the sign-in token
  username    text not null references public.lumo_accounts(username) on delete cascade,
  expires_at  bigint not null            -- unix seconds
);
create index if not exists lumo_sessions_expiry on public.lumo_sessions (expires_at);

alter table public.lumo_accounts enable row level security;
alter table public.lumo_sessions enable row level security;
