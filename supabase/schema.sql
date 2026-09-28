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

-- ---------- removed ----------
-- The all-time high score board is gone.
drop table if exists public.lumo_highscores;

-- ---------- question reports ----------
-- Players flag questions from the test screen. Read them in the Table Editor.
create table if not exists public.lumo_reports (
  id           bigserial primary key,
  question_id  text not null,
  reason       text not null,         -- wrong-answer | unclear | difficulty | display | other
  note         text not null default '',
  question     text not null,         -- snapshot, since generated variants aren't stored
  answer       text not null,
  difficulty   text not null,
  reporter     text not null,         -- hashed player key, never the key itself
  name         text not null default '',
  created_at   timestamptz not null default now()
);
create index if not exists lumo_reports_question on public.lumo_reports (question_id);

-- ---------- friends ----------
-- Friend codes, last-online times, and pending friend requests. Keyed by a hash
-- of the browser's player key, never the key.
create table if not exists public.lumo_presence (
  player_id    text primary key,
  code         text not null unique,        -- 6-character friend code
  name         text not null default '',
  elo          integer not null default 1200,
  last_seen    bigint not null default 0,   -- unix seconds
  requests     jsonb not null default '[]'::jsonb,  -- [{code, name, when}] waiting to be accepted
  updated_at   timestamptz not null default now()
);

-- ---------- lock everything down ----------
alter table public.lumo_accounts   enable row level security;
alter table public.lumo_sessions   enable row level security;
alter table public.lumo_classes    enable row level security;
alter table public.lumo_tutors     enable row level security;
alter table public.lumo_reports    enable row level security;
alter table public.lumo_presence   enable row level security;

-- Belt and braces: the public roles get no table privileges at all.
revoke all on public.lumo_accounts, public.lumo_sessions, public.lumo_classes,
              public.lumo_tutors, public.lumo_reports,
              public.lumo_presence from anon, authenticated;
revoke all on sequence public.lumo_reports_id_seq from anon, authenticated;
