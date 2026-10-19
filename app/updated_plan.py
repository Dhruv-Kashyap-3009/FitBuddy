"""AI plan/nutrition generator (updated_plan.py).

Talks to Google Gemini (1.5 Flash with a 1.5 Pro fallback) to build a
structured 7-day workout plan and a goal-specific nutrition/recovery tip.
When no API key is configured — or the API errors — it falls back to a
deterministic local generator so the product still works end to end.
"""

from __future__ import annotations

import json
import logging
import re

from .config import GEMINI_API_KEY, GEMINI_MODEL, GEMINI_MODEL_FALLBACK

logger = logging.getLogger("fitbuddy.ai")

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

TIPS = {
    "weight loss": [
        "Walk 20–30 minutes after your largest meal — it blunts the blood sugar spike and burns extra calories without adding fatigue.",
        "Fill half your plate with vegetables before anything else; volume first keeps calories in check without weighing food.",
        "Prioritise sleep: under 7 hours raises hunger hormones and undoes a week of good training.",
        "Drink a glass of water before each meal — thirst is often mistaken for hunger.",
    ],
    "muscle gain": [
        "Include 30–40 g of protein in your post-workout meal to maximise muscle protein synthesis.",
        "Spread protein across 4 meals (0.3–0.4 g per kg bodyweight each) — the total daily amount matters most.",
        "Add a calorie-dense snack like Greek yoghurt with nuts and honey between training and dinner.",
        "Recovery grows muscle: take a full rest day and hit 8 hours of sleep on training days.",
    ],
    "general wellness": [
        "Take a 5-minute mobility break every hour — hips and thoracic spine first.",
        "Eat a palm-sized protein source at every meal to steady energy and mood.",
        "Swap one screen-based evening ritual for stretching or a short walk to improve sleep quality.",
        "Keep a hydration benchmark: one glass on waking, and one with every cup of coffee.",
    ],
}

PLAN_SCHEMA_HINT = """{
  "days": [
    {"day": "Monday", "focus": "Upper body strength",
     "workout": ["Push-ups — 3 sets of 8-12", "Bent-over rows — 3 x 10"],
     "notes": "Rest 90s between sets."}
  ]
}"""


# --------------------------------------------------------------------------- #
# Gemini access
# --------------------------------------------------------------------------- #
def _generate_text(prompt: str) -> str | None:
    """Call Gemini, falling back from Flash to Pro. Returns None on failure."""
    if not GEMINI_API_KEY:
        return None
    try:
        import google.generativeai as genai

        genai.configure(api_key=GEMINI_API_KEY)
    except Exception as exc:  # pragma: no cover - import/config failures
        logger.warning("Gemini client unavailable (%s); using local generator", exc)
        return None

    for model_name in (GEMINI_MODEL, GEMINI_MODEL_FALLBACK):
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(
                prompt,
                generation_config={"temperature": 0.7, "response_mime_type": "text/plain"},
            )
            text = (response.text or "").strip()
            if text:
                return text
        except Exception as exc:
            logger.warning("Gemini call to %s failed: %s", model_name, exc)
    return None


def _extract_json(text: str) -> dict | None:
    """Parse JSON out of a model reply, tolerating code fences and prose."""
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    try:
        return json.loads(text)
    except ValueError:
        pass
    brace = re.search(r"\{.*\}", text, re.DOTALL)
    if brace:
        try:
            return json.loads(brace.group(0))
        except ValueError:
            return None
    return None


def _normalise_days(data: dict | None) -> list[dict] | None:
    """Coerce a model response into a clean 7-day structure."""
    if not isinstance(data, dict):
        return None
    days = data.get("days") or data.get("plan") or []
    if not isinstance(days, list):
        return None
    clean: list[dict] = []
    for i, day in enumerate(days[:7]):
        if not isinstance(day, dict):
            continue
        workout = day.get("workout") or day.get("exercises") or []
        if isinstance(workout, str):
            workout = [line for line in workout.split("\n") if line.strip()]
        elif not isinstance(workout, list):
            workout = []
        clean.append(
            {
                "day": str(day.get("day") or DAY_NAMES[i % 7]),
                "focus": str(day.get("focus") or day.get("title") or "Full body"),
                "workout": [str(x).strip() for x in workout if str(x).strip()],
                "notes": str(day.get("notes") or day.get("note") or ""),
            }
        )
    return clean if len(clean) == 7 else None


# --------------------------------------------------------------------------- #
# Fallback (offline) generator
# --------------------------------------------------------------------------- #
INTENSITY_SETS = {"low": 2, "medium": 3, "high": 4}
REP_RANGES = {"low": "10-12", "medium": "12-15", "high": "15-20"}

GOAL_ROUTINES = {
    "weight loss": [
        ("Full body circuit", ["Goblet squats", "Push-ups", "Dumbbell rows", "Mountain climbers"], "Keep rest to 30s to hold the heart rate up."),
        ("Cardio + core", ["Brisk walk or jog — 25 min", "Bicycle crunches", "Plank", "Dead bug"], "Steady pace; you should be able to talk."),
        ("Lower body burnout", ["Bodyweight lunges", "Glute bridges", "Step-ups", "Wall sit"], "Control the lowering phase for 3 seconds."),
        ("Upper body + HIIT", ["Push-up variations", "Shoulder press", "Burpees — 30s", "Jumping jacks"], "Alternate strength and cardio blocks."),
        ("Active recovery", ["30 min walk", "Hip circles", "Cat-cow stretches", "Foam roll"], "Movement, not intensity — flush the legs."),
        ("Conditioning", ["Jump rope or skipping — 5 rounds", "Kettlebell swings", "Reverse lunges"], "Round = 60s work / 60s rest."),
        ("Rest", ["Light stretching or yoga — 15 min"], "Sleep and hydration do the work today."),
    ],
    "muscle gain": [
        ("Push — chest & triceps", ["Bench press or push-ups — 4 x %s", "Overhead press — 3 x %s", "Triceps dips — 3 x %s"], "Progressive overload: add weight when reps top the range."),
        ("Pull — back & biceps", ["Pull-ups or lat pulldown — 4 x %s", "Bent-over rows — 3 x %s", "Bicep curls — 3 x %s"], "Squeeze at the top of every rep."),
        ("Legs — quads & glutes", ["Back squats — 4 x %s", "Romanian deadlifts — 3 x %s", "Walking lunges — 3 x %s"], "Full depth before adding load."),
        ("Rest / mobility", ["Hip mobility — 10 min", "Light rowing — 10 min"], "Recovery is when muscle is built."),
        ("Push — shoulders & arms", ["Dumbbell shoulder press — 4 x %s", "Lateral raises — 3 x %s", "Skull crushers — 3 x %s"], "Strict form, no momentum."),
        ("Pull — arms & rear delts", ["Barbell curls — 4 x %s", "Face pulls — 3 x %s", "Hammer curls — 3 x %s"], "Control the eccentric for 2 seconds."),
        ("Rest", ["Walk — 20 min", "Full-body stretch"], "Eat and sleep like it's part of the program."),
    ],
    "general wellness": [
        ("Full body basics", ["Goblet squats — 3 x %s", "Push-ups — 3 x %s", "One-arm rows — 3 x %s"], "Leave 2 reps in the tank."),
        ("Cardio + posture", ["Brisk walk or cycle — 25 min", "Band pull-aparts", "Glute bridges"], "Posture work after cardio."),
        ("Lower body + balance", ["Bodyweight squats — 3 x %s", "Single-leg deadlift — 3 x %s", "Calf raises — 3 x %s"], "Balance builds joint stability."),
        ("Upper body + core", ["Incline push-ups — 3 x %s", "Plank — 3 x 40s", "Side plank — 2 x 30s"], "Breathe through the holds."),
        ("Active recovery", ["Yoga flow — 20 min", "Easy walk"], "Best session of the week for most people."),
        ("Play day", ["Sport of choice — 30 min", "Light circuit: squats, push-ups, rows"], "Choose something genuinely fun."),
        ("Rest", ["Stretching and an early night"], "Set next week's intention today."),
    ],
}


def _fallback_plan(goal: str, intensity: str) -> dict:
    reps = REP_RANGES.get(intensity, "12-15")
    sets = INTENSITY_SETS.get(intensity, 3)
    days = []
    for i, (focus, exercises, notes) in enumerate(GOAL_ROUTINES.get(goal, GOAL_ROUTINES["general wellness"])):
        workout = [ex % (reps,) if "%s" in ex else ex for ex in exercises]
        if focus != "Rest" and focus != "Active recovery" and focus != "Play day":
            workout = [f"{ex} — {sets} x {reps}" if " x " not in ex and "min" not in ex and "—" not in ex else ex for ex in workout]
        days.append({"day": DAY_NAMES[i], "focus": focus, "workout": workout, "notes": notes})
    return {"days": days}


def _fallback_tip(goal: str) -> str:
    return TIPS.get(goal, TIPS["general wellness"])[0]


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def generate_workout_plan(
    name: str,
    age: int,
    weight: float,
    goal: str,
    intensity: str,
    feedback: str = "",
) -> tuple[dict, str]:
    """Return (plan_dict, source) where source is 'gemini' or 'fallback'."""
    feedback_clause = (
        f"\nThe user previously asked for this change to their plan: '{feedback}'. Apply it across the week."
        if feedback
        else ""
    )
    prompt = f"""You are an experienced strength and conditioning coach.
Create a structured 7-day workout plan (Monday through Sunday) for:
- Athlete: {name}, age {age}, weight {weight} kg
- Goal: {goal}
- Preferred intensity: {intensity}{feedback_clause}

Rules:
- Day 7 must include rest or active recovery if the week has 6 training days.
- Each day needs a short focus title, 3-5 concrete exercises with sets/reps, and one note.
- Match volume and difficulty to intensity: low = 2-3 sets, medium = 3, high = 4+.
- Reply with ONLY valid JSON in exactly this shape:
{PLAN_SCHEMA_HINT}"""

    text = _generate_text(prompt)
    if text:
        days = _normalise_days(_extract_json(text))
        if days:
            logger.info("Gemini generated a 7-day plan for %s", name)
            return {"days": days}, "gemini"
        logger.warning("Gemini reply was not usable JSON; using local generator")

    logger.info("Using local fallback generator for %s", name)
    return _fallback_plan(goal, intensity), "fallback"


def generate_tip(goal: str, feedback: str = "") -> tuple[str, str]:
    """Return (tip, source) for a goal — AI first, curated list as backstop."""
    prompt = f"""Give one concise, practical nutrition or recovery tip (max 40 words) for a user whose fitness goal is "{goal}".
Reply with the tip only — no preamble, no markdown.{f" Also respect this feedback: {feedback}." if feedback else ""}"""
    text = _generate_text(prompt)
    if text:
        tip = " ".join(text.replace("*", "").split())
        if 10 <= len(tip) <= 400:
            return tip, "gemini"
    return _fallback_tip(goal), "fallback"
