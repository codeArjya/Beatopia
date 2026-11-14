-- 001_init: CONTRACT §3, copied verbatim. Applied by scripts/db_init.py.

create extension if not exists vector;

create table tracks (
  id text primary key,
  source text not null check (source in ('freesound','jamendo','fma','ccmixter','archive','import')),
  source_id text,
  source_url text,
  title text not null,
  artist text,
  license text not null,            -- e.g. 'CC0', 'CC-BY-4.0', 'CC-BY-SA-3.0', 'CC-BY-NC-4.0'
  attribution text not null default '',
  duration_s real not null,
  bpm real,
  key text,                          -- e.g. 'A minor', 'F# major'
  beat_times real[] not null default '{}',
  audio_path text not null,          -- storage path of mix.mp3
  is_hero boolean not null default false,
  created_at timestamptz not null default now()
);

create table windows (
  id text primary key,
  track_id text not null references tracks(id) on delete cascade,
  stem text not null default 'mix',  -- mix|vocals|drums|bass|other|guitar|piano
  start_s real not null,
  end_s real not null,
  embedding vector(512) not null,    -- L2-normalized CLAP audio embedding
  tags text[] not null default '{}',
  tag_scores jsonb not null default '{}',
  loopability real not null default 0,   -- 0..1, higher = more regular onsets across bars
  rms real not null default 0,
  density real not null default 0.5      -- 0..1, lower = sparser (fewer things playing)
);
create index windows_track_idx on windows(track_id);
create index windows_tags_idx on windows using gin(tags);

create table stems (
  track_id text not null references tracks(id) on delete cascade,
  stem text not null,
  range_start_s real not null default 0,
  range_end_s real not null,
  path text not null,
  model text not null,
  primary key (track_id, stem, range_start_s, range_end_s)
);

create table notes (
  window_id text primary key references windows(id) on delete cascade,
  text text not null,
  model text not null,
  created_at timestamptz not null default now()
);

create table jobs (
  id uuid primary key default gen_random_uuid(),
  kind text not null check (kind in ('stems','analyze')),
  status text not null default 'queued' check (status in ('queued','running','done','error')),
  progress real not null default 0,
  input jsonb not null,
  output jsonb,
  error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index jobs_queue_idx on jobs(status, created_at);

create table events (
  id bigserial primary key,
  session_id text not null,
  query_id text,
  window_id text,
  action text not null check (action in ('play','pick','export','skip')),
  created_at timestamptz not null default now()
);

create table plan_cache (
  hash text primary key,
  plan jsonb not null,
  created_at timestamptz not null default now()
);
