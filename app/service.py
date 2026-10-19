"""Business logic shared by the HTML routes and the JSON API."""

from __future__ import annotations

import json
import logging

from sqlalchemy.orm import Session

from .models import User, WorkoutPlan
from .schemas import PlanRequest
from .updated_plan import generate_tip, generate_workout_plan

logger = logging.getLogger("fitbuddy.service")


def create_user_with_plan(db: Session, req: PlanRequest) -> tuple[User, WorkoutPlan]:
    """Persist a new user together with their generated 7-day plan."""
    plan, source = generate_workout_plan(
        name=req.name,
        age=req.age,
        weight=req.weight,
        goal=req.goal,
        intensity=req.intensity,
    )
    tip, _tip_source = generate_tip(req.goal)

    user = User(
        name=req.name,
        age=req.age,
        weight=req.weight,
        goal=req.goal,
        intensity=req.intensity,
    )
    db.add(user)
    db.flush()  # assign user.id

    record = WorkoutPlan(
        user_id=user.id,
        plan_json=json.dumps(plan, ensure_ascii=False),
        tip=tip,
        feedback="",
        source=source,
    )
    db.add(record)
    db.commit()
    db.refresh(user)
    db.refresh(record)
    logger.info("Created user #%s (%s) with plan #%s via %s", user.id, user.name, record.id, source)
    return user, record


def latest_plan(db: Session, user_id: int) -> WorkoutPlan | None:
    return (
        db.query(WorkoutPlan)
        .filter(WorkoutPlan.user_id == user_id)
        .order_by(WorkoutPlan.id.desc())
        .first()
    )


def get_user_or_none(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)


def apply_feedback(db: Session, user_id: int, feedback: str) -> WorkoutPlan:
    """Regenerate a user's plan from their feedback and update it in place."""
    user = db.get(User, user_id)
    if user is None:
        raise LookupError(f"No user with id {user_id}")

    plan, source = generate_workout_plan(
        name=user.name,
        age=user.age,
        weight=user.weight,
        goal=user.goal,
        intensity=user.intensity,
        feedback=feedback,
    )
    tip, _ = generate_tip(user.goal, feedback=feedback)

    record = latest_plan(db, user_id)
    if record is None:
        record = WorkoutPlan(user_id=user_id, plan_json="", tip="", feedback="")
        db.add(record)

    record.plan_json = json.dumps(plan, ensure_ascii=False)
    record.tip = tip
    record.feedback = feedback
    record.source = source
    db.commit()
    db.refresh(record)
    logger.info("Regenerated plan #%s for user #%s with feedback via %s", record.id, user_id, source)
    return record


def plan_days(record: WorkoutPlan) -> list[dict]:
    """Decode a stored plan into its list of day dicts."""
    try:
        data = json.loads(record.plan_json)
    except (TypeError, ValueError):
        return []
    days = data.get("days", []) if isinstance(data, dict) else []
    return [d for d in days if isinstance(d, dict)]
