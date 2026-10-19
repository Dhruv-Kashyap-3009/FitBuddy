"""HTML page routes: intake form, plan page, admin panel (Jinja2)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError
from sqlalchemy.orm import Session

from . import service
from .database import get_db
from .schemas import PlanRequest
from .templating import templates

logger = logging.getLogger("fitbuddy.routes")

router = APIRouter(include_in_schema=False)

EMPTY_FORM = {"name": "", "age": "", "weight": "", "goal": "weight loss", "intensity": "medium"}


def _coerce(value, caster):
    try:
        return caster(value)
    except (TypeError, ValueError):
        return None


def _form_errors(payload: dict) -> list[str]:
    try:
        PlanRequest(**payload)
    except ValidationError as exc:
        messages = []
        for err in exc.errors():
            field = ".".join(str(part) for part in err["loc"])
            raw = err["msg"]
            messages.append(f"{field}: {_friendly(field, raw, payload)}")
        return messages
    return []


def _friendly(field: str, raw: str, payload: dict) -> str:
    """Rewrite pydantic messages into the words the form uses."""
    if field == "age":
        if payload.get("age") is None:
            return "Age must be a whole number from 13 to 100."
        return "Age must be between 13 and 100."
    if field == "weight":
        if payload.get("weight") is None:
            return "Weight must be a number between 30 and 300 kg."
        return "Weight must be between 30 and 300 kg."
    if field == "goal":
        return "Choose weight loss, muscle gain or general wellness."
    if field == "intensity":
        return "Choose low, medium or high."
    if field == "name":
        return "Enter a name between 2 and 80 characters."
    return raw


@router.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)):
    """Intake form: collect name, age, weight, goal, intensity."""
    return templates.TemplateResponse(
        request,
        "index.html",
        {"form": EMPTY_FORM, "errors": []},
    )


@router.post("/generate", response_class=HTMLResponse)
def generate(
    request: Request,
    name: str = Form(""),
    age: str = Form(""),
    weight: str = Form(""),
    goal: str = Form(""),
    intensity: str = Form(""),
    db: Session = Depends(get_db),
):
    """Validate the form, create the user + plan, then redirect (PRG)."""
    payload = {
        "name": name,
        "age": _coerce(age, int),
        "weight": _coerce(weight, float),
        "goal": goal,
        "intensity": intensity,
    }
    errors = _form_errors(payload)
    if errors:
        logger.info("Rejected intake form: %s", errors)
        shown = {"name": name, "age": age, "weight": weight, "goal": goal, "intensity": intensity}
        return templates.TemplateResponse(
            request,
            "index.html",
            {"form": {**EMPTY_FORM, **shown}, "errors": errors},
            status_code=422,
        )

    user, record = service.create_user_with_plan(db, PlanRequest(**payload))
    return RedirectResponse(url=f"/plan/{record.id}", status_code=303)


@router.get("/plan/{plan_id}", response_class=HTMLResponse)
def plan_page(request: Request, plan_id: int, db: Session = Depends(get_db)):
    """Day-wise plan display plus the feedback box."""
    record = _get_plan(db, plan_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    user = service.get_user_or_none(db, record.user_id)
    return templates.TemplateResponse(
        request,
        "result.html",
        {
            "user": user,
            "plan": record,
            "days": service.plan_days(record),
            "tip": record.tip,
            "feedback": record.feedback,
            "flash": request.query_params.get("regenerated") == "1",
        },
    )


@router.post("/plan/{plan_id}/feedback")
def plan_feedback(
    request: Request,
    plan_id: int,
    feedback: str = Form(""),
    db: Session = Depends(get_db),
):
    """Accept user suggestions and regenerate the stored plan."""
    record = _get_plan(db, plan_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Plan not found")

    text = " ".join(feedback.split())
    if len(text) < 3 or len(text) > 600:
        message = (
            "Tell us what to change — at least 3 characters."
            if len(text) < 3
            else "Keep feedback to 600 characters or fewer."
        )
        return templates.TemplateResponse(
            request,
            "result.html",
            {
                "user": service.get_user_or_none(db, record.user_id),
                "plan": record,
                "days": service.plan_days(record),
                "tip": record.tip,
                "feedback": record.feedback,
                "flash": False,
                "feedback_error": message,
            },
            status_code=422,
        )

    try:
        service.apply_feedback(db, record.user_id, text)
    except LookupError:
        raise HTTPException(status_code=404, detail="Plan not found") from None
    return RedirectResponse(url=f"/plan/{plan_id}?regenerated=1", status_code=303)


@router.get("/admin/users", response_class=HTMLResponse)
def all_users(request: Request, db: Session = Depends(get_db)):
    """Admin panel: every stored user with their plan status."""
    users = _list_users(db)
    return templates.TemplateResponse(
        request,
        "all_users.html",
        {"users": users},
    )


@router.get("/admin")
def admin_home():
    return RedirectResponse(url="/admin/users", status_code=303)


# --------------------------------------------------------------------------- #
# small helpers kept local to avoid circular imports
# --------------------------------------------------------------------------- #
def _get_plan(db: Session, plan_id: int):
    from .models import WorkoutPlan

    return db.get(WorkoutPlan, plan_id)


def _list_users(db: Session):
    from .models import User

    return db.query(User).order_by(User.id.desc()).all()
