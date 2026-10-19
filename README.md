# FitBuddy

AI-generated 7-day workout plans and goal-specific nutrition/recovery tips.
FastAPI + Google Gemini + SQLite (SQLAlchemy ORM) with a Jinja2 HTML interface.

```
User (Browser)
   └─ FastAPI backend (app/main.py)
        ├─ HTML templating (Jinja2 + CSS)  → index.html (form) · result.html (plan) · all_users.html (admin)
        ├─ Workout logic (routes.py + AI)
        ├─ Gemini 1.5 Pro & 1.5 Flash API  (app/updated_plan.py)
        └─ SQLite + SQLAlchemy ORM         (fitbuddy.db → users, plans)
```

## Run it

```bash
pip install -r requirements.txt
cp .env.example .env            # optional: add GEMINI_API_KEY
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000 — tables are created automatically on first start.

**Gemini:** set `GEMINI_API_KEY` (from Google AI Studio) to generate plans with Gemini
1.5 Flash, falling back to 1.5 Pro. Without a key the app still works end to end using a
deterministic local generator (the plan page labels the source), so the UI, database and
feedback loop are always testable. Override models with `GEMINI_MODEL` /
`GEMINI_MODEL_FALLBACK`.

## Scenarios → where they live

| Scenario | Route | Behaviour |
|---|---|---|
| 1. Personal details → 7-day plan | `GET /` · `POST /generate` · `POST /api/generate` | Validated on client and server, plan stored per user |
| 2. Feedback → regenerated plan | `POST /plan/{id}/feedback` · `POST /api/feedback` | Suggestion is sent back to the model with the profile, plan updated in place |
| 3. Nutrition / recovery tip | `GET /api/tip?goal=…` · shown on every plan page | Goal-matched tip from Gemini, curated list as backstop |
| Admin | `GET /admin/users` · `GET /api/users` | All stored users with links to their latest plan |

## API

| Method | Path | Body / params |
|---|---|---|
| `POST` | `/api/generate` | `{name, age, weight, goal, intensity}` → user + 7-day plan + tip |
| `POST` | `/api/feedback` | `{user_id, feedback}` → regenerated plan |
| `GET` | `/api/tip` | `?goal=weight loss\|muscle gain\|general wellness` |
| `GET` | `/api/users` · `/api/users/{id}` | profiles (+ latest plan) |
| `GET` | `/api/plans/{user_id}` | latest stored plan |
| `GET` | `/api/health` | liveness |

Validation rejects out-of-range age (13–100), weight (30–300 kg), unknown goals or
intensities with `422` and a field-level `detail` list. Interactive docs at `/docs`.

## Validation

- **Frontend** — `static/js/main.js` checks the intake form inline (per-field messages,
  focus moves to the first invalid control) before any request is sent.
- **Backend** — the same rules in `app/schemas.py` (pydantic) drive both the JSON API and
  the HTML form flow, which re-renders the form with friendly messages and the values you
  typed (HTTP 422, PRG on success).

## Error handling & logging

Structured logging (`fitbuddy.*` loggers) covers rejected inputs, generation source,
Gemini failures and unhandled errors. Handlers return JSON `{"detail": …}` for 404/422/500;
Gemini failures are logged as warnings and degrade to the local generator instead of 500s.

## Tests

```bash
python -m pytest tests -q
```

23 tests cover every endpoint (generate, feedback, tips, retrieval, 404/422 paths) and the
UI flows (form render, invalid re-render, valid redirect, day-wise plan page, feedback
regeneration, admin list, static assets) against a throwaway `fitbuddy_test.db`.

## Project layout

```
app/
  main.py          app factory · logging · error handlers · static mount
  routes.py        HTML: intake form, plan page, feedback, admin
  api.py           JSON API
  service.py       shared business logic (create / regenerate / retrieve)
  updated_plan.py  Gemini prompts, JSON parsing, local fallback generator + tips
  models.py        SQLAlchemy: users, plans
  schemas.py       pydantic validation
  database.py      engine/session (SQLite)
templates/         index · result · all_users (Jinja2)
static/            style.css · main.js
tests/             pytest suite
```
