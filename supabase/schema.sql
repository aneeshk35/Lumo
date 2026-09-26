-- Lumo: everything the app keeps. The game server is the only client.
--
-- The Python server hashes passwords (PBKDF2) and talks to these tables with
-- the secret key, which lives only in Render's environment. Row level security
-- is on for every table with no policies, so Supabase's public keys can read
-- and write nothing.
--
-- Apply: Supabase dashboard -> SQL Editor -> New query -> paste this -> Run.
-- Safe to run again; it only adds what is missing.

-- ---------- accounts ----------
create table if not exists public.lumo_accounts (
  username     text primary key,            -- lowercase, unique
  display      text not null,               -- as typed at signup
  pass_hash    text not null,               -- pbkdf2_sha256$rounds$salt$hash
  profile      jsonb not null default '{}'::jsonb,
  rev          integer not null default 0,  -- bumps on every save; stale saves are refused
  ratings      jsonb not null default '{}'::jsonb,  -- Elo per difficulty, wins, losses (server-owned)
  ratings_rev  integer not null default 0,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);
alter table public.lumo_accounts add column if not exists ratings jsonb not null default '{}'::jsonb;
alter table public.lumo_accounts add column if not exists ratings_rev integer not null default 0;

create table if not exists public.lumo_sessions (
  token_hash   text primary key,            -- sha256 of the sign-in token; the token itself is never stored
  username     text not null references public.lumo_accounts(username) on delete cascade,
  expires_at   bigint not null              -- unix seconds
);
create index if not exists lumo_sessions_expiry on public.lumo_sessions (expires_at);

-- ---------- classes and tutor applications ----------
-- Members are identified by a hash of their browser's player key, never the key.
create table if not exists public.lumo_classes (
  code         text primary key,
  data         jsonb not null,
  updated_at   timestamptz not null default now()
);

create table if not exists public.lumo_tutors (
  player_id    text primary key,
  data         jsonb not null,              -- includes the applicant's email
  updated_at   timestamptz not null default now()
);

-- ---------- high scores ----------
create table if not exists public.lumo_highscores (
  id           bigserial primary key,
  name         text not null,
  score        integer not null,
  correct      integer not null,
  total        integer not null,
  section      text not null,
  date         text not null,
  created_at   timestamptz not null default now()
);
create index if not exists lumo_highscores_top on public.lumo_highscores (score desc);

-- ---------- lock everything down ----------
alter table public.lumo_accounts   enable row level security;
alter table public.lumo_sessions   enable row level security;
alter table public.lumo_classes    enable row level security;
alter table public.lumo_tutors     enable row level security;
alter table public.lumo_highscores enable row level security;

-- Belt and braces: the public roles get no table privileges at all.
revoke all on public.lumo_accounts, public.lumo_sessions, public.lumo_classes,
              public.lumo_tutors, public.lumo_highscores from anon, authenticated;
revoke all on sequence public.lumo_highscores_id_seq from anon, authenticated;
