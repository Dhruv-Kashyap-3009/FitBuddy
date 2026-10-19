"""Endpoint + UI flow tests for FitBuddy (pytest + FastAPI TestClient)."""

import os

# Keep the test database separate from the dev one (must precede app import).
os.environ.setdefault("FITBUDDY_DATABASE_URL", "sqlite:///./fitbuddy_test.db")

import pytest
from fastapi.testclient import TestClient

from app import models  # noqa: F401  (register tables)
from app.database import Base, engine
from app.main import app


@pytest.fixture()
def client():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


VALID_USER = {
    "name": "Asha Rao",
    "age": 27,
    "weight": 61.5,
    "goal": "muscle gain",
    "intensity": "high",
}


# --------------------------------------------------------------------------- #
# API: plan generation
# --------------------------------------------------------------------------- #
def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_generate_plan_returns_seven_days_and_tip(client):
    r = client.post("/api/generate", json=VALID_USER)
    assert r.status_code == 201
    body = r.json()
    assert len(body["plan"]) == 7
    assert [d["day"] for d in body["plan"]][0] == "Monday"
    for day in body["plan"]:
        assert day["focus"] and day["workout"]
    assert body["tip"]
    assert body["source"] in {"gemini", "fallback"}

    # persisted and retrievable
    fetched = client.get(f"/api/plans/{body['user_id']}")
    assert fetched.status_code == 200
    assert fetched.json()["plan_id"] == body["plan_id"]
    assert client.get("/api/users").json()["count"] == 1


@pytest.mark.parametrize(
    "patch",
    [
        {"age": 9},
        {"age": 101},
        {"weight": 10},
        {"goal": "fat burn"},
        {"intensity": "extreme"},
        {"name": "A"},
        {"name": "   "},
    ],
)
def test_generate_rejects_invalid_input(client, patch):
    r = client.post("/api/generate", json={**VALID_USER, **patch})
    assert r.status_code == 422
    assert isinstance(r.json()["detail"], list)


# --------------------------------------------------------------------------- #
# API: feedback loop
# --------------------------------------------------------------------------- #
def test_feedback_regenerates_plan(client):
    user_id = client.post("/api/generate", json=VALID_USER).json()["user_id"]
    r = client.post("/api/feedback", json={"user_id": user_id, "feedback": "more focus on cardio"})
    assert r.status_code == 200
    body = r.json()
    assert len(body["plan"]) == 7
    assert body["feedback"] == "more focus on cardio"

    stored = client.get(f"/api/plans/{user_id}").json()
    assert stored["feedback"] == "more focus on cardio"


def test_feedback_unknown_user_404(client):
    r = client.post("/api/feedback", json={"user_id": 4242, "feedback": "more rest days"})
    assert r.status_code == 404


def test_feedback_too_short_422(client):
    user_id = client.post("/api/generate", json=VALID_USER).json()["user_id"]
    r = client.post("/api/feedback", json={"user_id": user_id, "feedback": "x"})
    assert r.status_code == 422


# --------------------------------------------------------------------------- #
# API: tips
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("goal", ["weight loss", "muscle gain", "general wellness"])
def test_tip_for_each_goal(client, goal):
    r = client.get("/api/tip", params={"goal": goal})
    assert r.status_code == 200
    assert len(r.json()["tip"]) > 10
    assert r.json()["goal"] == goal


def test_tip_unknown_goal_422(client):
    assert client.get("/api/tip", params={"goal": "nope"}).status_code == 422


# --------------------------------------------------------------------------- #
# UI flows
# --------------------------------------------------------------------------- #
def test_index_renders_form(client):
    r = client.get("/")
    assert r.status_code == 200
    assert 'action="/generate"' in r.text
    for field in ["name", "age", "weight", "goal", "intensity"]:
        assert f'name="{field}"' in r.text


def test_invalid_form_rerenders_with_messages(client):
    r = client.post(
        "/generate",
        data={"name": "A", "age": "9", "weight": "5", "goal": "fat burn", "intensity": "low"},
        follow_redirects=False,
    )
    assert r.status_code == 422
    assert r.headers["content-type"].startswith("text/html")
    assert "Age must be" in r.text
    assert "Choose weight loss" in r.text
    assert 'value="9"' in r.text  # entered values are preserved


def test_valid_form_redirects_to_plan_page(client):
    r = client.post(
        "/generate",
        data={"name": "Ravi Kumar", "age": "31", "weight": "78", "goal": "weight loss", "intensity": "medium"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"].startswith("/plan/")

    page = client.get(r.headers["location"])
    assert page.status_code == 200
    assert page.text.count("ledger-row") == 7
    assert "Ravi Kumar's week" in page.text
    assert "tip-text" in page.text
    assert '<span class="day-name">MON</span>' in page.text  # Monday, day 01


def test_feedback_flow_updates_page(client):
    location = client.post(
        "/generate",
        data={"name": "Meera", "age": "27", "weight": "55", "goal": "general wellness", "intensity": "high"},
        follow_redirects=False,
    ).headers["location"]

    r = client.post(f"{location}/feedback", data={"feedback": "include more rest days"}, follow_redirects=False)
    assert r.status_code == 303
    assert "regenerated=1" in r.headers["location"]

    page = client.get(r.headers["location"])
    assert "Plan regenerated" in page.text
    assert "include more rest days" in page.text


def test_admin_lists_users(client):
    client.post("/api/generate", json=VALID_USER)
    r = client.get("/admin/users")
    assert r.status_code == 200
    assert "Asha Rao" in r.text
    assert "open plan" in r.text


def test_unknown_plan_page_404(client):
    assert client.get("/plan/98765").status_code == 404


def test_static_assets_served(client):
    css = client.get("/static/css/style.css")
    js = client.get("/static/js/main.js")
    assert css.status_code == 200 and "text/css" in css.headers["content-type"]
    assert js.status_code == 200 and "validate" in js.text
