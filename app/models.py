"""SQLAlchemy ORM models: users and workout plans."""

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    age: Mapped[int] = mapped_column(Integer, nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False)  # kg
    goal: Mapped[str] = mapped_column(String(40), nullable=False)
    intensity: Mapped[str] = mapped_column(String(10), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    plans: Mapped[list["WorkoutPlan"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="WorkoutPlan.id",
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "age": self.age,
            "weight": self.weight,
            "goal": self.goal,
            "intensity": self.intensity,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "plan_count": len(self.plans),
        }


class WorkoutPlan(Base):
    __tablename__ = "plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    # JSON string: {"days": [{"day": "Monday", "focus": ..., "workout": [...], "notes": ...}]}
    plan_json: Mapped[str] = mapped_column(Text, nullable=False)
    tip: Mapped[str] = mapped_column(Text, nullable=False, default="")
    feedback: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="gemini")  # gemini | fallback
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    user: Mapped[User] = relationship(back_populates="plans")

    def to_dict(self) -> dict:
        import json

        try:
            plan = json.loads(self.plan_json)
        except ValueError:
            plan = {"days": []}
        return {
            "id": self.id,
            "user_id": self.user_id,
            "plan": plan,
            "tip": self.tip,
            "feedback": self.feedback,
            "source": self.source,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
