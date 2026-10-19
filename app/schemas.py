"""Pydantic schemas — shared validation for API and HTML form flows."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from .config import GOALS, INTENSITIES

Goal = Literal["weight loss", "muscle gain", "general wellness"]
Intensity = Literal["low", "medium", "high"]


class PlanRequest(BaseModel):
    """User details submitted from the intake form."""

    name: str = Field(..., min_length=2, max_length=80)
    age: int = Field(..., ge=13, le=100)
    weight: float = Field(..., ge=30, le=300)
    goal: Goal
    intensity: Intensity

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        v = " ".join(v.split())
        if len(v) < 2:
            raise ValueError("Name must be at least 2 characters.")
        return v

    @field_validator("goal", "intensity")
    @classmethod
    def lowercase(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("goal")
    @classmethod
    def known_goal(cls, v: str) -> str:
        if v not in GOALS:
            raise ValueError(f"Goal must be one of: {', '.join(GOALS)}.")
        return v

    @field_validator("intensity")
    @classmethod
    def known_intensity(cls, v: str) -> str:
        if v not in INTENSITIES:
            raise ValueError(f"Intensity must be one of: {', '.join(INTENSITIES)}.")
        return v


class FeedbackRequest(BaseModel):
    """Feedback on an existing plan, used to regenerate it."""

    user_id: int = Field(..., gt=0)
    feedback: str = Field(..., min_length=3, max_length=600)

    @field_validator("feedback")
    @classmethod
    def clean_feedback(cls, v: str) -> str:
        v = " ".join(v.split())
        if len(v) < 3:
            raise ValueError("Feedback must be at least 3 characters.")
        return v


class TipRequest(BaseModel):
    goal: Goal


class DayPlan(BaseModel):
    day: str
    focus: str
    workout: list[str]
    notes: str = ""


class PlanResponse(BaseModel):
    user_id: int
    plan_id: int
    plan: dict
    tip: str
    source: str
