# Game Scout — Architecture & Rules

## Purpose
Game Scout collects external signals (Steam, SteamSpy, Reddit, TikTok, YouTube),
calculates trends, scores games and pitches, and shows results in dashboards.

## High-level structure

apps/
- api/        — FastAPI (HTTP API + dashboards)
- worker/     — background processing (Celery)
  - collectors/  — data collection
  - analysis/    — trend & narrative analysis
  - scoring/     — investment scoring logic
  - tasks/       — Celery tasks

docker/
- api.Dockerfile
- worker.Dockerfile

migrations/
- Alembic migrations (ONLY source of DB schema)

## Runtime
- Docker Compose is the source of truth
- Local DB data must NOT be committed
- All environments are reproducible from code

## Non-negotiable rules (IMPORTANT)
1. Do NOT rewrite large parts of the project.
2. Changes must be SMALL and LOCAL (1–3 files).
3. Do NOT change DB schema without a migration.
4. Prefer diffs instead of full file rewrites.
5. Keep everything runnable via docker compose.

## How to test changes
- docker compose up --build
- If something fails:
  - docker compose logs --no-color api
  - docker compose logs --no-color worker

## Environment
- Real secrets live in `.env` (never commit)
- `.env.example` is the contract
