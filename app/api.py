"""JSON API endpoints: generate plan, feedback, tips, retrieval, admin."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from . import service
from .config import GOALS
from .database import get_db
from .schemas import FeedbackRequest, PlanRequest, TipRequest
from .updated_plan import generate_tip

logger = logging.getLogger("fitbuddy.api")

router = APIRouter(prefix="/api")


@router.get("/health")
def health():
    return {"status": "ok", "service": "fitbuddy"}


@router.post("/generate", status_code=201)
def generate_plan(req: PlanRequest, db: Session = Depends(get_db)):
    """Send user data to the AI model and store the 7-day plan."""
    user, record = service.create_user_with_plan(db, req)
    return {
        "user_id": user.id,
        "plan_id": record.id,
        "user": user.to_dict(),
        "plan": service.plan_days(record),
        "tip": record.tip,
        "source": record.source,
    }


@router.post("/feedback")
def feedback(req: FeedbackRequest, db: Session = Depends(get_db)):
    """Regenerate an existing plan from the user's suggestions."""
    if service.get_user_or_none(db, req.user_id) is None:
        raise HTTPException(status_code=404, detail="User not found")
    try:
        record = service.apply_feedback(db, req.user_id, req.feedback)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    return {
        "user_id": req.user_id,
        "plan_id": record.id,
        "plan": service.plan_days(record),
        "tip": record.tip,
        "feedback": record.feedback,
        "source": record.source,
    }


@router.get("/tip")
def tip(goal: str = Query(..., description="weight loss | muscle gain | general wellness")):
    """Nutrition or recovery tip for a selected goal."""
    goal = goal.strip().lower()
    if goal not in GOALS:
        raise HTTPException(status_code=422, detail=f"Goal must be one of: {', '.join(GOALS)}")
    text, source = generate_tip(goal)
    return {"goal": goal, "tip": text, "source": source}


@router.post("/tip")
def tip_post(req: TipRequest):
    text, source = generate_tip(req.goal)
    return {"goal": req.goal, "tip": text, "source": source}


@router.get("/users")
def list_users(db: Session = Depends(get_db)):
    from .models import User

    users = db.query(User).order_by(User.id.desc()).all()
    return {"count": len(users), "users": [u.to_dict() for u in users]}


@router.get("/users/{user_id}")
def get_user(user_id: int, db: Session = Depends(get_db)):
    user = service.get_user_or_none(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    record = service.latest_plan(db, user_id)
    return {
        "user": user.to_dict(),
        "plan_id": record.id if record else None,
        "plan": service.plan_days(record) if record else [],
        "tip": record.tip if record else "",
        "source": record.source if record else None,
    }


@router.get("/plans/{user_id}")
def get_plan(user_id: int, db: Session = Depends(get_db)):
    if service.get_user_or_none(db, user_id) is None:
        raise HTTPException(status_code=404, detail="User not found")
    record = service.latest_plan(db, user_id)
    if record is None:
        raise HTTPException(status_code=404, detail="No plan generated yet for this user")
    return {
        "user_id": user_id,
        "plan_id": record.id,
        "plan": service.plan_days(record),
        "tip": record.tip,
        "feedback": record.feedback,
        "source": record.source,
    }
