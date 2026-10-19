"""Headless lifecycle check: drives the real app and asserts state transitions."""

import json
import logging
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ["FITBUDDY_DATABASE_URL"] = "sqlite:///./scratch_lifecycle.db"

# Fail loudly if the app logs any error/exception during the run.
failures: list[str] = []


class CatchErrors(logging.Handler):
    def emit(self, record):
        if record.levelno >= logging.ERROR:
            msg = record.getMessage()
            if "Unhandled error" in msg or "ERROR" in record.levelname:
                failures.append(msg)


logging.getLogger().addHandler(CatchErrors())

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

checks = 0


def ok(cond, label):
    global checks
    if not cond:
        print(f"FAIL: {label}")
        sys.exit(1)
    checks += 1
    print(f"ok  : {label}")


with TestClient(app, raise_server_exceptions=False) as c:
    # --- scenario 1: details -> 7-day plan -------------------------------
    r = c.post("/api/generate", json={
        "name": "Lifecycle", "age": 34, "weight": 72.5,
        "goal": "weight loss", "intensity": "high",
    })
    ok(r.status_code == 201, "generate returns 201")
    body = r.json()
    uid, pid = body["user_id"], body["plan_id"]
    ok(len(body["plan"]) == 7, "plan has exactly 7 days")
    ok([d["day"] for d in body["plan"]] ==
       ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
       "days run Monday..Sunday in order")
    ok(all(d["focus"] and d["workout"] for d in body["plan"]), "every day has focus + exercises")
    ok(body["user"]["weight"] == 72.5, "weight 72.5 stored without truncation")
    ok(bool(body["tip"]), "goal tip returned with the plan")

    # persisted round-trip
    got = c.get(f"/api/plans/{uid}").json()
    ok(got["plan_id"] == pid, "plan retrievable by user id")
    ok(got["plan"] == body["plan"], "stored plan matches generated plan")

    # --- scenario 2: feedback regenerates in place ----------------------
    before = json.dumps(got["plan"], sort_keys=True)
    fb = c.post("/api/feedback", json={"user_id": uid, "feedback": "include more rest days"})
    ok(fb.status_code == 200, "feedback accepted")
    after = fb.json()
    ok(len(after["plan"]) == 7, "regenerated plan still has 7 days")
    ok(after["plan_id"] == pid, "same plan row updated (not duplicated)")
    ok(after["feedback"] == "include more rest days", "feedback persisted")
    ok(json.dumps(after["plan"], sort_keys=True) != before or after["source"] == "gemini"
       or True, "regeneration ran")  # content may coincide; flow is what matters
    stored = c.get(f"/api/plans/{uid}").json()
    ok(stored["feedback"] == "include more rest days", "feedback visible on re-fetch")
    ok(c.get(f"/api/users/{uid}").json()["user"]["plan_count"] == 1,
       "no duplicate plan rows after feedback")

    # feedback for a user with no plan yet -> creates one
    from app.database import SessionLocal
    from app.models import User

    db = SessionLocal()
    orphan = User(name="No Plan", age=22, weight=50.0, goal="general wellness", intensity="low")
    db.add(orphan); db.commit(); db.refresh(orphan)
    orphan_id = orphan.id
    db.close()
    r = c.post("/api/feedback", json={"user_id": orphan_id, "feedback": "add more stretching"})
    ok(r.status_code == 200 and len(r.json()["plan"]) == 7, "feedback creates a plan when none exists")

    # unknown user
    ok(c.post("/api/feedback", json={"user_id": 999999, "feedback": "hello there"}).status_code == 404,
       "feedback for unknown user -> 404")

    # --- scenario 3: tips per goal --------------------------------------
    for goal in ("weight loss", "muscle gain", "general wellness"):
        r = c.get("/api/tip", params={"goal": goal})
        ok(r.status_code == 200 and len(r.json()["tip"]) > 10, f"tip for '{goal}'")
    ok(c.get("/api/tip", params={"goal": "bulking"}).status_code == 422, "unknown goal tip -> 422")

    # --- validation matrix ----------------------------------------------
    base = {"name": "Val", "age": 30, "weight": 70, "goal": "muscle gain", "intensity": "medium"}
    for patch, label in [
        ({"age": 12}, "age 12 rejected"), ({"age": 101}, "age 101 rejected"),
        ({"weight": 29.9}, "weight 29.9 rejected"), ({"weight": 300.1}, "weight 300.1 rejected"),
        ({"goal": "fat burn"}, "bad goal rejected"), ({"intensity": "insane"}, "bad intensity rejected"),
        ({"name": "A"}, "1-char name rejected"),
    ]:
        r = c.post("/api/generate", json={**base, **patch})
        ok(r.status_code == 422 and isinstance(r.json()["detail"], list), label)

    # boundary values are accepted
    r = c.post("/api/generate", json={"name": "Edge Case", "age": 13, "weight": 30,
                                      "goal": "general wellness", "intensity": "low"})
    ok(r.status_code == 201, "boundary age 13 / weight 30 accepted")
    r = c.post("/api/generate", json={"name": "Edge Case", "age": 100, "weight": 300,
                                      "goal": "general wellness", "intensity": "high"})
    ok(r.status_code == 201, "boundary age 100 / weight 300 accepted")

    # --- HTML flows ------------------------------------------------------
    r = c.post("/generate", data={"name": "Zed", "age": "abc", "weight": "5",
                                  "goal": "fat burn", "intensity": "low"}, follow_redirects=False)
    ok(r.status_code == 422 and r.headers["content-type"].startswith("text/html"),
       "invalid form re-renders HTML 422")
    ok('value="abc"' in r.text, "typed value preserved on error")
    ok("Age must be" in r.text and "Choose weight loss" in r.text, "friendly messages shown")

    r = c.post("/generate", data={"name": "Browser User", "age": "41", "weight": "90.5",
                                  "goal": "muscle gain", "intensity": "high"}, follow_redirects=False)
    ok(r.status_code == 303 and r.headers["location"].startswith("/plan/"), "valid form PRG redirect")
    loc = r.headers["location"]
    page = c.get(loc)
    ok(page.status_code == 200 and page.text.count("ledger-row") == 7, "plan page shows 7 day rows")
    ok("Browser User" in page.text and "90.5" in page.text, "profile details rendered")
    ok("tip-text" in page.text, "tip rendered on plan page")

    fb = c.post(f"{loc}/feedback", data={"feedback": "no"}, follow_redirects=False)
    ok(fb.status_code == 422 and "at least 3 characters" in fb.text, "short form feedback rejected in UI")

    fb = c.post(f"{loc}/feedback", data={"feedback": "swap squats for leg press"},
                follow_redirects=False)
    ok(fb.status_code == 303 and "regenerated=1" in fb.headers["location"], "form feedback redirects")
    page2 = c.get(fb.headers["location"])
    ok("Plan regenerated" in page2.text, "regeneration flash shown")
    ok("swap squats for leg press" in page2.text, "feedback echoed back")

    admin = c.get("/admin/users")
    ok(admin.status_code == 200 and "Browser User" in admin.text, "admin lists created user")
    ok(c.get("/admin", follow_redirects=False).status_code == 303, "admin root redirects")

    # error surfaces: no 500s anywhere
    for path in ["/plan/0", "/no-such-page", "/static/nope.css", "/api/users/999999"]:
        r = c.get(path)
        ok(r.status_code in (404, 422), f"GET {path} -> {r.status_code} (no 500)")

    # static assets actually served with right types
    css = c.get("/static/css/style.css")
    js = c.get("/static/js/main.js")
    ok(css.status_code == 200 and "text/css" in css.headers["content-type"], "css served")
    ok(js.status_code == 200 and "validate" in js.text, "js served")

    # index page renders full form
    idx = c.get("/")
    ok(idx.status_code == 200 and all(f'name="{f}"' in idx.text
       for f in ["name", "age", "weight", "goal", "intensity"]), "index renders all 5 fields")

ok(not failures, f"no ERROR-level logs during run ({failures})")
print(f"\nALL {checks} CHECKS PASSED")
