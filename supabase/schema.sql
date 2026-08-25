-- Lumo: accounts and durable progress.
--
-- The game engine (parties, duels, matchmaking) stays on the Python server.
-- This schema replaces what currently lives in each browser's localStorage,
-- so progress follows a player across devices instead of dying with the cache.
--
-- Apply with: supabase db push, or paste into the SQL editor.

-- ---------- profile, one row per auth user ----------
create table if not exists public.profiles (
  id           uuid primary key references auth.users on delete cascade,
  display_name text not null check (char_length(display_name) between 1 and 16),
  elo          int  not null default 1200,
  wins         int  not null default 0,
  losses       int  not null default 0,
  best_streak  int  not null default 0,
  test_date    date,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);

-- ---------- every answered question ----------
-- One row per attempt. Accuracy, per-domain mastery, and the mistake list are
-- all derived from this, so nothing needs to be kept in sync by hand.
create table if not exists public.attempts (
  id           bigserial primary key,
  user_id      uuid not null references public.profiles(id) on delete cascade,
  question_id  text not null,
  domain       text not null,
  skill        text not null,
  difficulty   text not null check (difficulty in ('easy','medium','hard')),
  chosen       smallint,          -- null when the timer ran out
  correct      boolean not null,
  points       int not null default 0,
  mode         text not null default 'solo',
  answered_at  timestamptz not null default now()
);
create index if not exists attempts_user_time on public.attempts (user_id, answered_at desc);
create index if not exists attempts_user_domain on public.attempts (user_id, domain);

-- Questions still open on the review list: most recent wrong attempt per
-- question, excluded once a later attempt got it right.
create or replace view public.open_mistakes as
select distinct on (a.user_id, a.question_id)
       a.user_id, a.question_id, a.domain, a.skill, a.difficulty,
       a.chosen, a.answered_at
from public.attempts a
order by a.user_id, a.question_id, a.answered_at desc;

-- ---------- leaderboard ----------
create table if not exists public.high_scores (
  id         bigserial primary key,
  user_id    uuid references public.profiles(id) on delete set null,
  name       text not null,
  score      int  not null,
  correct    int  not null,
  total      int  not null,
  section    text not null,
  created_at timestamptz not null default now()
);
create index if not exists high_scores_top on public.high_scores (score desc);

-- ---------- row level security ----------
-- Players read and write only their own rows. The leaderboard is world
-- readable but can only be written under your own user id.
alter table public.profiles    enable row level security;
alter table public.attempts    enable row level security;
alter table public.high_scores enable row level security;

drop policy if exists "own profile read"   on public.profiles;
drop policy if exists "own profile write"  on public.profiles;
drop policy if exists "own profile update" on public.profiles;
create policy "own profile read"   on public.profiles for select using (auth.uid() = id);
create policy "own profile write"  on public.profiles for insert with check (auth.uid() = id);
create policy "own profile update" on public.profiles for update using (auth.uid() = id);

drop policy if exists "own attempts read"  on public.attempts;
drop policy if exists "own attempts write" on public.attempts;
create policy "own attempts read"  on public.attempts for select using (auth.uid() = user_id);
create policy "own attempts write" on public.attempts for insert with check (auth.uid() = user_id);

drop policy if exists "scores are public"  on public.high_scores;
drop policy if exists "own score write"    on public.high_scores;
create policy "scores are public" on public.high_scores for select using (true);
create policy "own score write"   on public.high_scores for insert with check (auth.uid() = user_id);

-- ---------- create the profile row on signup ----------
create or replace function public.handle_new_user()
returns trigger language plpgsql security definer set search_path = public as $$
begin
  insert into public.profiles (id, display_name)
  values (new.id, coalesce(nullif(new.raw_user_meta_data->>'display_name', ''), 'Player'))
  on conflict (id) do nothing;
  return new;
end $$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();
